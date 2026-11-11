# A2T-BE-001 — Before and after

Date: 2026-11-11. Private evidence directory: `dev/backend_quality_20261111`. The original control exports remain unchanged. This report distinguishes historical CUDA output, matched CPU experiments and human acceptance.

## Confirmed historical defects

- Original export: 47 segments, 28 semantic groups, RU and EN channels (56 channel records).
- Two Russian groups with GMP/FDA were marked MIXED and could not be translated.
- The last RU-channel record failed without any generation: its raw ASR text was empty.
- Long portions of actual audio produced credit-like fragments. The stored VAD comparison did not recover them.
- The closing slogan was split into short sentences, with incorrect first-phrase meaning and distorted brands.

## Local waveform probes

Same prepared waveform, CPU/int8 Whisper. These counts are candidate recognition results, not certified word-error rates. Timestamp ownership remains within the original unit.

| Unit interval | Original context | Bounded alternative | Words before → after | Alternative runtime |
|---|---|---|---:|---:|
| 00:45.80–01:08.30 | 1-second padding; credit-like fragment | 3 seconds preceding context, no trailing context | 2 → 46 | 13.274 s |
| 03:51.80–04:14.60 | 1-second padding; credit-like fragment | 4-second padding | 1 → 45 | 23.864 s |
| 02:18.65–02:41.20 | Already recognized on CPU | 4-second padding | 40 → 42 | 21.352 s |

The third probe is not claimed as a patch gain: the unchanged CPU path already recovered that historical GPU failure. Four-second context did not fix the first interval; this justified a bounded second attempt. Short windows plus hotwords made results worse and were rejected. VAD was not globally changed.

## NLLB probes

The complete closing slogan with canonical FOHOW/FENDOU produced `One dream, one big team, FOHOW, FENDOU.` on the installed CPU model. The source spelling variants were separately retained. Isolated `Продолжение следует...` still produced the wrong idiom on the model, so an exact, source/target-specific phrase rule is stored in the external glossary; raw model output remains in generation evidence. No rule replaces arbitrary occurrences or rewrites personal names.

## Completed full-video comparison

Real waveform, CPU/int8 ASR and CPU NLLB, target EN. Both arms use fixed reference diarization; final AFTER also uses the BEFORE language plan. Compare ASR plus translation, not total wall time with different language-detection work.

| Measure | BEFORE | AFTER |
|---|---:|---:|
| Recognized segments / semantic groups | 46 / 29 | 52 / 28 |
| Recognized words (not certified reference words) | 508 | 640 |
| MIXED segments | 2 | 0 |
| Selected-channel unsupported_language | 2 | 0 |
| Selected-channel failed | 0 | 0 |
| Selected-channel needs_review / not_required | 26 / 1 | 27 / 1 |
| Journal review blocks | 4 | 7 |
| Known distorted brand variants | 12 | 0 |
| Canonical FOHOW / FENDOU occurrences | 0 / 1 | 22 / 3 |
| Canonical GMP / FDA occurrences | 0 / 0 | 1 / 1 |
| ASR + translation | 494.737 s | 612.392 s |
| Translation alone | 57.993 s | 73.828 s |

**Performance: +23.78% elapsed time. The no-substantial-regression criterion is NOT MET.** One pair is not a statistical benchmark. Actual recovery attempts account for 73.386 s; additional recognized text also increases translation work. Total walls (901.562 s BEFORE, 640.114 s AFTER) must NOT be interpreted as a speedup because final AFTER reuses language detection.

Recovered units: 45.80–68.30 s, 2→46 words; 184.20–208.10 s, 1→45; 231.80–254.60 s, 1→45. Every primary raw piece is archived, and all 19 primary units match BEFORE exactly in this final comparison. Three recovered intervals retain explicit review warnings. More recognized words are not proof that every word is correct or that all missing speech is recovered.

The closing first phrase changes from `It's just a dream. One big team.` to `One dream, one big team.`; canonical FOHOW/FENDOU are present in final translated output. Neither measured arm emits the separate continuation phrase, so its correction is demonstrated by a separate real-model phrase test, not attributed to this full-video export. The central-office interval has substantive speech after recovery; full semantic continuity and proper names still require human review.

Known variants searched: FOHOU, FOCHOU, FOCHAU, FHOC, FENTOO and Phantom. No known distorted form is present AFTER. This is a bounded terminology check, not an unrestricted spelling/semantic proof.

`needs_review` does not decrease: previously unsupported groups now receive actual translations; recovered ASR adds real review obligations. No real warning or human-review requirement was hidden to improve counts. Historical record 28/56 belonged to the RU channel; the matched target-EN experiment does not reproduce that exact route. Empty-source handling is separately tested.

## Export and resume evidence

TXT, JSON and DOCX generated in each isolated evidence directory. All recognized raw characters, hashes, member IDs and group membership pass the existing cache validator. Journal contains only ORI and selected EN. DOCX styles.xml, numbering.xml and theme/theme1.xml hashes match; exporter implementation is unchanged. Visual DOCX acceptance was not run.

AFTER resume passes require_resume with zero prepare_audio, diarization, whisper_detect, whisper_transcribe and nllb_generate calls. Private evidence: `dev/backend_quality_20261111/final_comparison.json`, paired cache/output/events and `after/resume_events.jsonl`. Production input/output/cache remain untouched.

## Real NLLB multilingual regression

One installed CPU NLLB model was exercised BEFORE and AFTER with synthetic AF→RU, NL→RU, EN→RU and ZH→RU inputs. Text and translation status match exactly for all four. Separate RU→EN tests produce `One dream.` and `To be continued.` with original model output retained. Evidence: `translation_regression.json` and `.log`. These are translation tests, not new AF/NL/Chinese audio benchmarks.

**Overall: PARTIAL.** Confirmed mechanism defects improve; performance acceptance and independent human audio/meaning review remain open. No new release, GUI acceptance or CUDA acceptance is claimed.
