# A2T-BE-001 — Backend quality validation

Date: 2026-11-11. Branch: `feature/backend-quality`. No commit/push/merge. GUI frozen. Final status: **PARTIAL**. Implementation and automated checks complete; performance and human semantic acceptance remain open.

## Automated gate

- Full Python discovery: **226 tests PASS**, including 19 new policy regressions and the existing AF/EN/NL/Chinese, translation, cache, IPC and performance-safety fixtures. Evidence: `dev/backend_quality_20261111/python_tests_final.log`.
- The initial sandbox run failed at `os.link` in the hardlink fixture. The same unmodified full suite passes in the ordinary user execution context. No ACL, security or driver changes were made.
- Rust: **34 PASS / 1 intentionally ignored Explorer test**. `cargo fmt --check` and offline locked Clippy with `-D warnings`: **PASS**. GUI was not launched.
- Python syntax compilation in memory and tabnanny: **PASS**. Ruff/Black/pyflakes are not installed; external Python lint: **UNAVAILABLE**, not installed by this task.
- Git diff whitespace check: **PASS** using CRLF-aware configuration.
- New fixtures contain synthetic text only. Private evidence, model paths, original media and exports remain ignored.

## Runtime comparison protocol

The entire 401.380-second control video is processed twice with matched CPU/int8 Whisper, CPU NLLB, AUTO source and explicit target EN. The same validated diarization is reused in both arms to isolate ASR/routing/translation changes; this is not a cold pyannote validation. FFmpeg prepares audio separately and the resulting checksum must match the original job. BEFORE runs fresh language detection. A separate interrupted AFTER runs fresh language detection and produces identical unit IDs, boundaries, languages, methods, candidate languages and probe metadata except confidence. Confidence differs, especially in the short empty tail (0.5262 versus 0.5644). Final AFTER explicitly reuses the complete BEFORE language plan under a validation-only fingerprint. ASR and translation execute freshly over the entire video in both measured arms. Performance is compared over ASR plus translation only; this does not validate a fully fresh final AUTO run. Each arm has its own cache and export directory.

This pair is one measurement per arm, not a statistical benchmark. The original GPU result is only historical quality evidence; its wall time is not a fair CPU performance baseline. GUI, CUDA acceptance and human semantic certification are not inferred from these runs.

## Preservation and cache

The baseline branch stays at `703dd5b52af8599a9fa17716ffee27967b424401`. Frozen v155/v156/v157 entrypoint/engine files and translation_v156.py, GUI source/assets, original video/outputs and production config are checked against a pre-task SHA256 manifest. `backend_runtime_v157.py` is intentionally changed only as the candidate policy adapter. The old V205 source manifest remains a baseline reference, not a candidate manifest.

Candidate policy code/terminology hashes participate in processing config and stage identity. Tests demonstrate invalidation on policy or dictionary changes. Existing production caches are not migrated or deleted. Candidate resume is checked with the existing `require_resume` guard, with zero inference required for acceptance.

## Acceptance limitations

Restored text is inferred from audio and carries a review warning with original/alternative evidence. No human transcript or independent listening sign-off is available. Names and geography are not auto-corrected. `needs_review` is retained where semantic validation is absent; successful EOS/coverage is not described as proof of complete meaning. No GUI/DOCX-formatting redesign or new CUDA translation mode is included.

## Final acceptance matrix

| Requested gate | Result | Evidence / limitation |
|---|---|---|
| Original fragments retained | PASS for structural preservation | Raw hashes and source-member coverage verified; all 19 primary ASR units exactly match paired BEFORE and remain available |
| No new missing audio | PARTIAL | Unit boundaries unchanged; three sparse intervals recovered; no certified transcript for absolute audio coverage |
| Languages / selected target | PASS on control and fixtures | MIXED 2→0; EN selected only; RU/EN bypass and manual whitelist fixtures pass |
| Protected terminology | PASS on bounded control checks | Known distortions 12→0; FOHOW/FENDOU/GMP/FDA present; names not corrected |
| failed / unsupported causes | PASS for reproduced mechanisms | Empty text no longer translated; unresolved/unmapped diagnostics; control unsupported 2→0 |
| Fewer unjustified review flags | PARTIAL | False MIXED warnings removed, but needs_review 26→27 and journal review 4→7 due to recovered speech; human semantic review remains mandatory |
| RU→EN meaning | PARTIAL | Two exact phrase tests pass on real CPU NLLB; full meaning/proper names await human review |
| AF/EN/NL/Chinese compatibility | PASS for tested scope | Real CPU NLLB output/status equality on four synthetic cases; existing fixtures pass; new multilingual audio benchmark NOT RUN |
| Cache correctness | PASS | Policy/dictionary hash invalidation; resume performs zero inference |
| No substantial performance regression | NOT MET | ASR+translation 494.737→612.392 s (+23.78%), one pair |
| Python / Rust | PASS | 226 Python; 34 Rust pass / 1 intentional GUI ignore; Rust fmt/Clippy pass |
| GUI / public baseline preserved | PASS for hash preservation | 106 protected manifest entries unchanged; baseline branch and EXE unchanged; no publication |

CLI TESTS: PASS. OFFSCREEN QA: NOT RUN. LIVE GUI GATE: NOT RUN. DOCX formatting XML hashes match; this is not visual acceptance. NLLB stayed on CPU. No cold pyannote or fresh final full AUTO/CUDA test was performed.

Final artifacts: `final_comparison.json`, `translation_regression.json`, `preservation_final.json`, `public_source_scan.json`, test/lint logs and separate before/after TXT/JSON/DOCX in ignored `dev/backend_quality_20261111`. Interrupted experiments are retained and excluded from acceptance. Candidate source hashes are in `final_comparison.json`; base HEAD remains unchanged. External Python lint unavailable; AST/tabnanny and Git whitespace checks pass.

Development returns to **PAUSED**. No commit/push/merge, production config/model/cache changes or GUI work. Next action: human listening review of the three recovered intervals and closing phrases, then decide separately whether the measured performance cost is acceptable. No automatic optimization phase.
