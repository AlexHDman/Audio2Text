//! Optional, bounded media inspection; never participates in processing/cache identity.
use std::os::windows::process::CommandExt;
use std::{
    io,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

#[derive(Default)]
pub struct Preview {
    pub duration: Option<f64>,
    pub image: Option<PathBuf>,
    pub video: bool,
}

fn tool(root: &Path, name: &str) -> PathBuf {
    let bundled = root.join("_internal/ffmpeg").join(format!("{name}.exe"));
    if bundled.is_file() {
        bundled
    } else {
        PathBuf::from(format!("{name}.exe"))
    }
}

fn bounded(command: &mut Command, seconds: u64) -> io::Result<Vec<u8>> {
    let mut child = command
        .creation_flags(0x08000000)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let start = Instant::now();
    loop {
        if child.try_wait()?.is_some() {
            let result = child.wait_with_output()?;
            return if result.status.success() {
                Ok(result.stdout)
            } else {
                Err(io::Error::other("media_probe_failed"))
            };
        }
        if start.elapsed() > Duration::from_secs(seconds) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "media_probe_timeout",
            ));
        }
        thread::sleep(Duration::from_millis(50));
    }
}

pub fn inspect(root: &Path, source: &Path, generation: u64) -> Preview {
    let mut result = Preview::default();
    let probe = bounded(
        Command::new(tool(root, "ffprobe"))
            .args([
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type:stream_disposition=attached_pic",
                "-of",
                "json",
            ])
            .arg(source),
        10,
    );
    if let Ok(bytes) = probe
        && let Ok(value) = serde_json::from_slice::<serde_json::Value>(&bytes)
    {
        result.duration = value["format"]["duration"]
            .as_str()
            .and_then(|s| s.parse::<f64>().ok())
            .filter(|n| n.is_finite() && *n >= 0.0);
        result.video = value["streams"].as_array().is_some_and(|a| {
            a.iter().any(|s| {
                s["codec_type"] == "video" && s["disposition"]["attached_pic"].as_u64() != Some(1)
            })
        });
    } else {
        result.video = source
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|s| {
                ["mp4", "mkv", "avi", "mov", "webm"].contains(&s.to_ascii_lowercase().as_str())
            });
    }
    if !result.video {
        return result;
    }
    let dir = root.join("logs/previews");
    if std::fs::create_dir_all(&dir).is_err() {
        return result;
    }
    let file = dir.join(format!("{}-{generation}.png", std::process::id()));
    let seek = result
        .duration
        .map(|n| (n * 0.1).min(5.0))
        .unwrap_or(0.0)
        .to_string();
    if bounded(
        Command::new(tool(root, "ffmpeg"))
            .args(["-v", "error", "-nostdin", "-y", "-ss"])
            .arg(seek)
            .arg("-i")
            .arg(source)
            .args([
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-vf",
                "scale=320:180:force_original_aspect_ratio=decrease",
                "-threads",
                "1",
            ])
            .arg(&file),
        15,
    )
    .is_ok()
        && file.is_file()
    {
        result.image = Some(file);
    }
    result
}
