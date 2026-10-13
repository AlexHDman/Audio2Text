"""Audio2Text frontend contract. No ML imports or inference decisions."""

from __future__ import annotations

import contextlib
import json
import math
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.5.7"
SCHEMA = 1
STAGES = frozenset(
    {
        "prepare",
        "extract_audio",
        "diarization",
        "language_detection",
        "asr",
        "language_reconciliation",
        "semantic_grouping",
        "translation",
        "export",
    }
)
STATES = frozenset({"waiting", "active", "completed", "warning", "failed"})
TERMINAL = frozenset({"job_completed", "job_partial", "job_failed"})
EVENTS = (
    frozenset(
        {
            "app_ready",
            "job_started",
            "file_loaded",
            "stage_started",
            "stage_progress",
            "stage_completed",
            "gpu_status",
            "telemetry",
            "language_detected",
            "languages_updated",
            "speaker_detected",
            "speakers_updated",
            "segment_progress",
            "current_segment",
            "translation_progress",
            "export_started",
            "export_completed",
            "warning",
            "error",
        }
    )
    | TERMINAL
)


@dataclass(frozen=True)
class AppPaths:
    """All runtime paths are rooted explicitly, never in the caller's cwd."""

    root: Path
    code: Path

    @classmethod
    def create(cls, root=None):
        code = Path(__file__).resolve().parent
        return cls(Path(root).resolve() if root else code, code)

    def resolve(self, value):
        p = Path(value)
        p = (self.root / p).resolve() if not p.is_absolute() else p.resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("path_outside_app_root")
        return p

    @property
    def config(self):
        portable = self.root / "_internal/config/config_v157.json"
        return portable if portable.is_file() else self.root / "config_v157.json"

    @property
    def vendor(self):
        return self.code / "vendor/text_lid"

    def defaults(self):
        portable = (self.root / "_internal").is_dir()
        return {
            "INPUT": "input",
            "OUTPUT": "output",
            "TEMP": "_internal/temp/v157" if portable else "temp/v157",
        }


