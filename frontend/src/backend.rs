use crate::{
    ipc::{Decoder, Event},
    logging::Log,
    paths::Paths,
    process::Child,
};
use std::{
    ffi::OsString,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    sync::mpsc::{self, Receiver, Sender},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
#[derive(Clone, Default)]
pub struct Options {
    pub config: Option<PathBuf>,
    pub require_resume: bool,
    pub limit: Option<f64>,
    pub source_languages: Vec<String>,
    pub target_language: Option<String>,
}
pub enum Message {
    Event(Box<Event>),
    Fault(String),
    Started(u32),
    Exited {
        code: u32,
        cancelled: bool,
        wall: f64,
    },
    Failed(String),
}
pub enum Control {
    Cancel,
}
enum Pipe {
    Event(Box<Event>),
    Fault(String),
}
pub struct Worker {
    pub control: Sender<Control>,
    pub messages: Receiver<Message>,
}

fn owned_locks(root: &Path, pid: u32) -> Vec<PathBuf> {
    fn scan(dir: &Path, pid: u32, out: &mut Vec<PathBuf>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for e in entries.flatten() {
            let p = e.path();
            let Ok(m) = e.metadata() else { continue };
            use std::os::windows::fs::MetadataExt;
            if m.file_attributes() & 0x400 != 0 {
                continue;
            }
            if m.is_dir() {
                scan(&p, pid, out);
            } else if p.file_name().is_some_and(|s| s == "run.lock")
                && let Ok(bytes) = std::fs::read(&p)
                && serde_json::from_slice::<serde_json::Value>(&bytes)
                    .ok()
                    .and_then(|v| v["pid"].as_u64())
                    == Some(pid as u64)
            {
                out.push(p);
            }
        }
    }
    let mut out = vec![];
    scan(root, pid, &mut out);
    out
}

fn output_dir(paths: &Paths, options: &Options) -> PathBuf {
    let file = options
        .config
        .clone()
        .unwrap_or(paths.root.join("config_v157.json"));
    let file = if file.is_absolute() {
        file
    } else {
        paths.root.join(file)
    };
    let value = std::fs::read(file)
        .ok()
        .and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok());
    let p = value
        .as_ref()
        .and_then(|v| v["OUTPUT"].as_str())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("output"));
    if p.is_absolute() {
        p
    } else {
        paths.root.join(p)
    }
}

