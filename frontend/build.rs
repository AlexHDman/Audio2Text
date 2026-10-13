fn main() {
    slint_build::compile("ui/main.slint").expect("Slint UI compilation failed");
    // Embed the original app icon using the installed Windows SDK, no new crate.
    println!("cargo:rerun-if-changed=assets/audio2text.rc");
    println!("cargo:rerun-if-changed=assets/brand/head.ico");
    println!("cargo:rerun-if-env-changed=RC");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let rc = std::env::var_os("RC")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| {
                let kits = std::path::PathBuf::from(
                    std::env::var_os("ProgramFiles(x86)")
                        .expect("Windows SDK location unavailable"),
                )
                .join("Windows Kits/10/bin");
                let mut candidates: Vec<_> = std::fs::read_dir(kits)
                    .expect("Install Windows SDK or set RC")
                    .filter_map(Result::ok)
                    .map(|e| e.path().join("x64/rc.exe"))
                    .filter(|p| p.is_file())
                    .collect();
                candidates.sort();
                candidates
                    .pop()
                    .expect("Windows SDK rc.exe unavailable; set RC")
            });
        let res =
            std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("audio2text.res");
        let status = std::process::Command::new(rc)
            .current_dir("assets")
            .arg("/nologo")
            .arg("/fo")
            .arg(&res)
            .arg("audio2text.rc")
            .status()
            .expect("Could not run Windows resource compiler");
        assert!(status.success(), "App icon resource compilation failed");
        println!("cargo:rustc-link-arg-bin=Audio2Text={}", res.display());
    }
}
