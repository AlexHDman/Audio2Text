# GitHub source backup audit

Date: 2026-11-12. Branch: `feature/backend-quality`.
Repository: https://github.com/AlexHDman/Audio2Text.
DEVELOPMENT: PAUSED. Source backup only; no release or product acceptance.

## Scope and provenance

Parent/stable baseline: `703dd5b52af8599a9fa17716ffee27967b424401`.
Existing BE-001 changes are preserved and committed as a candidate. Frozen Python
entrypoints/translation engine and Rust/Slint UI remain byte-identical to baseline.
Only recovery tooling, dependency metadata and documentation are newly prepared.
The private original history ref is not an ancestor of the publication branch and
will not be pushed. Only an explicit feature branch refspec is used.

## Publication contents and exclusions

Included: Python runtime sources, protected terminology/generic TCM dictionaries,
safe configuration templates, Rust/Slint source artwork and Cargo.lock, synthetic
tests, build/test/model-provision scripts and technical documentation.
Observed Python dependency pins contain names/versions only; model manifest
contains repo IDs/revisions only. No credential or installed third-party payload.

Excluded without local deletion: venv, vendor, models, input/output, customer
documents/media, caches/temp/logs, local production configs, target/build/dist/distr,
EXE/DLL/ZIP, portable artifacts, private fixtures/evidence and v2.0.6 experiments.
Root-deny publication allowlist retained with explicit build/dist/distr exclusions.
Source PNG/ICO/SVG artwork remains necessary for rebuilding the unchanged UI.

## Validation before publication

- Public Python suite: **175 PASS** (existing environment, no inference).
- Rust: **34 PASS / 1 ignored**; fmt and Clippy **PASS**.
- Publication tree: **111 files**, approximately **5.15 MiB**, including required
  source artwork. **62 protected baseline hashes match** (frozen backend and UI).
  Both reachable pre-existing public commits were scanned. No findings for the
  inspected credential/private-path patterns or forbidden payloads. The original
  private history is not an ancestor. The local gate also compares staged blobs
  against the inspected working-tree manifest before commit.
- New download helper: consent refusal, six exact requests, PLDA/offline refs and
  conflicting-cache refusal verified with fixtures; no model download/inference.
- Python AST/tabnanny and PowerShell parser PASS. Git whitespace check uses
  `core.whitespace=cr-at-eol` to respect the preserved Windows CRLF sources.
  It reports one pre-existing extra blank line at the end of backend_quality.py;
  candidate bytes are retained because its content hash participates in cache identity.
- No GUI automation, package installation, production cache/config changes,
  deletion, branch merge, force push, tag or GitHub Release.

## Recovery limits

RESTORE_FROM_GITHUB.md explains toolchain, 114 observed Python package pins,
langid vendor provisioning, six model revisions including PLDA, configuration,
working directories, tests and Rust build. Existing own-code license decision
remains deferred; dependency/model terms remain separate.
The observed runtime lacks declared torchcodec; this is explicitly documented,
not hidden by an automatic dependency upgrade. Package download availability,
new-machine CUDA and real fresh-install inference have not been tested here.
Private media/results cannot be reconstructed from this source-only backup.
Portable assembly evidence/payloads are local-only, not a reproducible ZIP claim.
BE-001 semantic review and +23.78% runtime cost remain open.

## Remote verification

- Initial source commit `c3e99bd02bb78bde846f0d200a92cf1743452115` pushed and
  retrieved via an independent GitHub clone; all initial 110 blobs matched.
  GitHub connector also fetched RESTORE_FROM_GITHUB.md at that immutable SHA.
- Clone testing exposed a hidden dependency on a private pre-UX backup file:
  174 tests passed, one errored. It was not counted as a successful recovery.
- Commit `6cb9fedc6c51353e06e9de8f2ea6f0a3ebab0a4a` added a minimal AST-only
  historical fixture and changed the test's lookup path. All nine original AST
  nodes match the actual historical source; no preservation assertion was removed.
  The full original backup file and production backend remain untouched.
- That commit was pushed, downloaded through a fast-forward update of the fresh
  clone, and checked: **111/111 SHA256 matches**, identical Git trees, clean
  tracked worktrees; **175 Python tests PASS** (13.696 s).
- Rust source from the GitHub clone: `build_frontend.ps1 -CheckOnly -Offline`
  **PASS**. This is `cargo check`, not a release EXE build. The existing host
  Cargo registry/build cache was reused. The 34/1 Rust tests and fmt/Clippy
  were run in the original checkout against the same unchanged Rust source.
- Clone tests used the existing host Python environment and a copy of local
  vendored langid in the clone's ignored vendor directory. No models or private
  fixtures were copied. This does not demonstrate fresh dependency installation.
- Stable remote `release/v2.0.5-baseline` remained at `703dd5b...`.
  No main, private-history ref, release, tag, force push or merge was published.
- The enclosing final documentation commit records this evidence; its identity
  is available through Git history. Final push/ref and documentation blob equality
  are rechecked after it, without repeating unchanged inference-free code tests.

**SOURCE BACKUP: PASS. FRESH-MACHINE RUNTIME RESTORE: PARTIAL / NOT RUN.**
DEVELOPMENT: PAUSED. Local evidence is retained under the ignored
`dev/github_backup_20261112` directory. No project or backup cleanup was performed.
