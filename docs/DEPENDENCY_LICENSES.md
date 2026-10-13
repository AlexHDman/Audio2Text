# Dependency license audit — v2.0.5 source publication

Reviewed 2026-10-13. Scope: published project source/assets, Windows Rust dependency declarations, direct installed Python runtime packages and named external models. No third-party library source, library binary, FFmpeg build, model weight or vendored LID model is shipped in this Git tree. This is not clearance for a portable binary or commercial model use.

## Project license and artwork

The owner explicitly deferred the project license decision. No LICENSE file is created and no MIT/GPL/other project license is implied. Dependency terms do not automatically license the project's own code. Artwork consists of the existing project logo, project icons and approved generated head/forest assets according to local asset records; image inspection found no client media or identifying metadata. This records provenance evidence, not a guarantee of exclusive rights.

## Rust / Windows

`cargo metadata --offline --locked --filter-platform x86_64-pc-windows-msvc` resolved **323 third-party packages**, all with license declarations. The [inventory](DEPENDENCY_LICENSES_WINDOWS.json) records name, version, declared license expression and upstream repository. Absolute local paths have been removed. Additional optional/non-Windows Cargo.lock packages are outside this Windows resolution audit. This is declaration evidence, not a packaged-notice bundle.

Direct dependencies: Slint/slint-build 1.18.1 (three-way expression below), rfd 0.17.2 (MIT), serde 1.0.229, serde_json 1.0.151 and windows-sys 0.61.2 (MIT OR Apache-2.0).

Slint packages declare `GPL-3.0-only OR LicenseRef-Slint-Royalty-free-2.0 OR LicenseRef-Slint-Software-3.0`. Its Royalty-Free desktop/mobile/web option requires attribution via AboutSlint or the official badge on a public webpage. Other options have their own conditions. Confirm the route and attribution/notice obligations before binary distribution; this audit does not choose GPL for Audio2Text. [Official Slint terms](https://slint.dev/terms-and-conditions).

Other expressions include MIT, Apache-2.0, BSD-2-Clause/BSD-3-Clause, ISC, Unicode-3.0, Zlib, BSL-1.0, CC0-1.0 and Unlicense combinations. Preserve applicable notices/license texts when distributing those components. No dependency code is copied into this repository.

## Python / direct observed runtime

Evidence: installed distribution metadata and available installed LICENSE files; missing direct metadata was checked against upstream licenses. This is not the complete native/transitive Python dependency closure.

| Package | Observed version | License evidence |
|---|---|---|
| torch | 2.11.0+cu128 | BSD-3-Clause |
| torchaudio | 2.11.0+cu128 | BSD-2-Clause, installed license text |
| faster-whisper | 1.2.1 | MIT |
| ctranslate2 | 4.8.1 | MIT |
| pyannote.audio | 4.0.7 | MIT, installed license text |
| transformers | 5.0.0 | Apache-2.0 |
| sentencepiece | 0.2.1 | [Apache-2.0, upstream license](https://github.com/google/sentencepiece/blob/master/LICENSE) |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| librosa | 0.11.0 | ISC |
| soundfile | 0.14.0 | BSD-3-Clause for Python package; native libsndfile needs separate review |
| python-docx | 1.2.0 | MIT |
| psutil | 7.2.2 | BSD-3-Clause |
| huggingface-hub | 1.22.0 | Apache-2.0 |
| safetensors | 0.7.0 | Apache-2.0 |
| accelerate | 1.14.0 | Apache-2.0 |

Vendored langid 1.1.6 and its embedded language model are excluded. Preserve its [upstream license](https://github.com/saffsd/langid.py/blob/master/LICENSE) and inspect the exact vendored payload before future distribution.

## Models and external tools

- **NLLB-200-distilled-600M:** CC-BY-NC-4.0. Do not describe the weights as unrestricted or commercially cleared. The card also identifies research use and limitations for document/domain-specific translation. No weights are included. [Model card](https://huggingface.co/facebook/nllb-200-distilled-600M).
- **faster-whisper-large-v3:** the converted model card declares MIT; weights are excluded. [Model card](https://huggingface.co/Systran/faster-whisper-large-v3).
- **pyannote/speaker-diarization-3.1:** MIT declaration plus gated access conditions, including its required segmentation model. No authentication data/models are included. Each user must satisfy applicable access terms. [Model card and requirements](https://huggingface.co/pyannote/speaker-diarization-3.1).
- **FFmpeg/FFprobe:** licensing depends on build configuration: LGPL by default, GPL components can change the terms, and nonfree builds can restrict redistribution. The actual binary is excluded; audit its configuration and complete obligations before packaging. [Official FFmpeg legal page](https://ffmpeg.org/legal.html).
- Python interpreter, CUDA/cuDNN and other native libraries are externally supplied. Exact redistribution closure and notices remain a future packaging gate.

## Decision

No dependency-payload publication blocker was identified in this source-only tree. Project LICENSE remains **DEFERRED by owner**. Binary/portable redistribution and commercial-model clearance remain **NOT APPROVED / NOT VALIDATED**. No release/tag is created.