pub fn launch(paths: Paths, source: PathBuf, options: Options, log: Log) -> Worker {
    let (ctrl_tx, ctrl_rx) = mpsc::channel();
    let (ui_tx, ui_rx) = mpsc::channel();
    thread::spawn(move || {
        let started = Instant::now();
        let result = (|| -> std::io::Result<()> {
            let source = paths.prepare_input(&source)?;
            let run = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis();
            let run_dir = paths.logs.join(format!("frontend-runs/{run}"));
            std::fs::create_dir_all(&run_dir)?;
            let out = output_dir(&paths, &options);
            std::fs::create_dir_all(&out)?;
            if !crate::paths::canonical(&out)?.starts_with(&paths.root) {
                return Err(std::io::Error::other("output_outside_root"));
            }
            let stem = format!(
                "{}{}_PRO",
                source.file_stem().unwrap_or_default().to_string_lossy(),
                if options.limit.is_some() {
                    "_SMOKE"
                } else {
                    ""
                }
            );
            let mut saved = vec![];
            for ext in ["txt", "json", "docx"] {
                let name = format!("{stem}.{ext}");
                let target = out.join(&name);
                let backup = run_dir.join(&name);
                let existed = target.is_file();
                if existed {
                    std::fs::copy(&target, &backup)?;
                }
                saved.push((target, backup, existed));
            }
            let mut args: Vec<OsString> = vec![
                "-B".into(),
                "-X".into(),
                "utf8".into(),
                paths.backend.clone().into_os_string(),
                "--ipc".into(),
                "jsonl".into(),
                "--app-root".into(),
                paths.root.clone().into_os_string(),
                source.into_os_string(),
            ];
            if let Some(c) = &options.config {
                args.push("--config".into());
                args.push(c.clone().into_os_string());
            }
            if options.require_resume {
                args.push("--require-resume".into());
            }
            if !options.source_languages.is_empty() {
                args.push("--source-languages".into());
                args.push(options.source_languages.join(",").into());
            }
            if let Some(target) = &options.target_language {
                args.push("--target-language".into());
                args.push(target.into());
            }
            if let Some(limit) = options.limit {
                args.push("--limit-seconds".into());
                args.push(limit.to_string().into());
            }
            log.line("LAUNCH", "backend v1.5.7; stdout JSONL; stderr separate");
            let (child, stdout, stderr) = Child::spawn(&paths.python, &args, &paths.root)?;
            let pid = child.pid;
            let _ = ui_tx.send(Message::Started(pid));
            log.line("PID", &pid.to_string());
            let (pipe_tx, pipe_rx) = mpsc::channel();
            let mut rawlog = std::fs::File::create(run_dir.join("events.jsonl"))?;
            let outlog = log.clone();
            let stdout_thread = thread::spawn(move || {
                let mut decoder = Decoder::default();
                for line in BufReader::new(stdout).lines() {
                    match line {
                        Ok(line) => match decoder.parse(&line) {
                            Ok(e) => {
                                // Preserve machine-readable evidence without transcript content.
                                let mut safe = e.clone();
                                for field in ["text_preview", "source_name", "message"] {
                                    safe.fields.remove(field);
                                }
                                if let Ok(json) = serde_json::to_string(&safe) {
                                    let _ = writeln!(rawlog, "{json}");
                                    let _ = rawlog.flush();
                                }
                                outlog.line(
                                    "EVENT",
                                    &format!(
                                        "{} {} job={} seq={}",
                                        e.event,
                                        e.text("stage"),
                                        e.job_id,
                                        e.sequence
                                    ),
                                );
                                let _ = pipe_tx.send(Pipe::Event(Box::new(e)));
                            }
                            Err(code) => {
                                outlog.line("IPC_ERROR", &code);
                                let _ = pipe_tx.send(Pipe::Fault(code));
                            }
                        },
                        Err(_) => {
                            let _ = pipe_tx.send(Pipe::Fault("stdout_read_error".into()));
                            break;
                        }
                    }
                }
            });
            let errlog = Log::open(&run_dir.join("stderr.log"))?;
            let stderr_thread = thread::spawn(move || {
                for line in BufReader::new(stderr).lines() {
                    if let Ok(line) = line {
                        errlog.line("BACKEND", &line);
                    } else {
                        break;
                    }
                }
            });
            let (mut cancelled, mut exporting, mut terminal, mut cancel_requested) =
                (false, false, false, false);
            let code = loop {
                while let Ok(msg) = pipe_rx.try_recv() {
                    match msg {
                        Pipe::Event(e) => {
                            if e.event == "export_started"
                                || (e.event == "stage_started" && e.text("stage") == "export")
                            {
                                exporting = true;
                            }
                            if e.event == "export_completed" {
                                exporting = false;
                            }
                            if e.terminal() {
                                terminal = true;
                                log.line("TERMINAL",&serde_json::to_string(&serde_json::json!({"event":e.event,"wall_seconds":e.number("wall_seconds"),"inference_calls":e.fields.get("inference_calls")})).unwrap_or_default());
                            }
                            let _ = ui_tx.send(Message::Event(e));
                        }
                        Pipe::Fault(s) => {
                            let _ = ui_tx.send(Message::Fault(s));
                        }
                    }
                }
                if ctrl_rx.try_recv().is_ok() {
                    cancel_requested = true;
                    log.line("CANCEL", "requested; export is non-interruptible");
                }
                if let Some(code) = child.status()? {
                    break code;
                }
                if cancel_requested && !terminal && !exporting {
                    let owned_pids = child.process_ids()?;
                    child.terminate()?;
                    cancelled = true;
                    // If cancellation raced with entry to publication, the worker's own lock
                    // proves ownership; restore the pre-job triplet before releasing that lock.
                    let locks: Vec<_> = owned_pids
                        .iter()
                        .flat_map(|&owner| owned_locks(&paths.root.join("temp"), owner))
                        .collect();
                    if locks
                        .iter()
                        .any(|p| p.to_string_lossy().contains("v156-publication"))
                    {
                        for (target, backup, existed) in &saved {
                            if *existed {
                                let staging = target.with_extension(format!("restore-{pid}"));
                                std::fs::copy(backup, &staging)?;
                                std::fs::rename(staging, target)?;
                            } else if target.exists() {
                                std::fs::remove_file(target)?;
                            }
                        }
                        log.line("CANCEL", "owned publication restored from pre-job snapshot");
                    }
                    for lock in locks {
                        std::fs::remove_file(lock)?;
                    }
                    // Portable temp may live outside the legacy temp directory.
                    for owner in owned_pids {
                        for lock in owned_locks(&paths.root.join("_internal/temp"), owner) {
                            std::fs::remove_file(lock)?;
                        }
                    }
                    log.line(
                        "CANCEL",
                        "child Job Object terminated; owned locks released; cache retained",
                    );
                    break child.status()?.unwrap_or(130);
                }
                thread::sleep(Duration::from_millis(20));
            };
            // Closing the job handle also reaps any leaked descendants before joining pipe readers.
            drop(child);
            let _ = stdout_thread.join();
            let _ = stderr_thread.join();
            while let Ok(msg) = pipe_rx.try_recv() {
                match msg {
                    Pipe::Event(e) => {
                        let _ = ui_tx.send(Message::Event(e));
                    }
                    Pipe::Fault(s) => {
                        let _ = ui_tx.send(Message::Fault(s));
                    }
                }
            }
            log.line(
                "EXIT",
                &format!(
                    "pid={pid} code={code} cancelled={cancelled} subprocess_wall={:.3}",
                    started.elapsed().as_secs_f64()
                ),
            );
            let _ = ui_tx.send(Message::Exited {
                code,
                cancelled,
                wall: started.elapsed().as_secs_f64(),
            });
            Ok(())
        })();
        if let Err(error) = result {
            log.line("WORKER_ERROR", &error.to_string());
            let _ = ui_tx.send(Message::Failed(
                "Backend не запущен или работа прервана; см. лог".into(),
            ));
        }
    });
    Worker {
        control: ctrl_tx,
        messages: ui_rx,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cleanup_ignores_foreign_locks() {
        let p = Paths::discover(None).unwrap();
        assert!(owned_locks(&p.root.join("dev/nonexistent-fixture"), u32::MAX).is_empty());
    }
}
