# Audio2Text v1.5.7 Backend Freeze

STATUS: **Backend Freeze**, final 1.x backend baseline for Audio2Text 2.x. Translation engine remains **PARTIAL**. This phase adds a presentation/observation boundary and does not improve or retrain NLLB.

## Boundary and ownership

```text
Future Rust Audio2Text.exe
  -> launch Python with argument array, read JSONL stdout + diagnostics stderr
  -> audio_pipeline_cuda_v157.py
  -> backend_contract_v1.py + backend_runtime_v157.py
  -> unchanged audio_pipeline_cuda_v156.py + translation_v156.py
  -> FFmpeg / faster-whisper / pyannote / NLLB
```

Rust is the presentation/orchestration layer. Python owns inference, audio preparation, diarization, speaker assignment, language decisions, semantic grouping, dictionaries, translation, cache and publication. Rust consumes schema 1 events and exported `journal`; it never parses console prose, debug/cache structures or NLLB-specific attempts.

The adapter loads an isolated instance of the accepted engine, observes real function boundaries/checkpoints, and restores all hooks at job end. It is single-job, single-process; concurrent jobs must use separate Python processes. No monkey-patch is applied to the source files. SHA-256 pins reject modified frozen engine/helper files before running:

- audio_pipeline_cuda_v156.py: `69e8a8172aa24b34413a6b05ba47e919a8cdbae9ad68e692411be53dc16e0e45`
- translation_v156.py: `06e262894397fd3dce18ada2d7dc35f13689f075e495db4399c8f86c4a42cb38`

Backend/public display version is **1.5.7**. The legacy `pipeline_version=1.5.6` inside cache/export denotes the frozen inference engine identity. It deliberately remains unchanged to preserve compatible cache fingerprints. JSON adds backend_version=1.5.7 and journal.backend_version=1.5.7; TXT/DOCX title displays 1.5.7. No source/decoding/model settings are changed.

## Journal schema 1

JSON export retains every existing field and checksum behavior, adding `journal`:

```json
{
  "schema": 1,
  "backend_version": "1.5.7",
  "inference_engine_version": "1.5.6",
  "translation_engine": "nllb-v156",
  "translation_engine_status": "PARTIAL",
  "status": "PARTIAL",
  "target_output_channels": ["RU", "EN"],
  "languages": ["AF", "EN", "NL"],
  "speakers": [{"speaker_id":"SPEAKER_00","speaker_display":"VOI 1"}],
  "blocks": [{
    "block_id": "t00017",
    "start_seconds": 83.2,
    "end_seconds": 90.1,
    "start_display": "--:01:23",
    "end_display": "--:01:30",
    "speaker_id": "SPEAKER_00",
    "speaker_display": "VOI 1",
    "speaker_role": null,
    "source_language": "AF",
    "detected_languages": ["AF"],
    "reconciled_language": "AF",
    "channels": {"ORI":"source text","RU":"Russian text","EN":"English text"},
    "channel_status": {"ORI":"available","RU":"needs_review","EN":"needs_review"},
    "status": "REVIEW",
    "review_required": true,
    "review_reasons": ["translation_quality_review"],
    "semantic_validation": "unreviewed"
  }]
}
```

This is an illustrative schema example, not a transcript quotation. Block IDs reuse stable semantic group IDs. Raw numeric timestamps and exact original strings (including original whitespace) are preserved. source_language/reconciled_language come from the existing resolved group label; detected_languages derives from member ASR evidence. Codes are uppercase stable short codes: RU, EN, AF, NL, ZH, DE, FR, IT, HE, ZU; UNKNOWN/MIXED remain explicit when present. Listing ZU does not add Zulu ASR support to Whisper.

VOI = voice/speaker display identity, ORI = source text, RU/EN = target channels. Known speakers are ordered by first chronological occurrence, with internal ID as a tie-break, and assigned VOI 1, VOI 2, etc. UNKNOWN remains UNKNOWN and consumes no number. Internal IDs are unchanged. Numbering is deterministic for one document; it is not a cross-document biometric identity. Discovery snapshots may update the mapping as evidence arrives. speaker_role is a separate optional configured field.

| Source | Visible channels when available |
|---|---|
| Other than RU/EN | ORI, RU, EN |
| EN | ORI, RU |
| RU | ORI, EN |

Missing/failed translations are omitted from `channels`; `channel_status` still identifies the expected target and its backend state. Empty duplicate channels are never inserted. Channel statuses preserve the engine enum: pending, complete, partial, needs_review, not_required, disabled, unsupported_language, failed; ORI uses available. Dictionary overlays remain in legacy JSON/export fields, never replace Journal ORI. No verbose translation labels enter this model.

`backend_contract_v1.format_timecode` is the sole new Journal time formatter: floor to whole seconds for display, `--` hours below 3600, otherwise at least two digits. Examples: 8 → --:00:08; 83.2 → --:01:23; 2835 → --:47:15; 3683 → 01:01:23. Raw floats are untouched. Negative/non-finite/bool inputs are rejected. Existing TXT/DOCX time formatting remains frozen for compatibility; Rust should render provided display fields rather than implement another formatter.

