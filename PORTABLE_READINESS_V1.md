# PORTABLE_READINESS_V1 — Audio2Text 2.0.5

Status: **PARTIAL — packaging and another-drive acceptance are not performed.**
Target: E:\Audio2Text_Portable. No runtime/model copies or final giant package were created.

## Verified audit

| Item | Classification | Evidence / remaining work |
|---|---|---|
| Rust APP_ROOT | READY | paths.rs discovers executable ancestors or explicit --app-root. Python/backend/output/log paths are rooted there; output command receives one literal APP_ROOT/output argument. Relocation command assertion passes. |
| Hardcoded development paths | READY for current source | Scan of production Python/config/BAT/Rust found no C:\AI production literal. E:/Audio2Text_Portable/output occurs only in a Rust test. Old documentation/evidence and venv metadata retain historical paths and are not portable runtime config. |
| Python executable | BLOCKER | Dev uses venv/Scripts/python.exe. pyvenv.cfg points to %LOCALAPPDATA%\Programs\Python\Python312 (3.12.10); sys.base_prefix confirms it. Bundle a self-contained compatible interpreter at _internal/runtime/python.exe. |
| venv | BLOCKER | Cannot treat the existing venv as a relocatable runtime. Reproduce installed pinned packages/native dependencies in the staged interpreter and test imports offline. |
| Backend/code/config | READY path contract | Frontend selects _internal/app/audio_pipeline_cuda_v157.py. AppPaths selects _internal/config/config_v157.json. Include frozen engines, adapter, language policy, old v155 module required by stage reuse, vendor/text_lid, dictionaries and cache_manager_v205.py. |
| FFmpeg / FFprobe | BLOCKER | Neither is discoverable in the current tool-process PATH; _internal does not exist. Frontend preview supports _internal/ffmpeg/{ffmpeg,ffprobe}.exe; backend prepends the same directory. Bundle both and verify versions/licensing. This is a current process observation, not proof they are absent from the entire machine. |
| Whisper/NLLB/pyannote models | BLOCKER | Current checksum-valid resume metadata refers to %USERPROFILE%\.cache\huggingface\hub snapshots; config overrides are null. Project models contains OpenVINO experiment directories, not proof of the accepted CUDA model package. |
| Hugging Face external cache | NEEDS CHANGE | Adapter supports _internal/models/huggingface and HF_HOME/HF_HUB_CACHE. Include required snapshots plus blobs/refs or materialize consistent local paths. Test with external cache unavailable and network offline. No tokens belong in the package. |
| Required model snapshots | NEEDS CHANGE | faster-whisper-large-v3 edaa852e…, NLLB f8d333a0…, speaker-diarization-3.1 84fd2591…, segmentation-3.0 e66f3d3b…, wespeaker 837717dd… from current cache metadata. Presence/completeness in a new package remains unverified. |
| LID vendor files | BLOCKER in current validation environment | vendor/text_lid/langid cannot be read (EPERM / WinError 5). This blocks 22 tests and causes three translation-test failures. Checkpoint baseline reproduces the same issue. Do not replace the model or weaken tests. |
| Job cache | NEEDS CHANGE in package config | New service understands temp/v157 and cache/jobs. Production config unchanged. Frozen portable default _internal/temp/v157 conflicts with desired final layout: supply TEMP=cache/jobs in copied package config. |
| System cache / temp | NEEDS CHANGE | Keep cache/system protected. Inspect existing runtime redirection (matplotlib/numba) before choosing final cache/system/temp destinations; do not put arbitrary runtime folders inside user-removable jobs. |
| Output/input/logs/assets | READY path interfaces | output, input and logs relative to root; no automatic movement. Slint source assets are embedded by the release build. Existing assets/layout preserved. |
| Native DLLs | NEEDS CHANGE | Installed torch/lib contains torch_cpu/torch_cuda, c10/c10_cuda, CUDA 12/cuBLAS/cuDNN 9, cuFFT/cuSPARSE/cuSOLVER, NVRTC, OpenMP, uv and zlib DLLs. ctranslate2 includes ctranslate2.dll, cudnn64_9.dll, libiomp5md.dll and cp312-win_amd64 extension. Transitive PE dependency closure and VC/UCRT availability must be checked in the staged runtime. |
| GPU driver / device | BLOCKER for GPU acceptance now | nvidia-smi returns “Failed to initialize NVML: Unknown Error”. Driver is host-installed, never a portable model-cache artifact. No CUDA benchmark PASS is available. |
| E: launch / offline cold run / physical GUI | BLOCKER acceptance gate | NOT TESTED. Building a frontend EXE on C: does not prove portable acceptance. |

Source evidence: dev/validation_v205/portable_path_scan.json, paths.rs, media.rs, backend_contract_v1.py, backend_runtime_v157.py, pyvenv.cfg, current resume metadata and runtime probe. Model locations above are current cache metadata, not a fresh rehash of multi-GB external model files.

## Exact next build sequence (future phase)

1. Restore a readable validation environment: langid vendor access, FFmpeg discovery/bundling and working GPU telemetry. Re-run all 186 Python tests and Rust/Clippy before packaging.
2. Create a new empty staging root for E:\Audio2Text_Portable. Keep existing source, caches, output and accepted evidence unchanged.
3. Stage the already-built frontend EXE plus frozen Python files, adapters, cache service, vendor LID and dictionaries under _internal/app. Write a source SHA256 manifest.
4. Assemble a self-contained Python 3.12-compatible runtime under _internal/runtime from pinned dependencies. Verify imports and transitive DLL resolution with the system Python/venv unavailable.
5. Stage FFmpeg/FFprobe under _internal/ffmpeg. Stage only the accepted Whisper/NLLB/pyannote snapshots and dependencies under _internal/models; preserve licenses and hash manifests. No unnecessary duplicate model trees.
6. Write copied _internal/config/config_v157.json with INPUT=input, OUTPUT=output, TEMP=cache/jobs and package-local model paths/cache redirection. Keep production TRANSLATION_DEVICE=cpu. Create cache/system, temp and logs separately. Do not migrate old jobs.
7. Copy the staged package to E: and launch with an unrelated working directory, network disabled and external Hugging Face cache unavailable. Verify picker, preview, output action, all dependencies, cold run, zero-inference resume, cancellation/close and synthetic cache cleanup.
8. Compare source/ASR/structural/export quality against accepted evidence, validate frozen hashes and capture actual UI evidence. Only after true portable PASS plan KEEP/MOVE/ARCHIVE/DELETE. No old versions/backups/data cleanup before that gate.
