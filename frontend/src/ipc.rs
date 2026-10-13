use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const STAGES: [&str; 9] = [
    "prepare",
    "extract_audio",
    "diarization",
    "language_detection",
    "asr",
    "language_reconciliation",
    "semantic_grouping",
    "translation",
    "export",
];
pub const EVENTS: [&str; 22] = [
    "app_ready",
    "job_started",
    "file_loaded",
    "stage_started",
    "stage_progress",
    "stage_completed",
    "gpu_status",
    "telemetry",
    "language_detected",
    "languages_updated",
    "speaker_detected",
    "speakers_updated",
    "segment_progress",
    "current_segment",
    "translation_progress",
    "export_started",
    "export_completed",
    "warning",
    "error",
    "job_completed",
    "job_partial",
    "job_failed",
];

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Event {
    pub schema: u32,
    pub event: String,
    pub timestamp: String,
    pub job_id: String,
    pub backend_version: String,
    pub sequence: u64,
    #[serde(flatten)]
    pub fields: serde_json::Map<String, Value>,
}
impl Event {
    pub fn text(&self, key: &str) -> &str {
        self.fields.get(key).and_then(Value::as_str).unwrap_or("")
    }
    pub fn number(&self, key: &str) -> Option<f64> {
        self.fields.get(key).and_then(Value::as_f64)
    }
    pub fn count(&self, key: &str) -> Option<u64> {
        self.fields.get(key).and_then(Value::as_u64)
    }
    pub fn flag(&self, key: &str) -> Option<bool> {
        self.fields.get(key).and_then(Value::as_bool)
    }
    pub fn terminal(&self) -> bool {
        matches!(
            self.event.as_str(),
            "job_completed" | "job_partial" | "job_failed"
        )
    }
}

#[derive(Default)]
pub struct Decoder {
    job: Option<String>,
    sequence: u64,
    terminal: bool,
}
impl Decoder {
    pub fn parse(&mut self, line: &str) -> Result<Event, String> {
        if line.len() > 1_048_576 {
            return Err("event_too_large".into());
        }
        let e: Event = serde_json::from_str(line).map_err(|_| "invalid_json_or_envelope")?;
        if e.schema != 1
            || e.backend_version != "1.5.7"
            || e.job_id.is_empty()
            || !e.timestamp.ends_with('Z')
        {
            return Err("invalid_contract".into());
        }
        if !EVENTS.contains(&e.event.as_str()) {
            return Err("unknown_event".into());
        }
        if self.terminal || e.sequence != self.sequence + 1 {
            return Err("event_order".into());
        }
        if self.job.as_ref().is_some_and(|id| id != &e.job_id) {
            return Err("job_id_mismatch".into());
        }
        if let Some(stage) = e.fields.get("stage")
            && !STAGES.contains(&stage.as_str().unwrap_or(""))
        {
            return Err("unknown_stage".into());
        }
        if let Some(state) = e.fields.get("state")
            && !["waiting", "active", "completed", "warning", "failed"]
                .contains(&state.as_str().unwrap_or(""))
        {
            return Err("invalid_stage_state".into());
        }
        if e.event.starts_with("stage_")
            && !["stage", "state", "completed_units", "total_units"]
                .iter()
                .all(|k| e.fields.contains_key(*k))
        {
            return Err("incomplete_stage".into());
        }
        for key in ["completed_units", "total_units"] {
            if e.fields
                .get(key)
                .is_some_and(|v| !v.is_null() && v.as_u64().is_none())
            {
                return Err("invalid_counter".into());
            }
        }
        if matches!((e.count("completed_units"),e.count("total_units")),(Some(a),Some(b)) if a>b) {
            return Err("counter_overflow".into());
        }
        for key in ["cuda_available", "cuda_active"] {
            if e.fields
                .get(key)
                .is_some_and(|v| !v.is_null() && !v.is_boolean())
            {
                return Err("invalid_telemetry".into());
            }
        }
        for key in ["gpu_utilization_percent", "vram_used_mb", "vram_total_mb"] {
            if e.fields.get(key).is_some_and(|v| {
                !v.is_null() && v.as_f64().is_none_or(|n| n < 0.0 || !n.is_finite())
            }) {
                return Err("invalid_telemetry".into());
            }
        }
        if e.number("gpu_utilization_percent")
            .is_some_and(|n| n > 100.0)
        {
            return Err("invalid_utilization".into());
        }
        self.sequence = e.sequence;
        self.job = Some(e.job_id.clone());
        self.terminal = e.terminal();
        Ok(e)
    }
}

pub fn stage_label(id: &str) -> &str {
    match id {
        "prepare" => "Подготовка",
        "extract_audio" => "Извлечение аудио",
        "diarization" => "Разделение голосов",
        "language_detection" => "Определение языка",
        "asr" => "Распознавание речи",
        "language_reconciliation" => "Уточнение языка",
        "semantic_grouping" => "Смысловые фрагменты",
        "translation" => "Перевод · RU / EN",
        "export" => "Сохранение результатов",
        _ => "Ожидание",
    }
}

#[cfg(test)]
pub fn fixture(name: &str, sequence: u64, payload: Value) -> String {
    let mut v = serde_json::json!({"schema":1,"event":name,"timestamp":"2026-10-08T12:00:00.000Z","job_id":"test-job","backend_version":"1.5.7","sequence":sequence});
    v.as_object_mut()
        .unwrap()
        .extend(payload.as_object().unwrap().clone());
    v.to_string()
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn valid_event() {
        assert!(
            Decoder::default()
                .parse(&fixture("app_ready", 1, json!({})))
                .is_ok()
        );
    }
    #[test]
    fn invalid_json() {
        assert!(Decoder::default().parse("traceback").is_err());
    }
    #[test]
    fn unknown_event() {
        assert!(
            Decoder::default()
                .parse(&fixture("fake", 1, json!({})))
                .is_err()
        );
    }
    #[test]
    fn wrong_schema() {
        assert!(
            Decoder::default()
                .parse(&fixture("app_ready", 1, json!({"schema":2})))
                .is_err()
        );
    }
    #[test]
    fn job_mismatch() {
        let mut d = Decoder::default();
        d.parse(&fixture("app_ready", 1, json!({}))).unwrap();
        assert!(
            d.parse(&fixture("job_started", 2, json!({"job_id":"other"})))
                .is_err()
        );
    }
    #[test]
    fn terminal_is_final() {
        let mut d = Decoder::default();
        d.parse(&fixture("job_partial", 1, json!({}))).unwrap();
        assert!(d.parse(&fixture("warning", 2, json!({}))).is_err());
    }
    #[test]
    fn counters_validated() {
        assert!(
            Decoder::default()
                .parse(&fixture(
                    "stage_progress",
                    1,
                    json!({"stage":"asr","state":"active","completed_units":3,"total_units":2})
                ))
                .is_err()
        );
    }
    #[test]
    fn stage_enum() {
        assert!(Decoder::default().parse(&fixture("stage_progress",1,json!({"stage":"imaginary","state":"active","completed_units":0,"total_units":null}))).is_err());
    }
    #[test]
    fn state_enum() {
        assert!(
            Decoder::default()
                .parse(&fixture(
                    "stage_progress",
                    1,
                    json!({"stage":"asr","state":"fake","completed_units":0,"total_units":null})
                ))
                .is_err()
        );
    }
    #[test]
    fn null_telemetry_valid() {
        assert!(
            Decoder::default()
                .parse(&fixture(
                    "telemetry",
                    1,
                    json!({"cuda_available":null,"vram_used_mb":null})
                ))
                .is_ok()
        );
    }
}
