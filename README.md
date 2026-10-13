# Audio2Text — v2.0.5 source baseline

Windows Rust/Slint UI with frozen Python v1.5.7 backend: FFmpeg extraction, faster-whisper, pyannote, NLLB translation and TXT/JSON/DOCX export. Production translation remains CPU.

This is a source baseline, not a released portable distribution or a full acceptance PASS. Development/interface work is PAUSED. See docs/GIT_BASELINE_V205.md, docs/EXPC_CHECKPOINT.md and docs/EXPC_BACKLOG.md.

## Local runtime prerequisites

The existing installation uses Python 3.12.10, NVIDIA RTX 5060 / driver 616.92, torch/torchaudio 2.11.0+cu128, faster-whisper 1.2.1, ctranslate2 4.8.1, pyannote.audio 4.0.7, transformers 5.0.0, sentencepiece 0.2.1, numpy 2.4.6, librosa 0.11.0, soundfile 0.14.0, python-docx 1.2.0 and psutil 7.2.2. This inventory is not a complete dependency lock or a tested fresh-install recipe.

Provide an independently provisioned local `venv`, FFmpeg/FFprobe, authorized model downloads and `vendor/text_lid/langid` 1.1.6. Installed vendor content embeds a language model and is deliberately excluded from Git, along with all model/cache directories. HF authentication belongs in the local environment; never commit credentials. No packages/models are installed by this baseline task.

Copy `config_v157.example.json` to ignored `config_v157.json` for the current backend. Older regression tests may need corresponding v155/v156 copies. Keep private dictionary overrides and speaker roles in ignored local configuration. The included TCM dictionaries contain reviewed generic terminology mappings only.

The repository includes original UI source assets required by Slint/resource compilation (not build outputs). Build tooling requires Rust and the Windows SDK resource compiler; Cargo.lock is retained. Existing EXE is stored outside Git under artifacts/v2.0.5.

## Validation boundaries

Ordinary Cargo tests are headless. Do not run the ignored Explorer test during headless validation. Included Python tests use synthetic fixtures and the locally supplied LID dependency; `tests/.runtime` must exist. The private-fixture-dependent test_v157.py, dev evidence, test/performance experiments and generated exports remain local-only. The Git baseline therefore does not claim self-contained full-suite execution from a clean clone.

All source/config templates preserve exact bytes via `.gitattributes`; frozen source SHA256 is checked by the backend. No inference, runtime config change, source rollback or v2.0.6 production promotion is part of Git initialization.
