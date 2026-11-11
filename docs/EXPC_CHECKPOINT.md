# EXPC CHECKPOINT — Audio2Text

## GitHub source backup — 2026-11-12

Stage: Source Backup / Backend Quality validation. DEVELOPMENT: **PAUSED**.
Task: audit, prepare, commit, push, verify current source; HEADLESS, Codex Desktop
Local, current model, HIGH effort. Branch: `feature/backend-quality`; backup
identity is the enclosing commit. Origin: https://github.com/AlexHDman/Audio2Text.git.
Stable baseline remains `703dd5b52af8599a9fa17716ffee27967b424401` on
`release/v2.0.5-baseline`. No main/merge/force-push/tag/release changes.

Prepared: BE-001 source/test/dictionary/reports, safe config examples, unchanged
Rust/Slint sources/assets, pinned observed dependency inventory, model revision
manifest, source build/test/provision helpers and RESTORE_FROM_GITHUB.md.
Private history, production config, vendor/model payloads, environments, portable
packages, media/results, resume caches and v2.0.6 experiments remain excluded.
No project or external backup deletion/cleaning. Candidate quality/performance
acceptance remains PARTIAL; this task changes no backend/UI algorithms.

CLI checks: public Python 175 PASS; Rust 34 PASS / 1 GUI test ignored; fmt/Clippy
PASS. Full clean-machine dependency provisioning and inference: NOT RUN.
OFFSCREEN QA / LIVE GUI GATE: NOT RUN. Final publication/clone evidence is recorded
in GITHUB_BACKUP_AUDIT.md and the GitHub branch history. Preserve all open findings.

NEXT: retain DEVELOPMENT: PAUSED; use the restore guide when recovery is requested.
No automatic further development or release.

## Previous BE-001 checkpoint — historical

Updated: 2026-11-11. Stage: **Backend Quality Improvement / validation**. Development: **PAUSED** after A2T-BE-001; GUI/interface remain frozen.
Mode: AUDIT → IMPLEMENT → TEST, HEADLESS/BACKGROUND. Agent: Codex Desktop Local; model identity not independently exposed; effort HIGH.
Root: C:/AI/Audio2Text. Local candidate branch: `feature/backend-quality` at unchanged HEAD `703dd5b52af8599a9fa17716ffee27967b424401`, with uncommitted candidate changes. Public baseline `release/v2.0.5-baseline` remains at that SHA. No commit/push/merge/tag/release.

## A2T-BE-001 result — PARTIAL

- Implemented `backend_quality.py`, external protected terminology and narrow adapter hooks in `backend_runtime_v157.py`. Frozen v155/v156/v157 entrypoints, inference engine, translation_v156, production config and GUI remain unchanged. No NLLB CUDA switch.
- Real full-video CPU ASR/translation pair: 508→640 recognized words; three sparse intervals recovered with primary evidence retained. MIXED and selected-channel unsupported_language 2→0. Known distorted brand variants 12→0. Original text remains immutable.
- Matched scope: fixed reference diarization in both arms, fixed BEFORE language plan in final AFTER. Fresh prior AFTER LID has equal boundaries/routes with different confidence. This is not a fresh final full AUTO/pyannote acceptance run.
- ASR+translation: 494.737→612.392 seconds, **+23.78%**. No-substantial-performance-regression gate NOT MET. One pair only. No semantic PASS inferred from text counts, probability or agreement.
- Python **226 PASS** in normal user context; sandbox hardlink restriction reproduced without weakening tests. Rust **34 PASS / 1 ignored**, fmt/Clippy PASS. AST/tabnanny/Git whitespace PASS; external Python lint unavailable.
- Real NLLB CPU AF/NL/EN/ZH→RU outputs and statuses unchanged on synthetic controls. RU→EN exact phrase checks pass. All 19 primary ASR units match paired BEFORE; complete source/member coverage validated. Resume has zero inference calls. TXT/JSON/DOCX generated in isolated evidence directories; DOCX format XML hashes unchanged.
- 106 protected manifest entries unchanged, including control materials, old experimental scripts, GUI/core/config. Baseline EXE SHA256 remains `0c873d19a1edd4b4c4262e3d9848cdb2972710b03924c4f82d416df7bf619a65`. Working caches and original outputs not migrated/deleted/overwritten.
- Private artifacts and exact candidate hashes: `dev/backend_quality_20261111/final_comparison.json`; before/after caches/exports/events, `translation_regression.json`, test/lint logs and preservation manifest. Interrupted experiments retained, excluded from acceptance.
- Reports: `BACKEND_QUALITY_AUDIT.md`, `BACKEND_QUALITY_VALIDATION.md`, `BACKEND_QUALITY_BEFORE_AFTER.md`. No private transcript/media copied into public fixtures/docs.
- CLI TESTS: PASS. OFFSCREEN QA: NOT RUN. LIVE GUI GATE: NOT RUN. Human audio/meaning and proper-name review remain open. `needs_review` preserved; no hidden warning suppression.

