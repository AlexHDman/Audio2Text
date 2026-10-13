# VALIDATION_V205_NIGHTLY

STATUS: **PARTIAL**
VERSION: **2.0.5**
DESIGNATION: **STABILITY / CACHE MANAGER / PERFORMANCE EXPERIMENT / PORTABLE PREP**

Project: C:\AI\Audio2Text. Task date: 2026-10-13 supplied session context; raw tool logs retain host timestamps.
No commit, push, tag, release or real-job cleanup.

## Delivered

- Source-only rollback checkpoint: backups/v204_before_v205_nightly, 93 files; SHA256SUMS.txt and FROZEN_BACKEND_SHA256SUMS.txt. No venv/models/media/results/binaries copied into the checkpoint. Final verification: zero checkpoint/frozen mismatches.
- Fixed test_v156.V156Tests.test_cache_reuses_accepted_asr using a minimal checksum-valid synthetic v155 predecessor. Verifies exact units/diarization/segments, unchanged predecessor bytes, translation invalidation preserving previous text, provenance and rejection of changed ASR configuration/corruption. No historical resume.json fixture or real-cache dependency.
- Cache service + Rust/Slint modal, grouping source variants, selection/count/size, explicit confirmations and bounded cleanup. Details: CACHE_MANAGER_V1.md.
- Existing isolated performance harness hardened; no inference experiment ran because preflight rejected unavailable NVIDIA telemetry.
- Portable dependency/path audit: PORTABLE_READINESS_V1.md.
- Frontend release build: artifacts/v2.0.5/Audio2Text.exe, 20,483,584 bytes.
  SHA256: 0c873d19a1edd4b4c4262e3d9848cdb2972710b03924c4f82d416df7bf619a65.

## V204 LIVE gate / output / terminal states

**V204 LIVE GATE: PARTIAL.**
Computer Use app launch returned “Computer Use app approval timed out”. No app screenshot or actual output-button click was captured. No visual PASS is claimed.

**OUTPUT BUTTON: PASS programmatic / LIVE visual pending.**
The callback calls the shared handle_output handler. Its command is explorer.exe with one literal APP_ROOT/output argument. The ordinary test checks argument/root resolution, including a relocated E: path; the explicitly run OS test invoked that same handler:
Explorer PID 46320, path C:\AI\Audio2Text\output.
Evidence: output_gate.log and output_os.log. This proves the OS spawn request, not successful visual navigation or actual UI clicking; subsequent window inventory did not confirm an output window.

Completed and partial states remain distinct after corresponding process exit; missing/mismatched terminals still become errors. Lower Slint processing/telemetry/journal panel source is byte-identical to checkpoint. Header/cache modal only; assets and animation code unchanged.

## Tests and checks

| Check | Result |
|---|---|
| Rust normal suite | 34 PASS / 0 FAIL; one explicit OS test excluded from ordinary runs |
| Rust explicit output OS test | 1 PASS / 0 FAIL; combined unique tests **35 PASS / 0 FAIL** |
| Cache safety | **17 PASS / 0 FAIL**, synthetic temporary fixtures only |
| Performance harness safety | **6 PASS / 0 FAIL**, fake subprocesses; no hardware performance claim |
| Fixed reuse fixture | PASS; additionally verified in full suite |
| Python full suite | **186 discovered; 164 executed; 161 PASS / 3 FAIL; 22 blocked by one setUpClass error** |
| Checkpoint Python baseline under same current runtime | 163 discovered; 141 executed; 137 PASS / 4 FAIL; same 22 blocked |
| Rust cargo fmt --check | PASS |
| Rust Clippy --all-targets -- -D warnings | PASS |
| Rust release build | PASS |
| Changed Python source compile | PASS, all six changed/new Python sources |
| Python Ruff / pytest availability | BLOCKED: no modules installed in venv; Ruff not in PATH. Existing unittest tests were run with unittest discovery, not skipped. |
| git diff | No .git repository; source checkpoint diff generated with git diff --no-index |
| Whitespace check | PASS with CR-at-EOL recognized for existing Windows files |
| Targeted secret scan | PASS: no high-confidence token/private-key patterns in changed/new files |
| Frozen backend/config | UNCHANGED (all seven manifest entries) |

Python failures:
- test_missing_beginning_detected_and_retried
- test_rejected_generation_stays_in_attempts_not_reading_channel
- test_second_sentence_is_not_silently_dropped

