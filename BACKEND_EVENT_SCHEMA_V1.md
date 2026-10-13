# Audio2Text Backend Event Schema v1

STATUS: frozen contract for backend **1.5.7**. Transport: UTF-8 JSON Lines over stdout, one object per line, flushed immediately. One process serves one job; no stdin commands, server, GUI, cancellation protocol or concurrent jobs are implemented.

```powershell
venv\Scripts\python.exe -B -X utf8 audio_pipeline_cuda_v157.py --ipc jsonl "input\sample.mp4"
```

Rust launches Python with an argument array and `shell=false`, reads stdout and stderr concurrently, and keeps stderr out of the JSON parser. Do not launch the interactive BAT wrapper for IPC. Startup logs, native output and child process diagnostics are redirected to stderr. A duplicated original stdout handle is reserved for the event writer. Events contain no arbitrary exception text, configuration dumps, request URLs or authentication headers. Current text previews are bounded to 200 characters; they are transcript content and should be handled as user data.

## Envelope

```json
{"schema":1,"event":"stage_progress","timestamp":"2026-10-08T06:22:52.000Z","job_id":"generated-uuid","backend_version":"1.5.7","sequence":18,"stage":"asr","state":"active","completed_units":7,"total_units":22,"remaining_seconds":null}
```

All events contain schema (integer 1), event (documented name), timestamp (UTC ISO 8601 with timezone), job_id (nonempty string, generated UUID per invocation), backend_version (1.5.7), sequence (positive integer, strictly increasing from 1). Sequence, not wall-clock timestamp, defines ordering. Multiple telemetry threads use the same serialized writer. JSON NaN/Infinity and blank lines are forbidden. Unknown optional fields may be ignored. Changes to existing field meaning or enum values require a new schema version.

Optional counters are nonnegative integers or null; completed_units <= total_units when both exist. Remaining time is null until a job has finished. No overall percentage or fabricated ETA is emitted. The frontend can compute only a stage-specific ratio when its denominator is known.

## Event payloads

| Event | Payload and meaning |
|---|---|
| app_ready | designation, journal_schema; accepted startup configuration / control operation |
| job_started | source_name, translation_engine_status; processing begins |
| file_loaded | name, size_bytes, duration_seconds (null until known); source file identified and hashed, not proof of decoded audio |
| stage_started | stage, state=active, completed_units, total_units, remaining_seconds; actual function entry |
| stage_progress | stage, state, counters; waiting initialization or real unit progress |
| stage_completed | stage, state=completed/warning/failed, counters; reused=true identifies completed cached results |
| gpu_status | gpu_name, cuda_available, cuda_active, selected_asr_device, selected_translation_device |
| telemetry | gpu_name, cuda_available, cuda_active, current_stage, telemetry_scope=device, gpu_utilization_percent, vram_used_mb, vram_total_mb; optional sampled_gpu_name |
| language_detected | source_language, reconciled_language (nullable), optional unit_id, reused; emitted from actual unit detection or saved reconciled segments |
| languages_updated | languages (sorted uppercase codes), target_output_channels=[RU, EN], reused |
| speaker_detected | speaker_id, speaker_display, reused |
| speakers_updated | speakers array of speaker_id + speaker_display, reused; authoritative replacement snapshot |
| segment_progress | stage=asr, state, completed_units, total_units, unit=asr_unit, segment_count, reused |
| current_segment | current_stage, current_segment (ASR ID or null), current_semantic_group (group ID or null), current_speaker (internal ID or null), speaker_display, current_source_language, text_preview; optional target_language |
| translation_progress | stage=translation, state=active, counters, unit=channel_record, current_semantic_group, target_language (nullable), remaining_seconds=null; initial reused_units or per-call result |
| export_started | formats=[TXT, JSON, DOCX], counters 0/3 |
| export_completed | files (absolute paths), counters 3/3, journal_schema, block_count; published files now exist |
| warning | code; document_review_required includes review_block_count |
| error | code, optional error_type, retryable; no raw exception dump |
| job_completed | status=PASS; processing success or control operation (`operation=validate_config/help`) |
| job_partial | status=PARTIAL; processing/export finished with review/partial result |
| job_failed | status=ERROR, code; handled failure or interruption |

