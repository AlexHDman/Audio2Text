"""Observation and compatibility adapter for the unchanged v1.5.6 engine."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import patch

from backend_contract_v1 import VERSION, journal_document, speaker_map

ENGINE_SHA256 = "69e8a8172aa24b34413a6b05ba47e919a8cdbae9ad68e692411be53dc16e0e45"
TRANSLATION_SHA256 = "06e262894397fd3dce18ada2d7dc35f13689f075e495db4399c8f86c4a42cb38"


def selected_channel_needs_review(group, segments, target):
    """Same review checks as the frozen exporter, applied only to selected channels.

    An intentionally omitted EN/RU channel must not create a missing-translation
    warning. Source/speaker/ASR issues are still checked independently.
    """
    record = group if target == "ru" else group.get("english", {})
    if record.get("quality", {}).get(
        "flags"
    ) or "semantic_review_required" in record.get("warnings", []):
        return True
    important = {
        "uncertain_language",
        "uncertain_language_conflict",
        "alternative_language_check_failed",
        "speaker_unassigned",
        "empty_asr_audio_retained",
        "mixed_script_review",
        "audio_text_language_disagreement",
        "missing_word_alignment_context_may_repeat",
    }
    members = [segments[sid] for sid in group.get("member_ids", [])] or [group]
    if any(
        s.get("transcription_status") in {"empty", "failed", "unsupported_language"}
        or s.get("speaker_id") == "UNKNOWN"
        or s.get("language") in {"unknown", "mixed"}
        or important.intersection(s.get("warnings", []))
        for s in members
    ):
        return True
    if group["language"] == target:
        return False

    def chunk_issue(chunk):
        if chunk.get("children"):
            return any(chunk_issue(child) for child in chunk["children"])
        return bool(chunk.get("warnings")) or chunk.get("status") in {
            "failed",
            "partial",
            "pending",
        }

    return (
        record.get("translation_status")
        in {"failed", "partial", "pending", "unsupported_language", "disabled"}
        or not record.get("translation_" + target)
        or any(chunk_issue(chunk) for chunk in record.get("chunks", []))
    )


def load_engine(paths):
    import hashlib

    source = paths.code / "audio_pipeline_cuda_v156.py"
    for file, expected in (
        (source, ENGINE_SHA256),
        (paths.code / "translation_v156.py", TRANSLATION_SHA256),
    ):
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError("frozen_engine_hash_mismatch")
    name = "_audio2text_frozen_engine"
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    module.ROOT = paths.root
    module.inside_root = paths.resolve
    return module


def load_config(api, paths, filename=None):
    # Config/legacy dictionaries belong to app_root, code/vendor belongs to code_root.
    if filename is not None and not paths.resolve(filename).is_file():
        raise ValueError("config_not_found")
    with patch.dict(api.DEFAULTS, paths.defaults()):
        config = api.load_config(paths.resolve(filename) if filename else paths.config)
    for key in ("WHISPER_PATH", "TRANSLATOR_PATH", "DIARIZATION_PATH"):
        if config[key] and not Path(config[key]).is_absolute():
            config[key] = str(paths.resolve(config[key]))
    return api.validate_config(config)


class Observer:
    def __init__(self, api, paths, events, telemetry, config, require_resume=False):
        self.api, self.paths, self.events, self.telemetry, self.config = (
            api,
            paths,
            events,
            telemetry,
            config,
        )
        self.require_resume = require_resume
        self.data = None
        self.runtime = {}
        self.languages = set()
        self.speakers = {}
        self.seen_segments = set()
        self.unit_total = None
        self.asr_done = 0
        self.reconciled = 0
        self.translation_done = 0
        self.translation_total = 0
        self.translation_started = False
        self.file_sent = False
        self.reused = False
        self.calls = {
            "prepare_audio": 0,
            "diarization": 0,
            "whisper_detect": 0,
            "whisper_transcribe": 0,
            "nllb_generate": 0,
        }
        self.stack = contextlib.ExitStack()

    def stage(self, event, stage, state, done=None, total=None, **extra):
        if state == "active":
            self.telemetry.current_stage = stage
        elif self.telemetry.current_stage == stage:
            self.telemetry.current_stage = None
        self.events.emit(
            event,
            stage=stage,
            state=state,
            completed_units=done,
            total_units=total,
            remaining_seconds=None,
            **extra,
        )

    def snapshot(self, data, reused=False):
        self.data = data
        units = data.get("units", [])
        self.unit_total = len(units) or None
        self.asr_done = sum(bool(u["asr_done"]) for u in units)
        mapping = speaker_map(data)
        # Cache is complete or checkpoint segments are appended in chronological unit order.
        for sid, display in mapping.items():
            if sid not in self.speakers:
                self.events.emit(
                    "speaker_detected",
                    speaker_id=sid,
                    speaker_display=display,
                    reused=reused,
                )
        if mapping != self.speakers:
            self.speakers = mapping
            self.events.emit(
                "speakers_updated",
                speakers=[
                    {"speaker_id": k, "speaker_display": v} for k, v in mapping.items()
                ],
                reused=reused,
            )
        languages = {s["language"].upper() for s in data.get("segments", [])}
        if languages != self.languages:
            for language in sorted(languages - self.languages):
                self.events.emit(
                    "language_detected",
                    source_language=language,
                    reconciled_language=language,
                    reused=reused,
                )
            self.languages = languages
            self.events.emit(
                "languages_updated",
                languages=sorted(languages),
                target_output_channels=[self.config["TARGET_LANGUAGE"].upper()]
                if self.config.get("TARGET_LANGUAGE")
                else ["RU", "EN"],
                reused=reused,
            )
        added = [
            s
            for s in data.get("segments", [])
            if s["segment_id"] not in self.seen_segments
        ]
        for seg in added:
            self.seen_segments.add(seg["segment_id"])
            # Reused results are discovery snapshots, not claims of current inference.
            if not reused:
                self.events.emit(
                    "current_segment",
                    current_stage="asr",
                    current_segment=seg["segment_id"],
                    current_semantic_group=None,
                    current_speaker=seg["speaker_id"],
                    speaker_display=mapping.get(seg["speaker_id"], "UNKNOWN"),
                    current_source_language=seg["language"].upper(),
                    text_preview=seg["raw_text"][:200],
                )
        if added or reused:
            self.events.emit(
                "segment_progress",
                stage="asr",
                state="completed"
                if units and self.asr_done == len(units)
                else "active",
                completed_units=self.asr_done,
                total_units=self.unit_total,
                unit="asr_unit",
                segment_count=len(data.get("segments", [])),
                reused=reused,
            )

    def count(self, key):
        self.calls[key] += 1
        if self.require_resume:
            raise RuntimeError("resume_requires_inference")

    @contextlib.contextmanager
    def code_root(self):
        previous = self.api.ROOT
        self.api.ROOT = self.paths.code
        try:
            yield
        finally:
            self.api.ROOT = previous

    def hook(self, obj, name, replacement):
        self.stack.enter_context(patch.object(obj, name, replacement))

    def __enter__(self):
        p = self.api
        import translation_v156 as mt
        from language_control_v204 import install

        install(self)
        if self.config.get("TARGET_LANGUAGE"):
            self.hook(
                p,
                "group_needs_review",
                lambda group, segments: selected_channel_needs_review(
                    group, segments, self.config["TARGET_LANGUAGE"]
                ),
            )

        original_source = p.source_identity

        def source_identity(path):
            value = original_source(path)
            if not self.file_sent:
                self.events.emit(
                    "file_loaded",
                    name=path.name,
                    size_bytes=value["size"],
                    duration_seconds=None,
                )
                self.file_sent = True
            return value

        self.hook(p, "source_identity", source_identity)

        original_runtime = p.runtime_info

        def runtime_info(config):
            value = original_runtime(config)
            self.runtime = value
            import torch

            self.telemetry.cuda_available = bool(torch.cuda.is_available())
            self.telemetry.gpu_name = value.get("gpu")
            self.events.emit(
                "gpu_status",
                gpu_name=value.get("gpu"),
                cuda_available=self.telemetry.cuda_available,
                cuda_active=False,
                selected_asr_device=value["device"],
                selected_translation_device=value["translation_device"],
            )
            self.telemetry.sample()
            return value

        self.hook(p, "runtime_info", runtime_info)

        original_meta = p.processing_metadata

        def metadata(*args):
            with self.code_root():
                return original_meta(*args)

        self.hook(p, "processing_metadata", metadata)
        original_lid = p.TextLanguageValidator

        def lid():
            with self.code_root():
                return original_lid()

        self.hook(p, "TextLanguageValidator", lid)

        original_read = p.read_cache

        def read_cache(folder, source, fingerprint):
            data, destination = original_read(folder, source, fingerprint)
            if data is None:
                predecessor = self.paths.resolve("temp/v156") / folder.name
                if predecessor != folder and (predecessor / "resume.json").is_file():
                    candidate, _ = original_read(predecessor, source, fingerprint)
                    if candidate is not None:
                        data = copy.deepcopy(candidate)
                        data["backend_reuse"] = {
                            "from_backend": "1.5.6",
                            "cache": str(predecessor),
                            "state_sha256": candidate["state_sha256"],
                        }
                        data["state_sha256"] = p.digest(
                            {k: v for k, v in data.items() if k != "state_sha256"}
                        )
                        p.validate_cache(data, source, fingerprint)
            self.stage("stage_completed", "prepare", "completed", 1, 1)
            if data is not None:
                self.reused = True
                self.snapshot(data, reused=True)
                self.reconciled = self.asr_done
                if data.get("prepared_sha256"):
                    self.stage(
                        "stage_completed",
                        "extract_audio",
                        "completed",
                        1,
                        1,
                        reused=True,
                    )
                if data["diarization_done"]:
                    self.stage(
                        "stage_completed", "diarization", "completed", 1, 1, reused=True
                    )
                if data["units"]:
                    self.stage(
                        "stage_completed",
                        "language_detection",
                        "completed",
                        len(data["units"]),
                        len(data["units"]),
                        reused=True,
                    )
                if self.unit_total and self.asr_done == self.unit_total:
                    for stage in ("asr", "language_reconciliation"):
                        self.stage(
                            "stage_completed",
                            stage,
                            "completed",
                            self.asr_done,
                            self.unit_total,
                            reused=True,
                        )
                if data.get("translation_groups"):
                    n = len(data["translation_groups"])
                    self.stage(
                        "stage_completed",
                        "semantic_grouping",
                        "completed",
                        n,
                        n,
                        reused=True,
                    )
            return data, destination

        self.hook(p, "read_cache", read_cache)
        original_write = p.atomic_write_json

        def write(path, payload):
            original_write(path, payload)
            if path.name == "resume.json":
                self.snapshot(payload)

        self.hook(p, "atomic_write_json", write)

        def simple_stage(name, stage, count_key=None):
            original = getattr(p, name)

            def call(*args, **kwargs):
                if count_key:
                    self.count(count_key)
                self.stage("stage_started", stage, "active", 0, None)
                # Frozen pyannote does not expose verified placement to this adapter.
                self.telemetry.cuda_active = None if stage == "diarization" else False
                try:
                    value = original(*args, **kwargs)
                    total = (
                        len(value)
                        if stage in {"language_detection", "semantic_grouping"}
                        else 1
                    )
                    if stage == "language_detection":
                        self.unit_total = total
                        for unit in value:
                            self.events.emit(
                                "language_detected",
                                source_language=unit["language"].upper(),
                                reconciled_language=None,
                                unit_id=unit["unit_id"],
                                reused=False,
                            )
                    self.stage("stage_completed", stage, "completed", total, total)
                    return value
                except Exception:
                    self.stage("stage_completed", stage, "failed", None, None)
                    raise
                finally:
                    self.telemetry.cuda_active = False

            self.hook(p, name, call)

        simple_stage("prepare_audio", "extract_audio", "prepare_audio")
        simple_stage("diarize", "diarization", "diarization")
        simple_stage("language_units", "language_detection")
        simple_stage("build_translation_groups", "semantic_grouping")

        original_transcribe = p.WhisperBackend.transcribe

        for cls in (p.WhisperBackend, p.Translator):
            original_init = cls.__init__

            def init(instance, *args, _original=original_init, **kwargs):
                if self.require_resume:
                    raise RuntimeError("resume_requires_model_load")
                return _original(instance, *args, **kwargs)

            self.hook(cls, "__init__", init)

        original_detect = p.WhisperBackend.detect

        def detect(instance, *args, **kwargs):
            self.count("whisper_detect")
            self.telemetry.cuda_active = self.runtime.get("device") == "cuda"
            try:
                return original_detect(instance, *args, **kwargs)
            finally:
                self.telemetry.cuda_active = False

        self.hook(p.WhisperBackend, "detect", detect)

        def whisper(instance, *args, **kwargs):
            self.count("whisper_transcribe")
            self.telemetry.cuda_active = self.runtime.get("device") == "cuda"
            try:
                return original_transcribe(instance, *args, **kwargs)
            finally:
                self.telemetry.cuda_active = False

        self.hook(p.WhisperBackend, "transcribe", whisper)
        original_generate = p.Translator.generate

        def generate(instance, *args, **kwargs):
            self.count("nllb_generate")
            self.telemetry.cuda_active = instance.device == "cuda"
            try:
                return original_generate(instance, *args, **kwargs)
            finally:
                self.telemetry.cuda_active = False

        self.hook(p.Translator, "generate", generate)

        for name, stage in (
            ("transcribe_unit", "asr"),
            ("reconcile_unit", "language_reconciliation"),
        ):
            original = getattr(p, name)

            def unit_call(*args, _original=original, _stage=stage, **kwargs):
                unit = args[0]
                done = self.asr_done if _stage == "asr" else self.reconciled
                self.stage(
                    "stage_started",
                    _stage,
                    "active",
                    done,
                    self.unit_total,
                    current_unit=unit["unit_id"],
                )
                try:
                    value = _original(*args, **kwargs)
                    if _stage == "language_reconciliation":
                        self.reconciled += 1
                    self.stage(
                        "stage_progress", _stage, "active", done + 1, self.unit_total
                    )
                    if done + 1 == self.unit_total:
                        self.stage(
                            "stage_completed",
                            _stage,
                            "completed",
                            done + 1,
                            self.unit_total,
                        )
                    return value
                finally:
                    self.telemetry.cuda_active = False

            self.hook(p, name, unit_call)

        original_route = mt.prepare_routing

        def route(api, data, config):
            value = original_route(api, data, config)
            self.data = data
            self.translation_total = len(data["translation_groups"]) * 2
            records = [g for g in data["translation_groups"]] + [
                g.get("english", {}) for g in data["translation_groups"]
            ]
            self.translation_done = sum(not self.eligible(r) for r in records)
            self.translation_started = True
            self.stage(
                "stage_started",
                "translation",
                "active",
                self.translation_done,
                self.translation_total,
                unit="channel_record",
                reused_units=self.translation_done,
            )
            self.events.emit(
                "translation_progress",
                stage="translation",
                state="active",
                completed_units=self.translation_done,
                total_units=self.translation_total,
                unit="channel_record",
                reused_units=self.translation_done,
                current_semantic_group=None,
                target_language=None,
                remaining_seconds=None,
            )
            return value

        self.hook(mt, "prepare_routing", route)

        def translation_wrapper(original, afnl):
            def call(*args, **kwargs):
                rec = args[1] if afnl else args[0]
                target = kwargs.get(
                    "target",
                    kwargs.get(
                        "target_language",
                        args[-1] if isinstance(args[-1], str) else "ru",
                    ),
                )
                group = next(
                    (
                        g
                        for g in self.data["translation_groups"]
                        if rec is g or rec is g.get("english")
                    ),
                    None,
                )
                self.telemetry.current_stage = "translation"
                self.events.emit(
                    "current_segment",
                    current_stage="translation",
                    current_segment=None,
                    current_semantic_group=group["group_id"] if group else None,
                    current_speaker=group["speaker_id"] if group else None,
                    speaker_display=self.speakers.get(group["speaker_id"], "UNKNOWN")
                    if group
                    else None,
                    current_source_language=rec["language"].upper(),
                    target_language=target.upper(),
                    text_preview=rec["raw_text"][:200],
                )
                try:
                    value = original(*args, **kwargs)
                    self.translation_done += 1
                    self.events.emit(
                        "translation_progress",
                        stage="translation",
                        state="active",
                        completed_units=self.translation_done,
                        total_units=self.translation_total,
                        unit="channel_record",
                        target_language=target.upper(),
                        current_semantic_group=group["group_id"] if group else None,
                        result=rec["translation_status"],
                        remaining_seconds=None,
                    )
                    return value
                finally:
                    self.telemetry.cuda_active = False

            return call

        self.hook(
            p, "translate_segment", translation_wrapper(p.translate_segment, False)
        )
        self.hook(mt, "translate_group", translation_wrapper(mt.translate_group, True))

        original_export = p.export_all

        def export(data, config, out):
            payload = copy.deepcopy(data)
            payload["backend_version"] = VERSION
            payload["journal"] = journal_document(p, data, config)
            # Display version only: inference/cache identity intentionally stays 1.5.6.
            with patch.object(p, "VERSION", VERSION):
                return original_export(payload, config, out)

        self.hook(p, "export_all", export)
        original_publish = p.publish_exports

        def publish(data, config, out):
            self.snapshot(data)
            journal = journal_document(p, data, config)
            if self.translation_started:
                self.stage(
                    "stage_completed",
                    "translation",
                    "warning" if journal["status"] != "PASS" else "completed",
                    self.translation_done,
                    self.translation_total,
                    unit="channel_record",
                )
            self.stage("stage_started", "export", "active", 0, 3)
            self.events.emit(
                "export_started",
                formats=["TXT", "JSON", "DOCX"],
                completed_units=0,
                total_units=3,
            )
            files = original_publish(data, config, out)
            self.stage("stage_completed", "export", "completed", len(files), 3)
            self.events.emit(
                "export_completed",
                files=[str(f) for f in files],
                completed_units=len(files),
                total_units=3,
                journal_schema=1,
                block_count=len(journal["blocks"]),
            )
            return files

        self.hook(p, "publish_exports", publish)
        return self

    def eligible(self, rec):
        return (
            rec.get("translation_status", "pending") == "pending"
            or any(self.api.pending_chunk(ch) for ch in rec.get("chunks", []))
            or self.retry_translation
            and rec.get("translation_status") in {"failed", "partial"}
        )

    retry_translation = False

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)


def run_job(
    api, paths, events, telemetry, config, source, *, require_resume=False, **options
):
    start = time.perf_counter()
    events.emit(
        "job_started",
        source_name=Path(source).name,
        translation_engine_status="PARTIAL",
    )
    from backend_contract_v1 import STAGES

    for stage in sorted(STAGES):
        events.emit(
            "stage_progress",
            stage=stage,
            state="waiting",
            completed_units=None,
            total_units=None,
            remaining_seconds=None,
        )
    telemetry.start()
    with Observer(api, paths, events, telemetry, config, require_resume) as observer:
        observer.retry_translation = options.get("retry_translation", False)
        observer.stage("stage_started", "prepare", "active", 0, 1)
        try:
            data, files = api.process(paths.resolve(source), config, **options)
            document = journal_document(api, data, config)
            telemetry.stop()
            status = "PARTIAL" if document["status"] != "PASS" else "PASS"
            if status == "PARTIAL":
                events.emit(
                    "warning",
                    code="document_review_required",
                    review_block_count=sum(
                        b["review_required"] for b in document["blocks"]
                    ),
                )
            events.emit(
                "job_partial" if status == "PARTIAL" else "job_completed",
                status=status,
                translation_engine_status="PARTIAL",
                inference_engine_version="1.5.6",
                wall_seconds=time.perf_counter() - start,
                inference_calls=observer.calls,
                cache_reused=observer.reused,
                block_count=len(document["blocks"]),
                segment_count=len(data["segments"]),
                files=[str(f) for f in files],
                current_stage=None,
                remaining_seconds=0,
            )
            return 2 if status == "PARTIAL" else 0
        except Exception:
            observer.stage(
                "stage_completed",
                telemetry.current_stage or "prepare",
                "failed",
                None,
                None,
            )
            raise
        finally:
            telemetry.stop()
