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
- Publication tree: **110 files**, approximately **5.13 MiB**, including required
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

Pending the authorized push and independent fresh-clone comparison. The final
verification entry will identify the source commit and exact scope tested.