Successful processing terminal events also contain wall_seconds (inside backend job), inference_calls, cache_reused, block_count, segment_count, files, current_stage=null, remaining_seconds=0, inference_engine_version=1.5.6, translation_engine_status=PARTIAL. `inference_calls` counts prepare_audio, diarization, whisper_detect, whisper_transcribe and nllb_generate. A count records an attempted call; `--require-resume` rejects it before inference and rejects model construction before loading weights.

Normal lifecycle: app_ready → job_started → file_loaded and stage/discovery/progress events → export_completed → warning if relevant → exactly one terminal event. Telemetry may interleave. Setup/argument errors may produce error → job_failed before app_ready/job_started. `--validate-config` and `--help` produce app_ready → job_completed, without processing/export. No events follow a terminal event.

Exit codes: 0 job_completed; 2 job_partial; 1 job_failed; 130 interrupted job_failed. A hard kill, OS crash, lost pipe or interpreter failure before the protocol starts can leave no terminal event; the frontend must show ERROR, never infer success from process exit alone. Closing the pipe is not a supported cancellation API. Existing engine checkpoints retain completed work.

## Stage contract

All stage events contain stage, state, completed_units and total_units, with null where unavailable. Allowed states: waiting, active, completed, warning, failed. Stage IDs are independent of UI language.

| ID | Actual backend work | Unit / progress semantics |
|---|---|---|
| prepare | source validation, hashing, runtime/model metadata, cache lookup | 0/1 then 1/1; no model download |
| extract_audio | existing FFmpeg preparation | unknown while active; 1/1 at return or cached completion |
| diarization | existing pyannote call | unknown while active; 1/1 at return or cached completion |
| language_detection | audio language probes and ASR-unit planning | unknown while active; resulting unit count at return |
| asr | transcribe_unit and actual Whisper calls | completed ASR units / planned units; granular segment_count is separate |
| language_reconciliation | reconcile_unit, including optional existing language retry | completed units / planned units |
| semantic_grouping | existing build_translation_groups | unknown while active; resulting semantic-group count at return |
| translation | existing RU and EN processing | channel records visited/resolved, including source-language bypasses and cached/failed results; not semantic accuracy |
| export | existing atomic TXT/JSON/DOCX publication | 0/3 before publication, 3/3 after success |

ASR and language_reconciliation are interleaved per unit; stage_started can recur for each unit. They are not fictional sequential whole-file phases. A frontend replaces stage state by ID and must not append a new progress bar for every entry. Cached stages can transition waiting → completed directly with reused=true. Reused completion does not mean new inference occurred. Interrupted/incomplete work may show failure with null counters. Group construction and export counts are reported only after those objects/files actually exist.

On the regression document translation has 61 groups and 122 internal target records; EN-source EN bypasses are included. The Journal renders only required channels. Initial translation_progress reports already resolved/skipped records, then actual record completions increment it. Do not label this counter “translated sentences” or “quality percent”.

## CUDA telemetry

Torch supplies availability/name and the selected ASR device. A lightweight `nvidia-smi` subprocess supplies device-wide utilization and VRAM, bounded by a one-second timeout. Metrics are sampled on runtime discovery and every two seconds while the job is running. NVIDIA memory values use MiB despite the compatibility field suffix `_mb`.

cuda_active is true only inside a wrapped Whisper detect/transcribe or NLLB generate call with an explicitly selected CUDA device. It is false during cache/export/CPU work. During frozen pyannote execution it is null because the adapter has no verified placement information. It does not mean GPU utilization is zero or that this process owns all device VRAM.

Unavailable NVIDIA tool, malformed/N/A data, ambiguous multiple GPUs or CUDA_VISIBLE_DEVICES remapping yield null utilization/VRAM. Before Torch discovery, cuda_available/gpu_name may be null. Failure of optional monitoring does not abort transcription. This phase introduces no GPU rendering dependency.

## Validation utility

```powershell
venv\Scripts\python.exe -B -X utf8 dev\validate_ipc_v157.py "input\sample.mp4" --require-resume --name resume
```

The utility launches the real entrypoint with stdout/stderr pipes; checks every stdout line, envelope, names, stage states, sane counters, sequence/job identity, terminal ordering and exit-code agreement; saves JSONL, stderr and summary under dev/validation_v157. The resume guard additionally verifies cache_reused and zero inference calls. It is a developer validator, not a Rust frontend.
