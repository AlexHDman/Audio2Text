# Restore Audio2Text CUDA PRO from GitHub

Updated 2026-11-12. Source backup: `feature/backend-quality`. DEVELOPMENT: PAUSED.
Stable alternative: `release/v2.0.5-baseline` at
`703dd5b52af8599a9fa17716ffee27967b424401`. The feature branch contains BE-001
candidate fixes, not an accepted release: meaning review remains open and the
measured ASR+translation pair was 23.78% slower. UI is unchanged v2.0.5;
frozen entrypoint is v1.5.7. Production translation stays on CPU.

## 1. Restore sources to a NEW directory

PowerShell, Windows x64. Never delete/reset an existing checkout or a backup.

```powershell
git clone --single-branch --branch feature/backend-quality https://github.com/AlexHDman/Audio2Text.git Audio2Text-Restored
Set-Location Audio2Text-Restored
git status --short
git rev-parse HEAD
git remote -v
```

Record the verified commit SHA from the backup receipt. A branch may advance;
for exact recovery compare HEAD with that SHA. `.gitattributes` preserves frozen
source bytes. Do not run formatting/newline conversion over frozen Python files.
Use a separate clone of `release/v2.0.5-baseline` if the stable baseline is needed;
do not remove `backend_quality.py` ad hoc to simulate that baseline.

## 2. Provision development tools and Python

Observed working toolchain: CPython **3.12.10 x64**, Rust **1.99.1** MSVC x64,
Visual Studio 2022 Build Tools (C++ workload, Windows SDK `rc.exe`), VC++ x64
runtime. Cargo.lock pins Rust dependencies including Slint 1.18.1. Install tools
from their official distributors; no installers or dependency binaries are in Git.
Use a Developer PowerShell for VS for Rust builds. Keep Python patch/architecture
matching the inventory for the first reconstruction.

In the NEW clone only:

```powershell
py -3.12 -m venv venv
& .\venv\Scripts\python.exe --version
& .\venv\Scripts\python.exe -m pip install --no-deps --index-url https://download.pytorch.org/whl/cu128 -r requirements-torch-cu128.txt
& .\venv\Scripts\python.exe -m pip install --no-deps --index-url https://pypi.org/simple -r requirements-runtime-win-py312.txt
& .\venv\Scripts\python.exe -m pip install --no-deps --index-url https://pypi.org/simple --target vendor/text_lid langid==1.1.6
& .\venv\Scripts\python.exe -m pip check
```

The two files record **114 installed runtime packages**, not wheel hashes or a
freshly resolver-validated lock. `--no-deps` deliberately recreates the observed
set rather than upgrading it through transitive resolution. Vendored langid is
separate. The working environment lacks the declared `torchcodec` dependency;
FFmpeg/waveform input works in previous local tests. `pip check` may therefore
report this known mismatch. Record any mismatch, and do not label dependency
resolution PASS or blindly install/upgrade packages to silence it. Wheel
availability, clean installation and a fresh-machine full pipeline remain
unverified. Never change the working production venv during reconstruction.

## 3. FFmpeg and CUDA

Supply `ffmpeg.exe` and `ffprobe.exe` on PATH; observed build is Gyan FFmpeg 9.0.2.
Verify `ffmpeg -version`, `ffprobe -version`. The inspected full build is GPL;
do not redistribute it without satisfying the separate binary/source license
gate in DEPENDENCY_LICENSES.md. No FFmpeg binaries are in this backup.

The working host uses RTX 5060 and NVIDIA driver 616.92 with Torch/torchaudio
2.11.0+cu128 and CTranslate2 4.8.1. A compatible NVIDIA driver and native CUDA/
cuDNN dependencies must be available to the chosen wheels. These observations
are not a minimum-driver certification. Check `nvidia-smi` and imports in the
new environment; a Torch CUDA probe alone does not validate faster-whisper CUDA.
Never copy GPU drivers from the old checkout or silently change NLLB to CUDA.

## 4. Restore model cache separately

Weights are deliberately absent. Exact six revisions are recorded in
`scripts/model_revisions.json`. Review model cards and accept gated pyannote
conditions under your own account. NLLB weights have noncommercial restrictions;
no own-code LICENSE has been selected. See DEPENDENCY_LICENSES.md.

