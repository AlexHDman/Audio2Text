#![windows_subsystem = "windows"]
mod app_state;
mod backend;
mod cache;
mod ipc;
mod logging;
mod media;
mod paths;
mod process;

use app_state::{AppState, Phase};
use backend::{Control, Message, Options, Worker};
use slint::{ComponentHandle, Model, ModelRc, VecModel};
use std::{
    cell::RefCell,
    path::PathBuf,
    rc::Rc,
    time::{Duration, Instant},
};
slint::include_modules!();

fn duration(seconds: f64) -> String {
    let s = seconds.max(0.0) as u64;
    if s < 3600 {
        format!("{:02}:{:02}", s / 60, s % 60)
    } else {
        format!("{:02}:{:02}:{:02}", s / 3600, s / 60 % 60, s % 60)
    }
}
fn output_command(path: &std::path::Path) -> std::process::Command {
    let mut command = std::process::Command::new("explorer.exe");
    command.arg(path);
    command
}
fn open_output(path: &std::path::Path, log: &logging::Log) {
    if path.is_dir() {
        match output_command(path).spawn() {
            Ok(child) => log.line(
                "OUTPUT_OPEN",
                &format!("Explorer pid={} path={}", child.id(), path.display()),
            ),
            Err(e) => log.line("OUTPUT_ERROR", &e.to_string()),
        }
    }
}
fn handle_output(paths: &paths::Paths, log: &logging::Log) {
    if std::fs::create_dir_all(&paths.output).is_ok() {
        open_output(&paths.output, log);
    }
}

fn render(
    ui: &Dashboard,
    state: &AppState,
    stages: &Rc<VecModel<StageRow>>,
    events: &Rc<VecModel<EventRow>>,
) {
    ui.set_status(state.phase.label().into());
    ui.set_busy(state.worker_alive);
    ui.set_can_start(state.selected.is_some() && !state.worker_alive);
    ui.set_can_stop(
        state.worker_alive && state.phase != Phase::CancelPending && state.terminal.is_none(),
    );
    ui.set_warning(state.phase == Phase::Partial);
    ui.set_failure(state.phase == Phase::Error);
    if let Some(file) = &state.selected {
        ui.set_filename(
            file.file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .as_ref()
                .into(),
        );

        let size = std::fs::metadata(file)
            .map(|m| m.len() as f64 / 1_048_576.0)
            .unwrap_or(0.0);
        ui.set_fileinfo(
            format!(
                "{}   ·   {}   ·   {:.1} MB",
                file.extension()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_uppercase(),
                if ui.get_media_duration() >= 0.0 {
                    duration(ui.get_media_duration() as f64)
                } else {
                    "--:--".into()
                },
                size
            )
            .into(),
        );
    }
    let stage_label = |id: &str| {
        if id == "translation" {
            format!("Перевод · {}", ui.get_target_language())
        } else {
            ipc::stage_label(id).to_owned()
        }
    };
    ui.set_stage(stage_label(&state.current_stage).into());
    ui.set_counter(state.progress_label().into());
    ui.set_known_progress(state.ratio().is_some());
    ui.set_progress(state.ratio().unwrap_or(0.0));
    ui.set_progress_unit(
        match state.current_stage.as_str() {
            "asr" | "language_reconciliation" => "Обработано аудиоинтервалов",
            "translation" => "Записи RU / EN · включая кэш и пропуски дубликатов",
            "semantic_grouping" => "Смысловые группы",
            "export" => "Сохранено файлов",
            _ => "Прогресс текущего этапа · общий процент не определён",
        }
        .into(),
    );
    if state.current_stage == "translation" {
        ui.set_progress_unit(
            format!(
                "Записи {} · включая кэш и пропуски дубликатов",
                ui.get_target_language()
            )
            .into(),
        );
    }
    ui.set_elapsed(if state.started.is_some() {
        duration(state.elapsed).into()
    } else {
        "--".into()
    });
    ui.set_eta(state.eta.map(duration).unwrap_or("--".into()).into());
    ui.set_gpu(state.gpu.clone().into());
    ui.set_gpu_load(
        state
            .utilization
            .map(|n| format!("{n:.0}%"))
            .unwrap_or("--".into())
            .into(),
    );
    ui.set_cuda(
        match (state.cuda_available, state.cuda_active) {
            (_, Some(true)) => "ACTIVE",
            (Some(true), Some(false)) => "Доступна",
            (Some(false), _) => "Недоступна",
            _ => "--",
        }
        .into(),
    );
    ui.set_cuda_active(state.cuda_active == Some(true));
    ui.set_vram(
        match (state.vram_used, state.vram_total) {
            (Some(a), Some(b)) => format!("{:.1} / {:.1} GiB", a / 1024.0, b / 1024.0),
            _ => "--".into(),
        }
        .into(),
    );
    ui.set_voices(if state.speakers.is_empty() {
        "--".into()
    } else {
        state.speakers.len().to_string().into()
    });
    ui.set_segments(
        state
            .segments
            .map(|n| n.to_string())
            .unwrap_or("--".into())
            .into(),
    );
    ui.set_groups(
        state
            .groups
            .map(|n| n.to_string())
            .unwrap_or("--".into())
            .into(),
    );
    ui.set_languages(if state.languages.is_empty() {
        "--".into()
    } else {
        state.languages.join(" / ").into()
    });
    ui.set_current_voi(state.current_voi.clone().into());
    ui.set_current_language(state.current_language.clone().into());
    ui.set_current_time(state.timecode.clone().into());
    ui.set_preview(state.preview.clone().into());
    ui.set_formats(if state.output_files.is_empty() {
        "Результаты ещё не созданы".into()
    } else {
        "TXT  /  JSON  /  DOCX".into()
    });
    let rows: Vec<StageRow> = state
        .stages
        .iter()
        .map(|s| StageRow {
            label: stage_label(&s.id).into(),
            state: s.state.clone().into(),
            counter: match (s.done, s.total) {
                (Some(a), Some(b)) => format!("{a}/{b}"),
                _ => String::new(),
            }
            .into(),
        })
        .collect();
    if stages.row_count() != rows.len() {
        stages.set_vec(rows);
    } else {
        // Preserve delegate identity: progress ticks must not restart completion bloom.
        for (index, row) in rows.into_iter().enumerate() {
            if stages.row_data(index).as_ref() != Some(&row) {
                stages.set_row_data(index, row);
            }
        }
    }
    let rows: Vec<EventRow> = state
        .journal
        .iter()
        .rev()
        .map(|e| EventRow {
            time: e.time.clone().into(),
            level: e.level.clone().into(),
            message: e.text.clone().into(),
        })
        .collect();
    if events.iter().collect::<Vec<_>>() != rows {
        events.set_vec(rows);
    }
}

