# Public publication audit — Audio2Text v2.0.5

Date: 2026-10-13. Stage: Release Baseline. Development: **PAUSED**. Execution: HEADLESS; no GUI or inference.

## Scope and history

All **93 files** of the original baseline were inspected by path, size, blob-content scan and manual review of candidate findings. A local account path/name and private regression-media filename were found in documentation/test source. The owner authorized a clean public root with the original commit retained locally.

Sanitized root: `72aee752e6d10f2e2cea0c65fb2b3731084c6280`, with no parents and 93 files. The original history is retained on local-only branch `local/private-v205-baseline`; it is not an ancestor of the publication branch. Never push that branch with `--all` or `--mirror`.

Remote ownership and push permission were verified using the authenticated GitHub account. The existing public repository was empty before the first push. The root was pushed to `release/v2.0.5-baseline` and confirmed by GitHub's commit API. Repository: [AlexHDman/Audio2Text](https://github.com/AlexHDman/Audio2Text). This documentation is a separate commit; resolve its identity from Git rather than embedding its own hash.

## Findings and disposition

| Check | Result | Evidence / boundary |
|---|---|---|
| Personal paths/account and private media name | PASS after sanitation | Generic environment-variable paths, sample name and environment notes |
| Media-dependent path test | PASS | Unique empty synthetic fixture in ignored tests/.runtime; removes only its own fixture; no decoding or runtime-path change |
| Secret scan | PASS within inspected tree | Credential/token/private-key patterns and manual candidate review; redaction keywords are not credentials |
| Client media, outputs, models, vendor, caches, logs, binaries | PASS | None tracked; ignore probes pass for protected paths |
| Artwork | PASS for publication inspection | Existing artwork visually inspected; no client photos or identifying metadata found |
| Config templates / TCM dictionaries | PASS | Generic settings/terminology; private config/overrides excluded |
| Source integrity | PASS | 80-entry manifest matches; frozen backend/runtime and production config unchanged |
| Dependencies | PASS for bounded source-only audit | 323 Windows Rust license declarations; direct Python review; external model constraints documented |
| Project LICENSE | DEFERRED | Owner decision; no open-source license selected/implied |
| Product acceptance | PARTIAL | Publication does not establish portable/LIVE acceptance or create a release |

Scans are bounded checks, not proof that every possible secret can be recognized. Raw audit evidence stays in ignored `dev/public_audit_20261013`; previous evidence stays in `dev/git_baseline_20261013`. Private evidence and working data were preserved.

## Validation

The only source change is under `#[cfg(test)]` in `frontend/src/paths.rs`, removing the private-file dependency. Production Rust behavior and Python/backend bytes are unchanged. The source manifest updates that test file's hash.

- Rust: **34 PASS, 0 failed, 1 intentionally ignored Explorer test**.
- Rust fmt: **PASS**. Clippy with `-D warnings`: **PASS**, with environment hardlink-copy warnings from rustc.
- Git diff whitespace check: **PASS**, respecting preserved CRLF via `core.whitespace=cr-at-eol`.
- Python: previous same-source baseline **155 PASS / 1 environment error**, 156 executed; not rerun for documentation/test-fixture sanitation. Error is in hardlink setup before product assertion.
- OFFSCREEN QA and LIVE GUI GATE: **NOT RUN**. No application rebuild, inference, release/tag or production CUDA switch.

README is bilingual. The deny-by-default .gitignore explicitly allows the three new audit/license documents; final documentation commit has **96 tracked files**. No LICENSE is created. See [dependency audit](DEPENDENCY_LICENSES.md), [checkpoint](EXPC_CHECKPOINT.md) and [paused backlog](EXPC_BACKLOG.md).