## Review and semantic truth

Journal block status is a presentation classification:

- ERROR: failed translation or incomplete/failed/unsupported ASR.
- PARTIAL: partial/pending/disabled/unsupported target, or explicit translation_semantic_review.
- REVIEW: another concrete issue is present.
- PASS: no concrete issue was flagged. **This does not certify translation semantics.** semantic_validation separately preserves reviewed/unreviewed.

Machine review_reasons include unknown_speaker, uncertain_language, asr_incomplete, translation_failed, translation_partial, translation_pending, translation_disabled, translation_unsupported_language, translation_semantic_review, translation_quality_review. Future explicit damaged_asr_word, translation_omission, translation_retry_exhausted metadata is passed through only if already present, never guessed by scanning prose or a particular word. Fine-grained legacy diagnostics remain available in the full JSON.

General engineering warnings (for example the frozen Zulu support notice) do not mark every block as review-required. The accepted regression document retains 14 concretely flagged blocks and a PARTIAL terminal state. Existing generic needs_review also prevents a document from being falsely advertised as semantically complete. `translation_engine_status=PARTIAL` is a capability limitation independent of each block's flag.

## Translation replacement boundary

Existing v156 translation architecture/NLLB is frozen. Known AF/NL semantic errors, damaged source words/pronouns, and koosmaak remain. No substitution, language rewrite or extra inference was introduced in v157.

A future engine adapter must consume group ID, exact raw source, resolved language and configured targets, and return independent target text/status/review metadata. It must retain original text, stable block/speaker/timestamp fields, bounded progress and standard events. Its internal tokens/prompts/model details stay outside Journal/schema 1. Replacing it is a separate backend release; Rust UI, event envelope, speaker model and Journal renderer need no redesign. A new engine/model/policy gets a new translation cache identity, never silently reuses incompatible translations.

## Cache and publication

Default writes use temp/v157. On a cache miss, a checksum-valid matching temp/v156 cache is copied in memory into the v157 run; its exact inference processing fingerprint, source identity, settings, model metadata, library versions and raw state must validate. backend_reuse records provenance. The predecessor is not rewritten. Current cache uses unchanged schema v2 and unchanged inference identity. Frontend-only code changes do not invalidate AI results. --fresh and --retry-translation preserve existing engine semantics. --require-resume rejects model loading/audio work/inference and is intended for regression checks, not normal processing.

TXT/JSON/DOCX publish directly under output, with existing `_PRO` names and atomic rollback behavior. Existing shared publication lock/staging under temp/v156-publication is retained to serialize writes with rollback versions; it is technical storage, never an output subdirectory. DOCX layout, colors, ORIGINAL/RU/EN labels and raw time display remain accepted v156 UX. New Journal terminology/timecodes are additive JSON fields.

## Paths and future portable package

`AppPaths` centralizes app_root, code_root, config lookup and bounded runtime resolution. Default app_root is the code directory; explicit `--app-root` is resolved independently of working directory. Relative input/output/temp/dictionary/config paths resolve under app_root; escapes are rejected. Config-relative model overrides resolve under app_root, while explicit absolute model overrides retain developer compatibility. Code/vendor resources resolve under code_root even when runtime root differs.

When `_internal/config/config_v157.json` exists it is the default config; otherwise app_root/config_v157.json is used. Portable defaults put TEMP under `_internal/temp/v157`. An existing `_internal/ffmpeg/ffmpeg.exe` is prepended to PATH. An existing `_internal/models/huggingface` becomes HF_HOME/HF_HUB_CACHE for that process; otherwise the existing developer HF cache is retained. No downloads, installation or asset relocation occur.

Future package layout:

```text
Audio2Text_Portable/
  Audio2Text.exe
  input/
  output/
  _internal/
    app/ runtime/ models/ ffmpeg/ config/ cache/ temp/ logs/ assets/
```

This is a path contract, not a portable build. The future launcher supplies app_root, Python executable and config. Current cache source/model identities include resolved paths, so moving to another drive is not promised to reuse old cache. Physical portable execution from another drive remains NOT TESTED and belongs to the package phase.

## Visual master and next major version

Source of truth: `C:\AI\Audio2Text\assets\UI_Master_Visual.png` (portable reference: app_root/assets/UI_Master_Visual.png until packaging mapping is finalized). Audio2Text 2.x is a compact single-page dashboard: dark bioluminescent technical noir, living interface, real process visualization, no fake telemetry/progress.

Future orb flow, stage pulse, CUDA glow, waveform, ambient animation, forest-style soundscape and hover sparks belong to the frontend. Processing-related effects must respond to real backend events. This phase creates no Rust executable, Slint/egui/wgpu experiment, animation or audio effect.

Next: **v2.0 — Rust Living Interface**, against this contract. Old v154/v155/v156 files, caches, validation materials and rollback assets remain. Cleanup waits until portable acceptance from another drive. No commit/push/tag/release.