NEXT: review the three recovered audio intervals and closing phrases against the private before/after exports; separately decide whether +23.78% processing time is acceptable. No automatic next implementation phase. DEVELOPMENT: PAUSED. STOP.

## Previous publication checkpoint — historical

Updated: 2026-10-13. Stage: **Release Baseline**. Development: **PAUSED**, including interface work.
Mode: RELEASE / GIT ONLY, HEADLESS/BACKGROUND. Agent: Codex Desktop Local, current model, effort HIGH.
Root: C:/AI/Audio2Text. Selected version: **v2.0.5 nightly source baseline**; backend **v1.5.7 FROZEN**. v2.0.6 is not accepted or published.

Branch: `release/v2.0.5-baseline`. Current documentation identity is the enclosing commit (`git rev-parse HEAD`). Confirmed public origin: https://github.com/AlexHDman/Audio2Text.git. Sanitized root `72aee752e6d10f2e2cea0c65fb2b3731084c6280` has been pushed and verified through GitHub. Original baseline remains on local-only `local/private-v205-baseline`; never publish that ref. No tag/release.

- Public audit: sanitized all 93 original files; no tracked private media, credentials, environments, model/vendor payloads, caches or compiled artifacts found. Added three audit/license documents in the separate documentation commit (96 total files).
- Bilingual README and publication allowlist prepared. LICENSE deliberately absent at the owner's request. Slint/model constraints and future binary-distribution gates recorded in DEPENDENCY_LICENSES.md.
- Only source change for publication: synthetic fixture replaces private-media dependency in one Rust test. Production Rust behavior and all Python/backend files unchanged. Manifest updated for test-file hash; remaining 79 entries unchanged.
- CLI TESTS: Rust 34 PASS / 1 ignored Explorer test; fmt and Clippy PASS, rustc hardlink-copy warnings. Latest same-source Python baseline: 155 PASS / 1 environment error, 156 executed; not rerun during publication. Full product validation remains PARTIAL.
- OFFSCREEN QA: NOT RUN. LIVE GUI GATE: NOT RUN. No inference, application rebuild, runtime config/cache changes or package installs.
- Frozen sources and production config hashes verified. Existing local EXE SHA256: `0c873d19a1edd4b4c4262e3d9848cdb2972710b03924c4f82d416df7bf619a65`; artifacts/v2.0.5/Audio2Text.exe remains outside Git.
- Source assets/config templates are listed in V205_SOURCE_SHA256.json. Audit: PUBLIC_AUDIT_V205.md. Private evidence: dev/public_audit_20261013 and dev/git_baseline_20261013.
- v2.0.6 experiments/results remain local-only; no accepted complete NLLB CUDA A/B or production CUDA switch. Prior memory forecasts are historical, not permission to run.
- Word Journal, settings and animation remarks remain OPEN / deferred in EXPC_BACKLOG.md.

NEXT: preserve PAUSED; collect specific validation/UX evidence only on a new user task. No automatic implementation or release. STOP.
