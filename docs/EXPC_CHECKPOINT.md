# EXPC CHECKPOINT — Audio2Text

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