In a NEW dedicated cache, after accepting those terms and authenticating locally:

```powershell
$env:HF_HOME = Join-Path $PWD 'models/huggingface'
& .\venv\Scripts\hf.exe auth login
& .\venv\Scripts\python.exe scripts/download_models.py --cache-dir (Join-Path $env:HF_HOME 'hub') --accepted-model-terms
```

Never put tokens in scripts, configs, Git, screenshots or shell command arguments.
Re-establish `HF_HOME` in each process/session used to launch the application.
The helper writes `refs/main` for the pinned snapshots, required by offline
transitive loading, and refuses conflicting existing refs. It does not infer.
It has fixture validation only; network downloads were not repeated for this backup.

Required payloads include Whisper model.bin/tokenizer/config, NLLB weights and
tokenizer, pyannote 3.1 config, segmentation and speaker embedding weights.
Installed pyannote 4.0.7 also needs community-1 PLDA files (`plda/plda.npz` and
`plda/xvec_transform.npz`), even with the frozen 3.1 configuration. Preserve
the original model configs. Verify downloads before enabling offline mode.

## 5. Local configuration, dictionaries and working folders

```powershell
foreach ($version in '155','156','157') {
    $destination = "config_v$version.json"
    if (-not (Test-Path -LiteralPath $destination)) {
        Copy-Item -LiteralPath "config_v$version.example.json" -Destination $destination
    }
}
foreach ($folder in 'input','output','cache','logs','temp','tests/.runtime') {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}
```

Examples are safe defaults, not the user's private runtime configuration. Keep
`TRANSLATION_DEVICE=cpu`. Generic TCM dictionaries and BE-001 protected terminology
are included. Configure optional DICTIONARY_FILES and speaker roles locally if
required; personal dictionaries/roles, source media and previous outputs must be
restored separately from an owner-controlled backup. They cannot be recovered
from GitHub. Backend cache identity includes paths/settings; do not assume old
caches remain reusable after relocation. Never merge unrelated resume files.

## 6. Tests and build

```powershell
& .\venv\Scripts\python.exe -B scripts/test_public.py
cargo fmt --manifest-path frontend/Cargo.toml -- --check
cargo clippy --locked --manifest-path frontend/Cargo.toml --all-targets -- -D warnings
cargo test --locked --manifest-path frontend/Cargo.toml
& .\scripts\build_frontend.ps1
```

The public runner selects only synthetic publishable tests. Private v1.5.7
media/resume fixtures and v2.0.6 performance experiments are deliberately absent;
the historical 226-local-test count must not be claimed for this clone. Hardlink
tests require normal filesystem permission; do not weaken tests or change ACLs.
The pre-UX core preservation test uses the included AST-only historical fixture;
it no longer requires a private backups directory.
Rust's Explorer-opening test remains ignored. The existing development venv
must exist before Rust path-discovery tests. No test above requires inference.
`-Offline` works for the build helper only if Cargo dependencies are already cached.

Result: `frontend/target/release/Audio2Text.exe`. It locates the clone through
its ancestor directories and uses `venv/Scripts/python.exe` plus the backend.
After a separately authorized GUI/inference test, the EXE may be started directly;
BAT is not required. Keep it inside the checkout or use the supported `--app-root`
argument. The helper does not overwrite an existing packaged EXE or launch a GUI.

## 7. Recovery acceptance boundaries

Source recovery requires matching commit/tree, passing the public suite and frozen
hashes, and a successful locked Rust build. Full runtime recovery additionally
requires a newly provisioned environment/model cache and an authorized real cold
ASR/diarization/NLLB job with TXT/JSON/DOCX, followed by zero-inference resume.
Those last steps are NOT RUN as part of this Git-only backup.

Portable distributions and one-off local packaging/evidence scripts are excluded.
This guide rebuilds the development application, not a byte-identical portable ZIP.
Portable payloads, old caches, private media/results, credentials, v2.0.6 experiments
and the original private-history ref remain local. Neither the project directory
nor the separate backup directory is deleted or cleaned by this procedure.

See GITHUB_BACKUP_AUDIT.md for the actual backup/clone verification evidence.
