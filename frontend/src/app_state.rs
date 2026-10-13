use crate::ipc::{Event, STAGES, stage_label};
use std::{
    collections::{BTreeMap, VecDeque},
    path::PathBuf,
    time::Instant,
};
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Idle,
    FileSelected,
    Starting,
    Processing,
    CancelPending,
    Partial,
    Completed,
    Error,
    Cancelled,
}
impl Phase {
    pub fn label(self) -> &'static str {
        match self {
            Self::Idle => "Выберите медиафайл",
            Self::FileSelected => "Готов к запуску",
            Self::Starting => "Запуск backend",
            Self::Processing => "Обработка",
            Self::CancelPending => "Остановка…",
            Self::Partial => "Готово · требуется проверка отдельных фрагментов",
            Self::Completed => "Готово",
            Self::Error => "Обработка завершилась с ошибкой",
            Self::Cancelled => "Обработка остановлена",
        }
    }
}
#[derive(Clone, Debug)]
pub struct Stage {
    pub id: String,
    pub state: String,
    pub done: Option<u64>,
    pub total: Option<u64>,
}
#[derive(Clone, Debug)]
pub struct Entry {
    pub time: String,
    pub level: String,
    pub text: String,
}
pub struct AppState {
    pub phase: Phase,
    pub selected: Option<PathBuf>,
    pub stages: Vec<Stage>,
    pub current_stage: String,
    pub gpu: String,
    pub cuda_available: Option<bool>,
    pub cuda_active: Option<bool>,
    pub utilization: Option<f64>,
    pub vram_used: Option<f64>,
    pub vram_total: Option<f64>,
    pub speakers: BTreeMap<String, String>,
    pub languages: Vec<String>,
    pub segments: Option<u64>,
    pub groups: Option<u64>,
    pub current_voi: String,
    pub current_language: String,
    pub preview: String,
    pub timecode: String,
    pub journal: VecDeque<Entry>,
    pub output_files: Vec<PathBuf>,
    pub started: Option<Instant>,
    pub elapsed: f64,
    pub backend_seconds: Option<f64>,
    pub eta: Option<f64>,
    pub terminal: Option<String>,
    pub protocol_fault: bool,
    pub worker_alive: bool,
    pub job_id: String,
}
impl Default for AppState {
    fn default() -> Self {
        Self {
            phase: Phase::Idle,
            selected: None,
            stages: STAGES
                .iter()
                .map(|s| Stage {
                    id: s.to_string(),
                    state: "waiting".into(),
                    done: None,
                    total: None,
                })
                .collect(),
            current_stage: String::new(),
            gpu: "--".into(),
            cuda_available: None,
            cuda_active: None,
            utilization: None,
            vram_used: None,
            vram_total: None,
            speakers: BTreeMap::new(),
            languages: vec![],
            segments: None,
            groups: None,
            current_voi: "--".into(),
            current_language: "--".into(),
            preview: String::new(),
            timecode: "--".into(),
            journal: VecDeque::new(),
            output_files: vec![],
            started: None,
            elapsed: 0.0,
            backend_seconds: None,
            eta: None,
            terminal: None,
            protocol_fault: false,
            worker_alive: false,
            job_id: String::new(),
        }
    }
}
impl AppState {
    pub fn start(&mut self) {
        let file = self.selected.clone();
        *self = Self::default();
        self.selected = file;
        self.phase = Phase::Starting;
        self.worker_alive = true;
        self.started = Some(Instant::now());
    }
    pub fn add(&mut self, time: &str, level: &str, text: impl Into<String>) {
        self.journal.push_back(Entry {
            time: time.into(),
            level: level.into(),
            text: text.into(),
        });
        while self.journal.len() > 12 {
            self.journal.pop_front();
        }
    }
    pub fn tick(&mut self) {
        if self.worker_alive {
            self.elapsed = self
                .started
                .map(|t| t.elapsed().as_secs_f64())
                .unwrap_or_default();
        }
    }
    pub fn apply(&mut self, e: &Event) {
        self.job_id = e.job_id.clone();
        let time = e.timestamp.get(11..19).unwrap_or("--");
        match e.event.as_str() {
            "app_ready" => self.add(time, "INFO", "Backend v1.5.7 готов"),
            "job_started" => {
                if self.phase != Phase::CancelPending {
                    self.phase = Phase::Processing;
                }
                self.add(time, "INFO", "Обработка началась");
            }
            "file_loaded" => self.add(time, "INFO", "Файл проверен"),
            "stage_started" | "stage_progress" | "stage_completed" => {
                let id = e.text("stage");
                if id == "semantic_grouping" && e.event == "stage_completed" {
                    self.groups = e.count("completed_units");
                }
                if let Some(stage) = self.stages.iter_mut().find(|s| s.id == id) {
                    stage.state = e.text("state").into();
                    stage.done = e.count("completed_units");
                    stage.total = e.count("total_units");
                }
                if e.text("state") == "active" {
                    self.current_stage = id.into();
                    self.eta = e.number("remaining_seconds");
                }
                if e.event == "stage_started" || e.event == "stage_completed" {
                    self.add(
                        time,
                        if e.text("state") == "failed" {
                            "ERROR"
                        } else if e.text("state") == "warning" {
                            "WARNING"
                        } else {
                            "INFO"
                        },
                        format!(
                            "{} · {}",
                            stage_label(id),
                            if e.flag("reused") == Some(true) {
                                "из кэша"
                            } else {
                                match e.text("state") {
                                    "completed" => "готово",
                                    "warning" => "проверка",
                                    "failed" => "ошибка",
                                    _ => "в работе",
                                }
                            }
                        ),
                    );
                }
            }
            "gpu_status" | "telemetry" => {
                if let Some(v) = e.fields.get("gpu_name") {
                    self.gpu = v.as_str().unwrap_or("--").into();
                }
                if e.fields.contains_key("cuda_available") {
                    self.cuda_available = e.flag("cuda_available");
                }
                if e.fields.contains_key("cuda_active") {
                    self.cuda_active = e.flag("cuda_active");
                }
                for (k, dst) in [
                    ("gpu_utilization_percent", &mut self.utilization),
                    ("vram_used_mb", &mut self.vram_used),
                    ("vram_total_mb", &mut self.vram_total),
                ] {
                    if e.fields.contains_key(k) {
                        *dst = e.number(k);
                    }
                }
            }
            "languages_updated" => {
                self.languages = e
                    .fields
                    .get("languages")
                    .and_then(|v| v.as_array())
                    .map(|a| {
                        a.iter()
                            .filter_map(|x| x.as_str().map(str::to_owned))
                            .collect()
                    })
                    .unwrap_or_default();
                self.add(
                    time,
                    "INFO",
                    format!("Языки · {}", self.languages.join(" / ")),
                );
            }
            "language_detected" => {
                let l = e.text("source_language");
                if !l.is_empty() && !self.languages.iter().any(|s| s == l) {
                    self.languages.push(l.into());
                }
            }
            "speakers_updated" => {
                self.speakers.clear();
                if let Some(a) = e.fields.get("speakers").and_then(|v| v.as_array()) {
                    for v in a {
                        if let (Some(id), Some(display)) =
                            (v["speaker_id"].as_str(), v["speaker_display"].as_str())
                        {
                            self.speakers.insert(id.into(), display.into());
                        }
                    }
                }
                self.add(
                    time,
                    "INFO",
                    format!("Голоса · {} VOI", self.speakers.len()),
                );
            }
            "segment_progress" => self.segments = e.count("segment_count"),
            "current_segment" => {
                self.current_voi = if e.text("speaker_display").is_empty() {
                    "--"
                } else {
                    e.text("speaker_display")
                }
                .into();
                self.current_language = e.text("current_source_language").into();
                self.preview = e.text("text_preview").into();
                self.timecode = e
                    .fields
                    .get("start_display")
                    .and_then(|v| v.as_str())
                    .unwrap_or("--")
                    .into();
            }
            "translation_progress" => {
                if let Some(s) = self.stages.iter_mut().find(|s| s.id == "translation") {
                    s.done = e.count("completed_units");
                    s.total = e.count("total_units");
                }
            }
            "export_started" => self.add(time, "INFO", "Сохранение TXT / JSON / DOCX"),
            "export_completed" => {
                self.groups = e.count("block_count");
                self.output_files = e
                    .fields
                    .get("files")
                    .and_then(|v| v.as_array())
                    .map(|a| {
                        a.iter()
                            .filter_map(|x| x.as_str().map(PathBuf::from))
                            .collect()
                    })
                    .unwrap_or_default();
                self.add(time, "INFO", "Результаты сохранены");
            }
            "warning" => self.add(time, "WARNING", "Результат требует проверки"),
            "error" => {
                self.phase = Phase::Error;
                self.add(time, "ERROR", "Ошибка backend · подробности в логе");
            }
            "job_completed" | "job_partial" | "job_failed" => {
                self.terminal = Some(e.event.clone());
                self.backend_seconds = e.number("wall_seconds");
                self.groups = e.count("block_count").or(self.groups);
                self.segments = e.count("segment_count").or(self.segments);
                self.cuda_active = Some(false);
                self.phase = match e.event.as_str() {
                    "job_completed" => Phase::Completed,
                    "job_partial" => Phase::Partial,
                    _ => Phase::Error,
                };
                self.add(
                    time,
                    if self.phase == Phase::Error {
                        "ERROR"
                    } else if self.phase == Phase::Partial {
                        "WARNING"
                    } else {
                        "INFO"
                    },
                    self.phase.label(),
                );
            }
            _ => {}
        }
    }
    pub fn exited(&mut self, code: u32, cancelled: bool) {
        self.tick();
        self.worker_alive = false;
        self.cuda_active = Some(false);
        if cancelled {
            self.phase = Phase::Cancelled;
        } else {
            let valid = matches!(
                (self.terminal.as_deref(), code),
                (Some("job_completed"), 0) | (Some("job_partial"), 2)
            );
            if !valid || self.protocol_fault {
                self.phase = Phase::Error;
                self.add(
                    "--",
                    "ERROR",
                    "Backend завершился без подтверждённого результата",
                );
            }
        }
    }
    pub fn ratio(&self) -> Option<f32> {
        let s = self.stages.iter().find(|s| s.id == self.current_stage)?;
        match (s.done, s.total) {
            (Some(a), Some(b)) if b > 0 => Some(a as f32 / b as f32),
            _ => None,
        }
    }
    pub fn progress_label(&self) -> String {
        let Some(s) = self.stages.iter().find(|s| s.id == self.current_stage) else {
            return "--".into();
        };
        match (s.done, s.total) {
            (Some(a), Some(b)) => format!("{a} / {b}"),
            _ => "--".into(),
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::{Decoder, fixture};
    use serde_json::json;
    fn event(name: &str, v: serde_json::Value) -> Event {
        Decoder::default().parse(&fixture(name, 1, v)).unwrap()
    }
    #[test]
    fn partial_not_error() {
        let mut s = AppState::default();
        s.apply(&event("job_partial", json!({})));
        s.exited(2, false);
        assert_eq!(s.phase, Phase::Partial);
    }
    #[test]
    fn missing_terminal_error() {
        let mut s = AppState::default();
        s.exited(0, false);
        assert_eq!(s.phase, Phase::Error);
    }
    #[test]
    fn cancel_state() {
        let mut s = AppState::default();
        s.exited(130, true);
        assert_eq!(s.phase, Phase::Cancelled);
    }
    #[test]
    fn mismatch_exit_error() {
        let mut s = AppState::default();
        s.apply(&event("job_completed", json!({})));
        s.exited(1, false);
        assert_eq!(s.phase, Phase::Error);
    }
    #[test]
    fn null_clears_telemetry() {
        let mut s = AppState {
            vram_used: Some(123.0),
            ..Default::default()
        };
        s.apply(&event("telemetry", json!({"vram_used_mb":null})));
        assert_eq!(s.vram_used, None);
    }
    #[test]
    fn voi_display() {
        let mut s = AppState::default();
        s.apply(&event("current_segment",json!({"speaker_display":"VOI 2","current_source_language":"AF","text_preview":"source"})));
        assert_eq!(s.current_voi, "VOI 2");
        assert_eq!(s.current_language, "AF");
        assert_eq!(s.timecode, "--");
    }
    #[test]
    fn real_progress() {
        let mut s = AppState::default();
        s.apply(&event(
            "stage_progress",
            json!({"stage":"asr","state":"active","completed_units":2,"total_units":4}),
        ));
        assert_eq!(s.ratio(), Some(0.5));
    }
    #[test]
    fn no_fake_progress() {
        assert_eq!(AppState::default().ratio(), None);
    }
    #[test]
    fn bounded_journal() {
        let mut s = AppState::default();
        for _ in 0..20 {
            s.add("--", "INFO", "message");
        }
        assert_eq!(s.journal.len(), 12);
    }
    #[test]
    fn reset_per_job() {
        let mut s = AppState {
            selected: Some(PathBuf::from("a.mp4")),
            gpu: "old".into(),
            ..Default::default()
        };
        s.start();
        assert_eq!(s.phase, Phase::Starting);
        assert_eq!(s.gpu, "--");
        assert!(s.selected.is_some());
    }

    #[test]
    fn completed_and_partial_remain_distinct_after_exit() {
        for (name, code, phase) in [
            ("job_completed", 0, Phase::Completed),
            ("job_partial", 2, Phase::Partial),
        ] {
            let mut state = AppState::default();
            state.start();
            state.apply(&event(name, json!({"files": [], "wall_seconds": 1.0})));
            state.exited(code, false);
            assert_eq!(state.phase, phase);
            assert!(!state.worker_alive);
        }
    }
}