fn request_preview(
    paths: &paths::Paths,
    file: PathBuf,
    generation: &std::cell::Cell<u64>,
    tx: &std::sync::mpsc::Sender<(u64, media::Preview)>,
) {
    let next = generation.get() + 1;
    generation.set(next);
    let root = paths.root.clone();
    let tx = tx.clone();
    std::thread::spawn(move || {
        let _ = tx.send((next, media::inspect(&root, &file, next)));
    });
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args_os().skip(1);
    let (mut root, mut selected) = (None, None);
    let mut options = Options::default();
    let mut auto_start = false;
    while let Some(a) = args.next() {
        match a.to_str() {
            Some("--app-root") => root = args.next().map(PathBuf::from),
            Some("--source") => selected = args.next().map(PathBuf::from),
            Some("--backend-config") => options.config = args.next().map(PathBuf::from),
            Some("--require-resume") => options.require_resume = true,
            Some("--validation-auto-start") => auto_start = true,
            Some("--limit-seconds") => {
                options.limit = args
                    .next()
                    .and_then(|v| v.to_str().and_then(|s| s.parse().ok()))
            }
            _ => return Err("Неизвестный аргумент запуска".into()),
        }
    }
    let paths = paths::Paths::discover(root)?;
    let log = logging::Log::open(&paths.logs.join("frontend_v2.log"))?;
    log.line(
        "STARTUP",
        "Audio2Text 2.0.4 / Slint / frozen inference core; language policy adapter / backend 1.5.7",
    );
    let fatal_log = log.clone();
    std::panic::set_hook(Box::new(move |_| {
        fatal_log.line("FATAL", "Rust panic; UI stopped");
    }));
    let ui = Dashboard::new()?;
    let selected_languages = Rc::new(RefCell::new(Vec::<String>::new()));
    let preview_generation = Rc::new(std::cell::Cell::new(0u64));
    let (preview_tx, preview_rx) = std::sync::mpsc::channel();
    let prefs = paths.logs.join("frontend_v2_settings.json");
    if let Ok(bytes) = std::fs::read(&prefs)
        && let Ok(v) = serde_json::from_slice::<serde_json::Value>(&bytes)
    {
        ui.set_reduced(v["reduced"].as_bool().unwrap_or(false));
        ui.set_auto_open(v["auto_open"].as_bool().unwrap_or(false));
        ui.set_cache_exit_policy(
            cache::exit_policy(v["cache_exit_policy"].as_str().unwrap_or("ask")).into(),
        );
    }
    let stages = Rc::new(VecModel::default());
    let events = Rc::new(VecModel::default());
    ui.set_stages(ModelRc::from(stages.clone()));
    ui.set_events(ModelRc::from(events.clone()));
    let state = Rc::new(RefCell::new(AppState::default()));
    let worker: Rc<RefCell<Option<Worker>>> = Rc::new(RefCell::new(None));
    let _cache_timer = cache::install(&ui, paths.clone(), state.clone());
    let close_pending = Rc::new(RefCell::new(false));
    if let Some(file) = selected
        && paths::Paths::supported(&file)
    {
        let mut s = state.borrow_mut();
        s.selected = Some(file.clone());
        request_preview(&paths, file, &preview_generation, &preview_tx);
        s.phase = Phase::FileSelected;
    }
    render(&ui, &state.borrow(), &stages, &events);
    {
        let weak = ui.as_weak();
        let state = state.clone();
        let stages = stages.clone();
        let events = events.clone();
        let log = log.clone();
        let input_dir = paths.root.join("input");
        let preview_paths = paths.clone();
        let preview_tx = preview_tx.clone();
        let preview_generation = preview_generation.clone();
        ui.on_select_file(move || {
            if state.borrow().worker_alive {
                return;
            }
            if std::fs::create_dir_all(&input_dir).is_err() {
                let mut s = state.borrow_mut();
                s.add("--", "ERROR", "Не удалось создать или открыть папку input");
                log.line("FILE_SELECT", "cannot prepare app input directory");
                if let Some(ui) = weak.upgrade() {
                    render(&ui, &s, &stages, &events);
                }
                return;
            }
            if let Some(file) = rfd::FileDialog::new()
                .set_title("Выберите аудио или видео")
                .set_directory(&input_dir)
                .add_filter("Медиафайлы", &paths::EXTENSIONS)
                .pick_file()
            {
                let mut s = state.borrow_mut();
                if paths::Paths::supported(&file) {
                    s.selected = Some(file.clone());
                    request_preview(&preview_paths, file, &preview_generation, &preview_tx);
                    if let Some(ui) = weak.upgrade() {
                        ui.set_media_duration(-1.0);
                        ui.set_has_thumbnail(false);
                        ui.set_thumbnail(slint::Image::default());
                        ui.set_media_pending(true);
                    }
                    s.phase = Phase::FileSelected;
                    s.add("--", "INFO", "Медиафайл выбран");
                    log.line("FILE_SELECT", "native picker accepted supported file");
                } else {
                    s.add("--", "ERROR", "Формат не поддерживается или файл не найден");
                }
                if let Some(ui) = weak.upgrade() {
                    render(&ui, &s, &stages, &events);
                }
            }
        });
    }
    {
        let weak = ui.as_weak();
        let state = state.clone();
        let worker = worker.clone();
        let paths = paths.clone();
        let options = options.clone();
        let selected_languages = selected_languages.clone();
        let log = log.clone();
        let stages = stages.clone();
        let events = events.clone();
        ui.on_start_job(move || {
            if worker.borrow().is_some() {
                return;
            }
            let mut s = state.borrow_mut();
            let Some(file) = s.selected.clone() else {
                return;
            };
            if !paths::Paths::supported(&file) {
                s.phase = Phase::Error;
                s.add("--", "ERROR", "Файл не найден");
            } else {
                let mut options = options.clone();
                options.source_languages = selected_languages.borrow().clone();
                if let Some(ui) = weak.upgrade() {
                    options.target_language = Some(ui.get_target_language().to_lowercase());
                    ui.set_language_popup(false);
                }
                s.start();
                *worker.borrow_mut() = Some(backend::launch(
                    paths.clone(),
                    file,
                    options.clone(),
                    log.clone(),
                ));
            }
            if let Some(ui) = weak.upgrade() {
                render(&ui, &s, &stages, &events);
            }
        });
    }
    {
        let state = state.clone();
        let worker = worker.clone();
        ui.on_stop_job(move || {
            if let Some(w) = worker.borrow().as_ref() {
                let _ = w.control.send(Control::Cancel);
                state.borrow_mut().phase = Phase::CancelPending;
            }
        });
    }
    {
        let paths = paths.clone();
        let log = log.clone();
        ui.on_open_output(move || {
            handle_output(&paths, &log);
        });
    }
    {
        let weak = ui.as_weak();
        let log = log.clone();
        ui.on_save_settings(move || {
            if let Some(ui) = weak.upgrade() {
                let value =
                    serde_json::json!({"reduced":ui.get_reduced(),"auto_open":ui.get_auto_open(),"cache_exit_policy":cache::exit_policy(ui.get_cache_exit_policy().as_str())});
                if let Ok(data) = serde_json::to_vec_pretty(&value) {
                    let _ = std::fs::write(&prefs, data);
                }
                log.line("SETTINGS", "presentation preferences saved");
            }
        });
    }
    {
        let worker = worker.clone();
        let state = state.clone();
        let close_pending = close_pending.clone();
        let weak = ui.as_weak();
        ui.window().on_close_requested(move || {
            if weak.upgrade().is_some_and(|ui| ui.get_cache_working()) {
                return slint::CloseRequestResponse::KeepWindowShown;
            }
            if let Some(w) = worker.borrow().as_ref() {
                let _ = w.control.send(Control::Cancel);
                state.borrow_mut().phase = Phase::CancelPending;
                *close_pending.borrow_mut() = true;
                slint::CloseRequestResponse::KeepWindowShown
            } else {
                slint::CloseRequestResponse::HideWindow
            }
        });
    }
    {
        let weak = ui.as_weak();
        let selected = selected_languages.clone();
        ui.on_toggle_language(move |code| {
            if let Some(ui) = weak.upgrade() {
                if ui.get_busy() {
                    return;
                }
                let mut codes = selected.borrow_mut();
                let code = code.to_lowercase();
                if code == "auto" {
                    codes.clear();
                } else if let Some(index) = codes.iter().position(|c| c == &code) {
                    codes.remove(index);
                } else if codes.len() < 3 {
                    codes.push(code);
                }
                ui.set_source_choices(ModelRc::new(VecModel::from(
                    ["ru", "en", "af", "nl", "de", "fr", "it", "zh", "he"]
                        .iter()
                        .map(|c| LanguageChoice {
                            code: c.to_uppercase().into(),
                            selected: codes.iter().any(|x| x == c),
                        })
                        .collect::<Vec<_>>(),
                )));
                ui.set_selected_sources(ModelRc::new(VecModel::from(
                    codes
                        .iter()
                        .map(|s| slint::SharedString::from(s.to_uppercase()))
                        .collect::<Vec<_>>(),
                )));
            }
        });
        ui.invoke_toggle_language("auto".into());
    }
    let timer = slint::Timer::default();
    let epoch = Instant::now();
    let weak = ui.as_weak();
    let mut frame = 0u64;
    timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(33),
        move || {
            let Some(ui) = weak.upgrade() else { return };
            frame += 1;
            let mut dirty = false;
            while let Ok((generation, preview)) = preview_rx.try_recv() {
                if generation != preview_generation.get() {
                    continue;
                }
                ui.set_media_pending(false);
                ui.set_media_duration(preview.duration.unwrap_or(-1.0) as f32);
                ui.set_is_video(preview.video);
                let image = preview
                    .image
                    .as_ref()
                    .and_then(|p| slint::Image::load_from_path(p).ok());
                ui.set_has_thumbnail(image.is_some());
                ui.set_thumbnail(image.unwrap_or_default());
                dirty = true;
            }
            let mut ended = false;
            if let Some(w) = worker.borrow().as_ref() {
                while let Ok(msg) = w.messages.try_recv() {
                    dirty = true;
                    let mut s = state.borrow_mut();
                    match msg {
                        Message::Event(e) => s.apply(&e),
                        Message::Started(pid) => {
                            log.line("UI_WORKER_PID", &pid.to_string());
                        }
                        Message::Fault(code) => {
                            s.protocol_fault = true;
                            s.add("--", "WARNING", "Некорректное событие backend · см. лог");
                            log.line("IPC_WARNING", &code);
                        }
                        Message::Failed(text) => {
                            s.phase = Phase::Error;
                            s.worker_alive = false;
                            s.add("--", "ERROR", text);
                            ended = true;
                        }
                        Message::Exited {
                            code,
                            cancelled,
                            wall,
                        } => {
                            s.exited(code, cancelled);
                            ui.set_runtime_note(
                                format!(
                                    "Backend {:.2} с · процесс {:.2} с",
                                    s.backend_seconds.unwrap_or(wall),
                                    wall
                                )
                                .into(),
                            );
                            ended = true;
                            if ui.get_auto_open()
                                && matches!(s.phase, Phase::Completed | Phase::Partial)
                                && let Some(parent) =
                                    s.output_files.first().and_then(|p| p.parent())
                            {
                                open_output(parent, &log);
                            }
                        }
                    }
                }
            }
            if ended {
                *worker.borrow_mut() = None;
                if *close_pending.borrow() {
                    let _ = ui.hide();
                    let _ = slint::quit_event_loop();
                }
            }
            if !ui.get_reduced() && (state.borrow().worker_alive || frame.is_multiple_of(3)) {
                let t = epoch.elapsed().as_secs_f32();
                ui.set_motion((t / 8.0).fract());
                ui.set_breathe((t * 0.9).sin() * 0.5 + 0.5);
            }
            if frame.is_multiple_of(15) {
                state.borrow_mut().tick();
                dirty = true;
            }
            if dirty {
                render(&ui, &state.borrow(), &stages, &events);
            }
        },
    );
    if auto_start {
        let weak = ui.as_weak();
        slint::Timer::single_shot(Duration::from_millis(800), move || {
            if let Some(ui) = weak.upgrade() {
                ui.invoke_start_job();
            }
        });
    }
    ui.run()?;
    Ok(())
}
fn main() {
    if let Err(_error) = run() {
        rfd::MessageDialog::new()
            .set_title("Audio2Text")
            .set_description(
                "Приложение не запущено. Проверьте путь проекта, backend и logs/frontend_v2.log.",
            )
            .set_level(rfd::MessageLevel::Error)
            .show();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn elapsed_is_distinct_from_media_timecode() {
        assert_eq!(duration(83.2), "01:23");
        assert_eq!(duration(0.0), "00:00");
        assert_eq!(duration(3599.0), "59:59");
        assert_eq!(duration(3600.0), "01:00:00");
        assert_eq!(duration(3683.0), "01:01:23");
    }

    #[test]
    fn output_callback_targets_app_root_with_one_literal_argument() {
        let paths = paths::Paths::discover(None).unwrap();
        assert_eq!(paths.output, paths.root.join("output"));
        let command = output_command(&paths.output);
        assert_eq!(command.get_program(), "explorer.exe");
        assert_eq!(
            command.get_args().collect::<Vec<_>>(),
            vec![paths.output.as_os_str()]
        );
        // Relocation changes the command argument, never a compiled development path.
        let alternate = std::path::Path::new("E:/Audio2Text_Portable/output");
        assert_eq!(
            output_command(alternate).get_args().next().unwrap(),
            alternate
        );
    }
    #[test]
    #[ignore = "explicit OS-level output gate; opens Explorer"]
    fn output_callback_os_invocation() {
        let paths = paths::Paths::discover(None).unwrap();
        let evidence = paths.root.join("dev/validation_v205/output_os.log");
        let log = logging::Log::open(&evidence).unwrap();
        handle_output(&paths, &log);
        let content = std::fs::read_to_string(evidence).unwrap();
        assert!(content.lines().last().unwrap().contains("[OUTPUT_OPEN]"));
        assert!(
            content
                .lines()
                .last()
                .unwrap()
                .contains(paths.output.to_str().unwrap())
        );
    }
}
