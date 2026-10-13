# Git baseline — Audio2Text v2.0.5

Date: 2026-10-13. Stage: Stabilization / Git Baseline. Development: PAUSED after this baseline commit.

## Version decision

Selected **v2.0.5 nightly source baseline**, frozen backend v1.5.7. v2.0.6 has no complete passing translation A/B or full acceptance and is not promoted. v2.0.5 also retains documented LIVE/portable acceptance limitations; this commit is not a release or a claim of full product PASS.

Existing v2.0.5 EXE: 20,483,584 bytes, SHA256 `0c873d19a1edd4b4c4262e3d9848cdb2972710b03924c4f82d416df7bf619a65`. Rechecked against VALIDATION_V205_NIGHTLY.md. Binary remains local, outside Git. No rebuild/GUI/inference was performed for this task.

41 selected files with entries in the pre-v206 checkpoint match their v2.0.5 SHA256 references, with zero mismatches. Remaining included original UI source assets are recorded in V205_SOURCE_SHA256.json. Frozen runtime sources and local production config remain unchanged. Config files in Git are generic copies named *.example.json; actual config files remain ignored.

## Fresh validation and limitations

- Process inventory through psutil showed no running Audio2Text benchmark/validation jobs before work; only the diagnostic Python process and its venv launcher. CIM enumeration was denied; no processes were interrupted.
- Python included-source regression set: **156 executed, 155 PASS, 0 assertion failures, 1 environment error**. test_cache_manager_v205.CacheTests.test_hardlink_content_refused hits WinError 5 at os.link before the product assertion. No skip or weakened assertion was introduced.
- Rust: **34 PASS, 0 failed, 1 intentionally ignored Explorer test**. cargo fmt --check PASS. Prior same-source Clippy PASS; hardlink-copy warning documented in v206 evidence.
- CLI TESTS: PARTIAL due to hardlink fixture. OFFSCREEN QA: NOT RUN. LIVE GUI GATE: NOT RUN.
- Full prior v206 suite is separate local evidence: 206 PASS / 1 environment error. Its experiments/tests are not part of the v2.0.5 Git baseline.
- No tag/release or production CUDA switch. Portable fresh-machine installation is not verified.

## Git scope and privacy

A local repository was initialized on `release/v2.0.5-baseline`. No remote existed or was added. No confirmed user-owned GitHub repository URL is available; push must stop until the user confirms the exact owner/repository URL. Global author identity was already configured; it was not invented or changed.

Track production and supporting regression source, Cargo lock/build inputs, reviewed generic TCM mappings, required UI source assets, generic config templates and current baseline documentation. A deny-by-default .gitignore protects venv/vendor/models, input/output, private material, temp/cache/logs, rollback copies, generated exports, secrets and build artifacts. Vendored langid embeds a model and must be supplied locally.

Private-fixture-dependent test_v157.py, all dev benchmark tooling, v2.0.6 safety tests and performance plans/results remain local and ignored. Nothing was deleted or reverted. The baseline is deliberately a source snapshot, not a self-contained distribution. README lists prerequisites.

.git attributes disable line-ending conversion to preserve frozen source hashes. Staged-byte scans, path/size checks and manifest comparisons are retained in ignored dev/git_baseline_20261013. Existing protected data is not staged. The source manifest can be rechecked against the enclosing commit with git show.

## Pause and next action

Further interface development is **PAUSED**. Preserve open Word Journal, settings and animation feedback in EXPC_BACKLOG.md. No implementation resumes without a new explicit task. Next Git action: obtain confirmation of the exact existing GitHub URL owned by the user, verify it, then push only when authorized. No remote is guessed.
