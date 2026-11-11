# A2T-BE-001 — Backend quality audit

Date: 2026-11-11. Project: Audio2Text CUDA PRO. Branch: `feature/backend-quality`, based on `703dd5b52af8599a9fa17716ffee27967b424401`. Scope: backend quality only, HEADLESS. GUI/assets/DOCX formatting frozen. No commit/push/merge.

## Evidence and preservation

The requested control video and PRO DOCX/TXT/JSON/ZIP were found under project input/output. Video duration: 401.380 seconds; audio: stereo, 44.1 kHz. The published baseline and original exports remain unchanged. A private source/hash snapshot and all raw experiments are under ignored `dev/backend_quality_20261111`. No personal names or source transcript are used as public test fixtures.

The original export contains 47 segments, 28 semantic groups and two translation channels (56 channel records). It is evidence of the defect, not a speech reference. Audio experiments read the actual prepared waveform whose hash is checked against the original job. No human-certified transcript is available; ASR agreement/log probability is not semantic certification.

## Confirmed findings

| Severity | Finding | Exact implementation / evidence |
|---|---|---|
| HIGH | Known Latin terminology incorrectly makes Russian MIXED | `audio_pipeline_cuda_v156.py:script_language`, lines 1167–1182: any two scripts with at least two letters trigger MIXED. Original groups containing GMP/FDA become unsupported in both channels. |
| HIGH | Speech is missing from the recognized text despite a complete unit timeline | `transcribe_unit`, lines 1237–1397. Stored primary and VAD-comparison text both collapse long speech into credit-like phrases. Word ownership preserves timing but cannot recover words Whisper did not emit. |
| HIGH | Equal VAD outputs are not evidence of complete recognition | `transcribe_unit`, lines 1253–1288, compares normalized strings only. The long missing-speech interval has the same defective result in both passes. VAD was already OFF in the production config, with comparison ON; this task does not globally disable it. |
| HIGH | Short phrases and brand names lose context in translation | `semantic_translation_spans`, lines 1468–1479, splits non-English input by sentences. CPU NLLB probe of the complete closing slogan with canonical names preserves FOHOW/FENDOU and improves its first phrase. Individual short fragments in the old result change meaning. |
| MEDIUM | Record 28/56 is an empty ASR tail, not a demonstrated model exception | `translate_segment`, lines 1916–1945: empty non-target input becomes failed. The control record has empty raw text, no generation chunks, source EN. ASR emptiness remains a review issue even when no translation is attempted. |
| MEDIUM | unsupported_language conflates unmapped and unresolved languages | `nllb_source`, lines 1481–1488, and `translate_segment`, lines 1932–1937: unknown/mixed have no NLLB mapping, with no specific reason on the record. No implicit EN fallback is used in this baseline. |
| MEDIUM | No explicit target requests both channels in the legacy CLI | `process`, lines 2506–2532, always constructs RU and EN records; `language_control_v204.py:install` suppresses the unselected channel only when TARGET_LANGUAGE exists. The control export used the legacy dual-channel path. |
| MEDIUM | Incomplete phrases can be separated at the group time limit | `build_translation_groups`, lines 1772–1815: maximum 24 seconds even for an unfinished sentence. Neighboring same-speaker Russian continuations can therefore lose translation context. |

## Findings that are not confirmed defects

- Mass `needs_review` is deliberate: `translate_chunk` around line 1725 and cache validation around lines 584 and 1871 forbid calling an unreviewed translation semantically complete. Technical success and semantic certification must remain distinct. This task removes concrete false warnings, not the human-review contract.
- The current tokenizer explicitly sets and checks source/target NLLB IDs (`Translator.set_language/generate`, lines 1519–1570), uses no input truncation and checks generation caps/EOS. No source-code mapping error for RU/EN/AF/NL was found.
- Source spans and raw hashes are validated; the observed speech gaps are not evidence that cache/export deleted recognized text.
- FFmpeg loudnorm/highpass/lowpass and mono 16 kHz conversion are unchanged. No controlled evidence establishes preprocessing as the cause.
- Names/geography and all translations remain unverified against a human transcript. No automatic personal-name correction is authorized or implemented.