def format_timecode(seconds):
    """Journal display floors seconds; raw floats are never changed."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ValueError("invalid_timecode")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("invalid_timecode")
    total = int(seconds)
    hours = f"{total // 3600:02}" if total >= 3600 else "--"
    return f"{hours}:{total % 3600 // 60:02}:{total % 60:02}"


def speaker_map(data):
    """First chronological appearance, ID tie-break; UNKNOWN never consumes a VOI."""
    first = {}
    for s in data.get("segments", []) + data.get("translation_groups", []):
        sid = s.get("speaker_id", "UNKNOWN")
        if sid != "UNKNOWN":
            first[sid] = min(first.get(sid, float("inf")), s["start"])
    return {
        sid: f"VOI {i + 1}"
        for i, sid in enumerate(sorted(first, key=lambda x: (first[x], x)))
    }


def review_reasons(api, group, segments):
    reasons = set()
    members = [segments[x] for x in group.get("member_ids", [])] or [group]
    if group.get("speaker_id") == "UNKNOWN":
        reasons.add("unknown_speaker")
    for s in members:
        if s.get("language") in {"unknown", "mixed"} or any(
            x in s.get("warnings", [])
            for x in (
                "uncertain_language_conflict",
                "audio_text_language_disagreement",
                "alternative_language_check_failed",
                "mixed_script_review",
            )
        ):
            reasons.add("uncertain_language")
        if s.get("transcription_status") in {"failed", "empty", "unsupported_language"}:
            reasons.add("asr_incomplete")
    for target, rec in (("ru", group), ("en", group.get("english", {}))):
        if target == group["language"]:
            continue
        status = rec.get("translation_status", "pending")
        if status in {
            "failed",
            "partial",
            "pending",
            "disabled",
            "unsupported_language",
        }:
            reasons.add("translation_" + status)
        if "semantic_review_required" in rec.get("warnings", []):
            reasons.add("translation_semantic_review")
        if rec.get("quality", {}).get("flags"):
            reasons.add("translation_quality_review")
        # Preserve explicit future machine reasons; never infer a damaged word from prose.
        for reason in rec.get("review_reasons", []):
            if reason in {
                "damaged_asr_word",
                "translation_omission",
                "translation_retry_exhausted",
            }:
                reasons.add(reason)
    if api.group_needs_review(group, segments) and not reasons:
        reasons.add("translation_quality_review")
    return sorted(reasons)


def journal_document(api, data, config):
    mapping = speaker_map(data)
    segments = {s["segment_id"]: s for s in data.get("segments", [])}
    roles = config.get("SPEAKER_ROLES", {}).get(
        data["source"]["sha256"] + ":" + data["processing_fingerprint"], {}
    )
    blocks = []
    for group in data.get("translation_groups", []):
        language = group["language"]
        channels = {"ORI": group["raw_text"]}
        channel_status = {"ORI": "available"}
        for target, record in (("ru", group), ("en", group.get("english", {}))):
            if config.get("TARGET_LANGUAGE") and target != config["TARGET_LANGUAGE"]:
                continue
            if language == target:
                continue
            channel_status[target.upper()] = record.get("translation_status", "pending")
            text = record.get("translation_" + target)
            if text:
                channels[target.upper()] = text
        reasons = review_reasons(api, group, segments)
        if "asr_incomplete" in reasons or "translation_failed" in reasons:
            status = "ERROR"
        elif any(
            x in reasons
            for x in (
                "translation_partial",
                "translation_pending",
                "translation_disabled",
                "translation_unsupported_language",
                "translation_semantic_review",
            )
        ):
            status = "PARTIAL"
        elif reasons:
            status = "REVIEW"
        else:
            status = "PASS"
        sid = group["speaker_id"]
        blocks.append(
            {
                "block_id": group["group_id"],
                "start_seconds": group["start"],
                "end_seconds": group["end"],
                "start_display": format_timecode(group["start"]),
                "end_display": format_timecode(group["end"]),
                "speaker_id": sid,
                "speaker_display": mapping.get(sid, "UNKNOWN"),
                "speaker_role": roles.get(sid),
                "source_language": language.upper(),
                "detected_languages": sorted(
                    {
                        segments[x]
                        .get("detected_language", segments[x]["language"])
                        .upper()
                        for x in group.get("member_ids", [])
                    }
                ),
                "reconciled_language": language.upper(),
                "channels": channels,
                "channel_status": channel_status,
                "status": status,
                "review_required": bool(reasons),
                "review_reasons": reasons,
                "semantic_validation": group.get("semantic_validation", "unreviewed"),
            }
        )
    # PASS for a block means no concrete issue was flagged, not semantic certification.
    return {
        "schema": SCHEMA,
        "backend_version": VERSION,
        "inference_engine_version": "1.5.6",
        "translation_engine_status": "PARTIAL",
        "translation_engine": "nllb-v156",
        "status": "PARTIAL"
        if any(b["review_required"] for b in blocks)
        or api.exported_status(data) != "complete"
        else "PASS",
        "target_output_channels": [config["TARGET_LANGUAGE"].upper()]
        if config.get("TARGET_LANGUAGE")
        else ["RU", "EN"],
        "languages": sorted({b["source_language"] for b in blocks}),
        "speakers": [
            {"speaker_id": k, "speaker_display": v} for k, v in mapping.items()
        ],
        "blocks": blocks,
    }


def validate_event(event):
    if (
        type(event.get("schema")) is not int
        or event.get("schema") != SCHEMA
        or event.get("backend_version") != VERSION
    ):
        raise ValueError("invalid_envelope")
    if (
        event.get("event") not in EVENTS
        or not isinstance(event.get("job_id"), str)
        or not event["job_id"]
    ):
        raise ValueError("invalid_event")
    if datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("timestamp_requires_timezone")
    if type(event.get("sequence")) is not int or event["sequence"] < 1:
        raise ValueError("invalid_sequence")
    if "stage" in event and event["stage"] not in STAGES:
        raise ValueError("invalid_stage")
    if "state" in event and event["state"] not in STATES:
        raise ValueError("invalid_stage_state")
    if event["event"].startswith("stage_") and not {
        "stage",
        "state",
        "completed_units",
        "total_units",
    }.issubset(event):
        raise ValueError("missing_stage_fields")
    done, total = event.get("completed_units"), event.get("total_units")
    for count in (done, total):
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError("invalid_counter")
    if done is not None and total is not None and done > total:
        raise ValueError("counter_overflow")
    json.dumps(event, allow_nan=False)


class EventStream:
    def __init__(self, stream=None, job_id=None):
        self.stream = stream
        self.job_id = job_id or str(uuid.uuid4())
        self.sequence = 0
        self.terminal = False
        self.lock = threading.RLock()

    def emit(self, event, **payload):
        with self.lock:
            if self.terminal:
                raise ValueError("event_after_terminal")
            self.sequence += 1
            value = {
                **payload,
                "schema": SCHEMA,
                "event": event,
                "timestamp": datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "job_id": self.job_id,
                "backend_version": VERSION,
                "sequence": self.sequence,
            }
            validate_event(value)
            if self.stream is not None:
                self.stream.write(
                    json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
                )
                self.stream.flush()
            self.terminal = event in TERMINAL
            return value


@contextlib.contextmanager
def jsonl_stdout(enabled):
    """Reserve a duplicate stdout pipe; redirect Python, native and child chatter."""
    if not enabled:
        yield None
        return
    sys.stdout.flush()
    saved = os.dup(1)
    sink = os.fdopen(os.dup(saved), "w", encoding="utf-8", buffering=1)
    win = None
    try:
        os.dup2(2, 1)
        if os.name == "nt":
            import ctypes
            import msvcrt

            win = ctypes.windll.kernel32
            win.SetStdHandle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
            win.SetStdHandle(-11 & 0xFFFFFFFF, msvcrt.get_osfhandle(2))
        with contextlib.redirect_stdout(sys.stderr):
            yield sink
    finally:
        sys.stderr.flush()
        os.dup2(saved, 1)
        if win is not None:
            win.SetStdHandle(-11 & 0xFFFFFFFF, msvcrt.get_osfhandle(1))
        os.close(saved)
        sink.close()


def read_gpu_metrics():
    """Device-wide NVIDIA counters. Unavailable/remapped/ambiguous means null."""
    blank = {
        "gpu_utilization_percent": None,
        "vram_used_mb": None,
        "vram_total_mb": None,
    }
    try:
        if os.environ.get("CUDA_VISIBLE_DEVICES"):
            return blank
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        rows = [r.split(",") for r in result.stdout.strip().splitlines()]
        if len(rows) != 1 or len(rows[0]) != 5:
            return blank
        _, name, utilization, used, total = [x.strip() for x in rows[0]]
        values = [float(x) for x in (utilization, used, total)]
        if (
            not all(math.isfinite(x) for x in values)
            or not 0 <= values[0] <= 100
            or not 0 <= values[1] <= values[2]
        ):
            return blank
        return dict(zip(blank, values), sampled_gpu_name=name)
    except Exception:
        return blank


class Telemetry:
    def __init__(self, events, interval=2.0):
        self.events = events
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.gpu_name = None
        self.cuda_available = None
        self.cuda_active = False
        self.current_stage = None

    def sample(self):
        metrics = read_gpu_metrics()
        self.events.emit(
            "telemetry",
            gpu_name=self.gpu_name,
            cuda_available=self.cuda_available,
            cuda_active=self.cuda_active,
            current_stage=self.current_stage,
            telemetry_scope="device",
            **metrics,
        )

    def start(self):
        def work():
            while not self.stop_event.wait(self.interval):
                try:
                    self.sample()
                except Exception:
                    # Optional monitoring must never abort inference.
                    pass

        self.thread = threading.Thread(target=work, name="a2t-telemetry", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
