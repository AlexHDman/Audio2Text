# Audio2Text project rules

Read `C:\AI\AGENTS.md` and `C:\AI\EXPC_DEVELOPMENT_PROTOCOL.md` before work. Maintain docs/EXPC_CHECKPOINT.md and docs/EXPC_BACKLOG.md.

Baseline: frontend v2.0.5 nightly, frozen backend v1.5.7. Development and interface work are PAUSED after baseline commit. Resume implementation only on explicit user instruction.

Preserve frozen backend hashes, production config, models, input/output and resume caches. Remain headless; no inference or GUI acceptance without task authorization. No commit/push/tag/release without explicit authorization. v2.0.6 experiments are local-only and are not an accepted release.

The Git allowlist excludes private data, installed vendor/model payloads, environment/cache, binaries and local experiments. Never use git add -f to bypass it. Read README.md for excluded runtime prerequisites and validation limitations.