## Candidate implementation

`backend_quality.py` installs narrow policy hooks through the existing `backend_runtime_v157.py` adapter. The v155/v156/v157 entrypoints, frozen inference engine, `translation_v156.py`, pyannote integration and exports remain byte-identical. GUI source, assets and EXE remain untouched.

- A separate `dictionaries/protected_terms.json` stores approved spellings, bounded aliases, context requirements and exact phrase translations. Originals remain immutable; encoder normalization and postprocessing are recorded separately. Ordinary words such as Phantom and unconfirmed personal names are not globally replaced.
- Russian script checks ignore only known Latin terms when audio already indicates RU. Actual English prose or an unknown audio language is not silently reclassified as Russian. Existing manual whitelist reconciliation is preserved.
- A sparse-speech check requires a long unit and substantial diarized speech. Two context retries run without hotwords or changed VAD settings; a third is allowed only to corroborate an already substantive candidate. A replacement requires substantially more words and improved log probability, or agreement between two confident alternative contexts; primary text/pieces and every attempt remain archived. Recovered or unresolved units retain explicit review warnings.
- Short Russian sentence groups share bounded translation context. Longer input and EN/AF/NL/ZH splitting retain the existing paths. A bounded same-speaker/same-language merge joins unfinished Russian continuations without dropping member spans or changing segment timestamps.
- Empty text skips translation while preserving the ASR problem. Unsupported routes get a reason and source/target codes. Missing protected terminology is a generation defect, not an invented replacement.
- Explicit GUI/CLI target choices are retained. The candidate default is a single RU target when none was selected; it does not silently generate EN too.
- Code, terminology and policy hashes enter processing config and therefore both job identity and stage-reuse identity. Old caches remain untouched; incompatible candidate results cannot be reused across the policy boundary.

## Rejected alternatives

Short ASR windows plus canonical hotwords introduced new unrelated phrases in the actual waveform probe. They are not enabled. Symmetric four-second context failed on one sparse unit; the second bounded attempt uses preceding context only. Neither retry is accepted merely because its text is longer. NLLB CUDA remains disabled for these tests. A candidate context-leak regression was reproduced and fixed: terminology context is scoped per record, including AF/NL translation, and restored even after exceptions.

See `BACKEND_QUALITY_VALIDATION.md` and `BACKEND_QUALITY_BEFORE_AFTER.md` for final measured outcomes, limitations and acceptance state.

## Candidate change map

| File / line area | Responsibility | Boundary |
|---|---|---|
| `backend_runtime_v157.py:36,97,246` | Review flags, config policy identity and hook installation | Existing inference primitives and selected language constraints retained |
| `backend_quality.py:21–82` | External terminology validation, context and cache hashes | No personal-name/geography rewrite |
| `backend_quality.py:85–185` | Sparse-speech detection, bounded context recovery and evidence | Original unit ownership, primary pieces and review warnings retained |
| `backend_quality.py:190–228` | Lossless group continuations and short RU context | No formatting or exporter changes |
| `backend_quality.py:232–318` | Translation normalization, evidence, empty handling and diagnostics | NLLB CPU; original text and raw model response preserved |
| `dictionaries/protected_terms.json` | Approved aliases and two exact RU→EN phrases | No generic rewriting or Phantom replacement |
| `tests/test_backend_quality.py` | Policy, confidence, context isolation and preservation regressions | Synthetic fixtures; no private media dependency |

Unchanged: `audio_pipeline_cuda_v155.py`, `audio_pipeline_cuda_v156.py`, `audio_pipeline_cuda_v157.py`, `translation_v156.py`, `language_control_v204.py`, `backend_contract_v1.py`, production config and all GUI files. The candidate adapter intentionally differs from the frozen baseline; it is not a new accepted release.
