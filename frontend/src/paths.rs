use std::{
    io,
    path::{Path, PathBuf},
};
pub const EXTENSIONS: [&str; 12] = [
    "mp3", "wav", "flac", "aac", "m4a", "ogg", "opus", "mp4", "mkv", "avi", "mov", "webm",
];
// std canonicalize adds a verbatim prefix on Windows. Python includes that spelling
// in source identity, so retain its ordinary absolute spelling at the IPC boundary.
pub fn canonical(path: &Path) -> io::Result<PathBuf> {
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    let p = path.canonicalize()?;
    let wide: Vec<u16> = p.as_os_str().encode_wide().collect();
    let prefix: Vec<u16> = "\\\\?\\".encode_utf16().collect();
    if wide.starts_with(&prefix) {
        let unc: Vec<u16> = "UNC\\".encode_utf16().collect();
        let tail = &wide[4..];
        let normalized = if tail.starts_with(&unc) {
            [vec![92, 92], tail[4..].to_vec()].concat()
        } else {
            tail.to_vec()
        };
        return Ok(std::ffi::OsString::from_wide(&normalized).into());
    }
    Ok(p)
}
#[derive(Clone, Debug)]
pub struct Paths {
    pub root: PathBuf,
    pub python: PathBuf,
    pub backend: PathBuf,
    pub output: PathBuf,
    pub logs: PathBuf,
}
impl Paths {
    pub fn from_root(root: &Path) -> io::Result<Self> {
        let root = canonical(root)?;
        let python = if root.join("_internal/runtime/python.exe").is_file() {
            root.join("_internal/runtime/python.exe")
        } else {
            root.join("venv/Scripts/python.exe")
        };
        let backend = if root
            .join("_internal/app/audio_pipeline_cuda_v157.py")
            .is_file()
        {
            root.join("_internal/app/audio_pipeline_cuda_v157.py")
        } else {
            root.join("audio_pipeline_cuda_v157.py")
        };
        if !python.is_file() || !backend.is_file() {
            return Err(io::Error::new(io::ErrorKind::NotFound, "backend_missing"));
        }
        Ok(Self {
            output: root.join("output"),
            logs: root.join("logs"),
            python,
            backend,
            root,
        })
    }
    pub fn discover(explicit: Option<PathBuf>) -> io::Result<Self> {
        if let Some(root) = explicit {
            return Self::from_root(&root);
        }
        for p in std::env::current_exe()?.ancestors().skip(1) {
            if let Ok(paths) = Self::from_root(p) {
                return Ok(paths);
            }
        }
        Err(io::Error::new(io::ErrorKind::NotFound, "app_root_missing"))
    }
    pub fn supported(file: &Path) -> bool {
        file.is_file()
            && file
                .extension()
                .and_then(|s| s.to_str())
                .is_some_and(|s| EXTENSIONS.contains(&s.to_ascii_lowercase().as_str()))
    }
    pub fn prepare_input(&self, file: &Path) -> io::Result<PathBuf> {
        let source = canonical(file)?;
        if source.starts_with(&self.root) {
            return Ok(source);
        }
        let dir = self.root.join("input");
        std::fs::create_dir_all(&dir)?;
        let name = source
            .file_name()
            .ok_or_else(|| io::Error::other("invalid_filename"))?;
        let mut target = dir.join(name);
        if target.exists() {
            let id = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            target = dir.join(format!("import-{id}-{}", name.to_string_lossy()));
        }
        let mut input = std::fs::File::open(source)?;
        let mut output = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)?;
        std::io::copy(&mut input, &mut output)?;
        output.sync_all()?;
        Ok(target)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn executable_ancestors_find_project() {
        let p = Paths::discover(None).unwrap();
        assert!(p.backend.ends_with("audio_pipeline_cuda_v157.py"));
    }
    #[test]
    fn unsupported_missing_file() {
        assert!(!Paths::supported(Path::new("not-a-file.mp4")));
    }
    #[test]
    fn existing_input_not_copied() {
        let p = Paths::discover(None).unwrap();
        let id = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = p.root.join(format!(
            "tests/.runtime/input-path-{}-{id}",
            std::process::id()
        ));
        std::fs::create_dir_all(dir.parent().unwrap()).unwrap();
        std::fs::create_dir(&dir).unwrap();
        let f = dir.join("sample.mp4");
        std::fs::File::create_new(&f).unwrap();
        assert_eq!(p.prepare_input(&f).unwrap(), canonical(&f).unwrap());
        assert!(
            !p.prepare_input(&f)
                .unwrap()
                .to_string_lossy()
                .starts_with("\\\\?\\")
        );
        std::fs::remove_file(&f).unwrap();
        std::fs::remove_dir(&dir).unwrap();
    }
}
