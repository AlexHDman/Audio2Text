# EXPC CHECKPOINT — Audio2Text

Updated: 2026-10-13. Stage: **Stabilization / Git Baseline**. Development: **PAUSED** after baseline fixation; interface development paused.
Mode: RELEASE GATE + GIT, HEADLESS/BACKGROUND. Agent: Codex Desktop Local, current model, effort HIGH.
Root: C:/AI/Audio2Text. Selected version: **v2.0.5 nightly source baseline**; backend **v1.5.7 FROZEN**. v2.0.6 is not accepted or promoted.

Git branch: `release/v2.0.5-baseline`. Baseline identity is the enclosing commit (resolve with `git rev-parse HEAD`); no self-referential commit hash is embedded. No remote configured or confirmed. Push blocked pending exact user-owned GitHub URL. No tag/release.

- No active benchmark/validation process found before work; nothing interrupted.
- Existing v2.0.5 EXE SHA256 verified: `0c873d19a1edd4b4c4262e3d9848cdb2972710b03924c4f82d416df7bf619a65`; artifact remains local at artifacts/v2.0.5/Audio2Text.exe. No rebuild.
- Included source matches 41 available v2.0.5 checkpoint entries. V205_SOURCE_SHA256.json records baseline source/assets/templates.
- CLI TESTS: PARTIAL. Fresh included Python tests 155 PASS / 1 environment error (hardlink WinError 5; 156 executed). Rust 34 PASS / 1 intentionally ignored Explorer test; fmt PASS. OFFSCREEN QA and LIVE GUI GATE: NOT RUN.
- Scope: source/config templates/necessary documentation. Models, vendor payload, venv, private media/output, cache, logs, binaries and v2.0.6 experiments are ignored and preserved locally.
- v2.0.6 dynamic gate remains LOCAL-ONLY: tested guards, no safe complete NLLB A/B. Last forecast required 7225 MiB free; last recorded deficit 3272 MiB. These time-specific values are not current admission permission.
- Old CUDA runs failed resource/quality gates (639–680 MiB recorded free; 1 generation vs CPU 109). No accepted speedup.
- LID/NVML access recovered in the prior step without ACL/driver changes. No runtime/config/cache or UI changes in this task.
- Baseline report: GIT_BASELINE_V205.md. Local evidence: dev/git_baseline_20261013. Previous checkpoint preserved in backups/v205_before_git_baseline_20261013.
- Word Journal, settings and animation remarks retained in EXPC_BACKLOG.md; implementation deferred during PAUSED.

NEXT: user confirms the exact existing GitHub repository URL; verify ownership/access before push. Development remains PAUSED. STOP.