Current vendor/text_lid/langid read attempts fail with EPERM / WinError 5. TextLanguageValidator import reports ModuleNotFoundError: langid.langid. The same three failures and FinalTests setUpClass error reproduce using the original checkpoint test sources in the original runtime context. Only the old real-cache fixture failure is removed by this change. **Full Python acceptance has NOT passed.** No production/model/ACL changes were made to conceal this.

PROJECT_STATUS.md remains unchanged because this task explicitly permits its update only after successful validation; it still contains the prior status and must not be mistaken for v2.0.5 validation.

## Cache acceptance

CACHE MANAGER: **PARTIAL** — implementation/build/automated safety passed; actual modal visual interaction not tested.
CACHE JOBS DISCOVERED: **1 user project / 2 namespaces**, 22,138,389 bytes (21.1 MiB). One protected service/unknown entry. Real jobs not deleted.
CACHE SAFETY: **PASS automated**, ownership/path/lock/checksum/confirmation/reparse/hardlink/changed-snapshot cases covered.
EXIT CACHE POLICY: **DOCUMENTED / config support implemented** (ask default, always_clean_completed, never). Actual exit cleanup/dialog deferred; every policy currently keeps real cache on exit. Existing backend close/cancel handling retained; close held only while cache service work is active.

## Performance

NLLB A/B: **BLOCKED**.
Exact blocker: nvidia-smi -> “Failed to initialize NVML: Unknown Error”.
CPU NLLB median: N/A.
CUDA NLLB median: N/A.
Speedup / seconds / percentage: N/A.
Peak used VRAM / minimum free: N/A.
Quality: NOT MEASURED; no differences were generated or certified.
Pyannote A/B: NOT RUN; NLLB completion prerequisite unmet.
Current cold run: accepted prior ~288–317 seconds.
Candidate estimate: N/A; no independently passing experiments.

Reports: dev/performance/NLLB_CPU_CUDA_V205.md and NLLB_CPU_CUDA_DIFF.md.
Existing smoke01-A evidence predates this task and is not counted. Production config remains CPU. Warmup/order/forbidden-inference guards are tested; live metric accuracy and complete G0–G4 evidence remain unverified. Per-process VRAM in the existing analyzer is an estimate, not independently verified measurement.

## Portable

PORTABLE READINESS: **PARTIAL**; final package and E: launch NOT TESTED.
Blockers: host-bound Python/venv, external Hugging Face model snapshots, missing bundled FFmpeg/FFprobe, unreadable LID vendor, unavailable GPU telemetry, native DLL closure/offline relocation validation. Future package config must select cache/jobs instead of frozen _internal/temp/v157 default. No model duplication or real-cache migration performed.

## File inventory

Created:
- cache_manager_v205.py
- frontend/src/cache.rs
- tests/test_cache_manager_v205.py
- tests/test_perf_safety_v205.py
- dev/validate_v205_tests.py
- CACHE_MANAGER_V1.md
- PORTABLE_READINESS_V1.md
- VALIDATION_V205_NIGHTLY.md
- dev/performance/NLLB_CPU_CUDA_V205.md
- dev/performance/NLLB_CPU_CUDA_DIFF.md
- backups/v204_before_v205_nightly/* (checkpoint + manifests)
- dev/validation_v205/* (logs, JSON evidence, source diff, post-change manifest)
- artifacts/v2.0.5/Audio2Text.exe + SHA256SUMS.txt

Updated:
- frontend/src/main.rs
- frontend/src/app_state.rs (terminal-state test only)
- frontend/ui/main.slint
- frontend/Cargo.toml
- frontend/Cargo.lock (application version only)
- tests/test_v156.py
- dev/perf_audit_v158.py

Frozen files NOT TOUCHED:
- audio_pipeline_cuda_v156.py
- translation_v156.py
- audio_pipeline_cuda_v157.py
- backend_runtime_v157.py
- backend_contract_v1.py
- language_control_v204.py
- config_v157.json

Old versions, real temp/v157 caches, accepted output, source input, protected assets, models and rollback material were not cleaned or migrated. tests/.runtime lifecycle cleanup is limited to explicitly created synthetic test fixtures.

## Remaining limitations / NEXT

Remaining: full Python/Ruff gate, physical UI/output/final terminal screenshots, executed exit-cleanup policy, measured NLLB quality/resource gates, optional pyannote experiment and portable another-drive acceptance.

**NEXT RECOMMENDED PHASE:** restore readable vendor/text_lid/langid access and close the full Python validation gate without changing frozen inference semantics.

COMMIT/PUSH: **NO**. STOP.
