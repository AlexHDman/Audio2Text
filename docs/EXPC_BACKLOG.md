# EXPC BACKLOG — Audio2Text

Updated: 2026-11-12. Stage: Source Backup / Backend Quality validation. Development: **PAUSED**. Candidate branch `feature/backend-quality`; identity is the enclosing commit. Stable baseline `703dd5b52af8599a9fa17716ffee27967b424401` remains unchanged. GUI remains frozen.

## GitHub backup — 2026-11-12

Source backup published and clone-verified on `feature/backend-quality`; stable
v2.0.5 stays unchanged. DEVELOPMENT: PAUSED after backup. Restore recipe, observed
dependency pins and safe build/test helpers added. Fresh-machine installation,
authorized real inference, semantic review and performance acceptance remain OPEN.
Private media fixtures and v2.0.6 experiments remain local-only. No release or
portable publication. See GITHUB_BACKUP_AUDIT.md for publication verification.
111 source files match the GitHub clone; public Python 175 PASS and Rust check
PASS. One previously hidden test-only backup dependency is now an included
AST-preserving fixture. Existing runtime/Cargo dependencies were reused, so this
is source-recovery PASS and fresh-machine runtime recovery remains NOT RUN.
Earlier statements withholding commit/push authorization describe prior tasks;
the user's current GitHub-backup task explicitly authorizes this branch's backup.

## A2T-BE-001 — current findings

| ID | Priority | Observed / expected | State and evidence |
|---|---|---|---|
| BE-001-ASR | P1 | Long speech units collapsed to credit-like text; expected substantive speech coverage | FIXED CANDIDATE / HUMAN REVIEW OPEN: three actual waveform units recovered, primary evidence retained; 508→640 words across film; no certified audio reference |
| BE-001-LID | P1 | RU with GMP/FDA incorrectly MIXED; expected RU without masking actual code-switches | VERIFIED in control and fixtures: MIXED/unsupported 2→0; final full AUTO audio route not rerun from scratch |
| BE-001-TERMS | P1 | FOHOW variants and short slogans mistranslated | VERIFIED within bounded control/phrase checks: known distortions 12→0, external context-aware glossary; original text and model response retained; names not auto-corrected |
| BE-001-EMPTY | P2 | Empty ASR tail reported translation failed | FIXED / TESTED: translation skipped with explicit empty-source warning; underlying empty ASR remains visible |
| BE-001-REVIEW | P1 | Semantic certification absent despite technical completion | OPEN: selected needs_review 26→27, journal blocks 4→7; new recovered speech requires review; false MIXED flags removed without hiding genuine issues |
| BE-001-PERF | P1 | Expected no substantial slowdown | NOT MET: paired CPU ASR+NLLB 494.737→612.392 s (+23.78%); one pair, fixed diarization/LID. Decide acceptance or authorize a separate bounded optimization task |
| BE-001-MULTI | P1 | Preserve AF/EN/NL/ZH scenarios | VERIFIED translation/fixtures: identical real CPU NLLB output/status on four synthetic controls; new multilingual audio acceptance NOT RUN |
| BE-001-CACHE | P1 | Candidate policy/dictionary must not reuse incompatible results | VERIFIED: hash invalidation and zero-inference resume; original working cache retained |
| BE-001-QA | P2 | Headless regression and preservation | 226 Python PASS; Rust 34 PASS/1 ignored; fmt/Clippy/AST/tabnanny PASS; 106 protected hashes and baseline EXE unchanged |

Evidence and acceptance boundaries: `BACKEND_QUALITY_VALIDATION.md`, `BACKEND_QUALITY_BEFORE_AFTER.md`; private raw artifacts under ignored `dev/backend_quality_20261111`. NEXT: human listening review, then a separate decision on measured processing cost. No new phase, commit, push or release is authorized.

## Preserved earlier backlog — historical status unless superseded above

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
