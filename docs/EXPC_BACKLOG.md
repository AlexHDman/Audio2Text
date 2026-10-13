# EXPC BACKLOG вЂ” Audio2Text

Updated 2026-10-13. Release Baseline. Development: **PAUSED**, including interface work. Selected baseline v2.0.5 nightly, backend v1.5.7 frozen; v2.0.6 remains local-only. Branch release/v2.0.5-baseline; enclosing commit is the baseline identity.

| ID | Priority | Observed / expected | State and evidence |
|---|---|---|---|
| PERF-01 | P0 | CUDA memory forecast needs 7225 MiB free; historically available 3953.87; missing 3272 MiB | BLOCKED; dev/validation_v206/recovery_20261013_130004/dynamic_vram_gate.json. No model loaded; fixed 4000 cap removed |
| PERF-02 | P0 | Historical B runs drop below 768 MiB, produce only 1 generation and failed translations; equivalent complete workload required | Historical resource/quality FAIL. Existing results retained. New dynamic admission/watchdog tested, real loaded-model gate NOT TESTED |
| PERF-03 | P1 | Old free=total-used counted about 256 MiB reserved as free | FIXED in dev harness via existing direct NVML. Production used/total provider unchanged |
| QA-01 | P1 | Hardlink fixture os.link raises WinError 5 before assertion | OPEN environment limitation; Python 206/207 PASS. No ACL/security workaround, no test weakening; Rust compiler also warns and copies |
| QA-02 | P2 | Ruff absent in venv/PATH | UNAVAILABLE, not installed; Python compile and Rust fmt/Clippy checked |
| QA-03 | P2 | Explorer-opening Rust test requires GUI | Intentionally ignored under HEADLESS; normal Rust 34 PASS |
| ENV-01 | P0 | Earlier LID WinError 5 under CodexSandboxOffline | ACCESS RECOVERED under the local Windows account; protected owner ACL explains contrast. Vendored 1.1.6 imports, previous 3 failures + 22 blocked tests pass. No files/ACL repaired |
| ENV-02 | P1 | Earlier nvidia-smi exit255 and shell helper failures | CURRENT probes PASS under the local Windows account; historical sandbox behavior not re-created |
| DOC-01 | P2 | PROJECT_STATUS.md is an older v2.0.3 report | Current public authority: EXPC_CHECKPOINT.md; local experimental validation remains private |

## Preserved UI feedback вЂ” deferred while PAUSED

- **UI-WORD-JOURNAL:** user requested preservation of Word Journal remarks. Detailed examples/reproduction and acceptance criteria are not supplied in this task; keep the topic OPEN / NOT VERIFIED and obtain them before implementation. Do not infer a backend/export fix.
- **UI-SETTINGS:** settings remarks retained as OPEN / NOT VERIFIED. Concrete correction scope requires the user's next task; no settings redesign authorized now.
- **UI-ANIMATION:** previous requests require perceptible stage-marker motion and readable panels. Physical LIVE acceptance remains pending; preserve the concern and approved visual assets/layout. No animation changes during pause.
- **GIT-REMOTE:** RESOLVED. Confirmed public origin https://github.com/AlexHDman/Audio2Text.git; sanitized root 72aee752e6d10f2e2cea0c65fb2b3731084c6280 pushed and verified. Original history preserved on local-only backup branch; no release/tag.
- **LICENSE:** DEFERRED by owner. README and dependency audit document source-publication boundaries. Binary/portable redistribution requires a separate license/notice/model gate.
- **PUBLIC-PRIVACY:** RESOLVED for inspected publication tree. Personal paths and regression-media filename removed; synthetic path fixture passes. Production backend remains frozen.

NEXT: preserve PAUSED and collect concrete validation/UX evidence only on a new user task. Development stays PAUSED. Future benchmark work requires a new explicit task and fresh dynamic VRAM admission; old timings cannot become an accepted speedup. No production CUDA switch.
