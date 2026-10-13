use std::{
    fs::{File, OpenOptions},
    io::Write,
    path::Path,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};
#[derive(Clone)]
pub struct Log(Arc<Mutex<File>>);
impl Log {
    pub fn open(path: &Path) -> std::io::Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        Ok(Self(Arc::new(Mutex::new(
            OpenOptions::new().create(true).append(true).open(path)?,
        ))))
    }
    pub fn line(&self, kind: &str, text: &str) {
        if let Ok(mut f) = self.0.lock() {
            let time = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis();
            let _ = writeln!(f, "{time} [{kind}] {}", redact(text));
            let _ = f.flush();
        }
    }
}
pub fn redact(text: &str) -> String {
    let lower = text.to_ascii_lowercase();
    if ["authorization", "password", "token=", "token:"]
        .iter()
        .any(|marker| lower.contains(marker))
    {
        return "[REDACTED credential-bearing diagnostic]".into();
    }
    text.split_whitespace()
        .map(|w| {
            let l = w.to_ascii_lowercase();
            if ["hf_", "sk-", "ghp_", "token=", "authorization", "password="]
                .iter()
                .any(|x| l.contains(x))
            {
                "[REDACTED]"
            } else {
                w
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn credential_mask() {
        assert!(!redact("x hf_exampleSECRET token=secret").contains("SECRET"));
        assert!(!redact("Authorization: Bearer secret-value").contains("secret-value"));
    }
}
