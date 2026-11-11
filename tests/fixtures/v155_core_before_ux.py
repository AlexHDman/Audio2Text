"""AST-only historical core fixture; never imported or executed.
Extracted verbatim from the pre-UX v155 source. Original full-file SHA256:
2a46073de94941c0c74292eed49a9b3f162c6c1332fb576fbdb027aa7a2baaf9
Only the nine nodes compared by the preservation test are included.
"""

def prepare_audio(source: Path, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("prepared-" + uuid.uuid4().hex + ".wav")
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-af",
        "loudnorm,highpass=f=80,lowpass=f=8000",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(tmp),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode or not tmp.is_file() or tmp.stat().st_size < 44:
            raise PipelineError(
                "FFmpeg не смог подготовить WAV; проверьте формат и доступ к файлу"
            )
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def normalize_diarization(
    output: Any, duration: float
) -> tuple[list[dict], list[dict]]:
    regular = getattr(output, "speaker_diarization", output)
    exclusive = getattr(output, "exclusive_speaker_diarization", None)

    def extract(annotation):
        if not hasattr(annotation, "itertracks"):
            raise PipelineError("pyannote вернула неподдерживаемый output")
        result = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            a, b = max(0.0, float(turn.start)), min(duration, float(turn.end))
            if not math.isfinite(a) or not math.isfinite(b):
                raise PipelineError("pyannote interval is non-finite")
            if b > a:
                result.append({"start": a, "end": b, "speaker_id": str(speaker)})
        return sorted(result, key=lambda x: (x["start"], x["end"], x["speaker_id"]))

    return extract(regular), extract(exclusive) if exclusive is not None else []


def diarize(audio: Any, config: dict, path: Path) -> tuple[list[dict], list[dict]]:
    import torch
    from pyannote.audio import Pipeline

    try:
        pipeline = Pipeline.from_pretrained(str(path / "config.yaml"))
        if pipeline is None:
            raise PipelineError(
                "pyannote model unavailable: проверьте cached gated dependencies"
            )
        options = {"min_speakers": config["MIN_SPEAKERS"]}
        if config["MAX_SPEAKERS"] is not None:
            options["max_speakers"] = config["MAX_SPEAKERS"]
        output = pipeline(
            {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": 16000},
            **options,
        )
        return normalize_diarization(output, len(audio) / 16000)
    except PipelineError:
        raise
    except Exception as error:
        raise PipelineError(
            f"pyannote: {type(error).__name__}; проверьте локальные модели/доступ HF"
        ) from error


def speaker_for(
    start: float, end: float, intervals: list[dict]
) -> tuple[str, list[str]]:
    scores = {}
    for item in intervals:
        overlap = max(0.0, min(end, item["end"]) - max(start, item["start"]))
        if overlap:
            scores[item["speaker_id"]] = scores.get(item["speaker_id"], 0.0) + overlap
    if not scores:
        return "UNKNOWN", []
    ordered = sorted(scores, key=lambda s: (-scores[s], s))
    return ordered[0], ordered if len(ordered) > 1 else []


class WhisperBackend:
    def __init__(self, path: Path, config: dict, runtime: dict):
        from faster_whisper import WhisperModel

        self.config = config
        try:
            self.model = WhisperModel(
                str(path),
                device=runtime["device"],
                compute_type=runtime["compute_type"],
                local_files_only=True,
            )
        except Exception as error:
            raise PipelineError(
                f"Whisper {runtime['device']}: {type(error).__name__}. "
                "Проверьте CUDA/VRAM; CPU запуск: --device cpu"
            ) from error

    def detect(self, audio: Any) -> tuple[str, float]:
        language, probability, _ = self.model.detect_language(
            audio=audio, vad_filter=False
        )
        return language, float(probability)

    def transcribe(self, audio: Any, language: str | None):
        c = self.config
        pieces, info = self.model.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=c["BEAM_SIZE"],
            best_of=c["BEST_OF"],
            temperature=c["TEMPERATURE"],
            vad_filter=c["USE_VAD"],
            vad_parameters={
                "threshold": c["VAD_THRESHOLD"],
                "min_speech_duration_ms": c["VAD_MIN_SPEECH_MS"],
                "min_silence_duration_ms": c["VAD_MIN_SILENCE_MS"],
                "speech_pad_ms": c["VAD_PAD_MS"],
            },
            condition_on_previous_text=c["CONDITION_ON_PREVIOUS_TEXT"],
            repetition_penalty=c["REPETITION_PENALTY"],
            no_repeat_ngram_size=c["NO_REPEAT_NGRAM_SIZE"],
            compression_ratio_threshold=c["COMPRESSION_RATIO_THRESHOLD"],
            log_prob_threshold=c["LOG_PROB_THRESHOLD"],
            no_speech_threshold=c["NO_SPEECH_THRESHOLD"],
            word_timestamps=True,
        )
        return list(pieces), info


def language_units(audio: Any, backend: ASRBackend, config: dict) -> list[dict]:
    units = []

    def visit(start: float, end: float):
        force = config["FORCE_LANGUAGE"]
        probes = []
        if force:
            language, confidence, method, candidate = force, None, "forced", force
        else:
            probe = config["LANGUAGE_PROBE_SECONDS"]
            cursor = start
            while cursor < end - 1e-6:
                stop = min(end, cursor + probe)
                detected = backend.detect(
                    audio[int(cursor * 16000) : int(stop * 16000)]
                )
                probes.append(
                    {
                        "start": cursor,
                        "end": stop,
                        "language": detected[0],
                        "confidence": detected[1],
                    }
                )
                cursor = stop
            threshold = config["LANGUAGE_CONFIDENCE"]
            strong = [item for item in probes if item["confidence"] >= threshold]
            strong_codes = {item["language"] for item in strong}
            minimum = config["MIN_LANGUAGE_UNIT_SECONDS"]
            for left, right in zip(strong, strong[1:]):
                if left["language"] != right["language"] and end - start >= 2 * minimum:
                    cut = min(
                        end - minimum,
                        max(start + minimum, (left["end"] + right["start"]) / 2),
                    )
                    visit(start, cut)
                    visit(cut, end)
                    return
            best = max(probes, key=lambda item: item["confidence"])
            candidate, confidence = best["language"], best["confidence"]
            language = (
                candidate
                if confidence >= threshold and len(strong_codes) == 1
                else "unknown"
            )
            method = "whisper_audio_local"
            if language == "unknown":
                # Use more audio for detection only, never inherit a speaker's language.
                pad = 3.0 if end - start < config["MIN_LANGUAGE_UNIT_SECONDS"] else 0.0
                ca, cb = max(0, start - pad), min(len(audio) / 16000, end + pad)
                context = backend.detect(audio[int(ca * 16000) : int(cb * 16000)])
                probes.append(
                    {
                        "start": ca,
                        "end": cb,
                        "language": context[0],
                        "confidence": context[1],
                        "method": "context",
                    }
                )
                if (
                    context[1] >= threshold
                    and len(strong_codes) < 2
                    and (context[0] == candidate or not strong)
                ):
                    candidate, confidence = context
                    language = candidate
                    method = (
                        "whisper_audio_expanded_context"
                        if pad
                        else "whisper_audio_full_unit"
                    )
        units.append(
            {
                "unit_id": f"u{len(units):05}",
                "start": start,
                "end": end,
                "language": language,
                "language_confidence": confidence,
                "language_method": method,
                "candidate_language": candidate,
                "probes": probes,
                "asr_done": False,
                "segment_ids": [],
                "raw_pieces": [],
            }
        )

    for span in initial_units(audio, config):
        visit(span["start"], span["end"])
    return units


def reconcile_unit(
    unit: dict,
    segments: list[dict],
    units: list[dict],
    index: int,
    audio: Any,
    backend: ASRBackend,
    lid: Any,
    config: dict,
) -> None:
    text = "".join(s["raw_text"] for s in segments)
    evidence = lid.assess(text)
    continuity = (
        0 < index < len(units) - 1
        and units[index - 1]["language"] == units[index + 1]["language"] == "af"
        and unit["end"] - unit["start"] <= 12
    )
    resolved, reason = resolve_text_language(
        unit["language"], evidence, continuity, bool(config["FORCE_LANGUAGE"])
    )
    provenance = {
        "detected_language": unit["language"],
        "text_evidence": evidence,
        "af_neighbors": continuity,
        "resolved_language": resolved,
        "reason": reason,
        "raw_selection": "primary_preserved",
    }
    # Exactly one alternative on a demonstrated conflict or AF/NL continuity.
    # Never replace immutable primary ASR by an alternative merely for fluency.
    alternative_language = (
        resolved
        if resolved != unit["language"]
        else "af"
        if unit["language"] == "nl" and continuity
        else None
    )
    if alternative_language and not config["FORCE_LANGUAGE"]:
        a = max(0, unit["start"] - config["BOUNDARY_PADDING_SECONDS"])
        b = min(len(audio) / 16000, unit["end"] + config["BOUNDARY_PADDING_SECONDS"])
        try:
            pieces, info = backend.transcribe(
                audio[int(a * 16000) : int(b * 16000)], alternative_language
            )
            alt_text = "".join(piece.text for piece in pieces)
            provenance["alternative"] = {
                "requested_language": alternative_language,
                "text_evidence": lid.assess(alt_text),
                "pieces": [
                    {
                        "start": a + x.start,
                        "end": a + x.end,
                        "text": x.text,
                        "tokens": list(x.tokens),
                        "avg_logprob": float(x.avg_logprob),
                    }
                    for x in pieces
                ],
                "info_language": info.language,
            }
        except Exception as error:
            provenance["alternative"] = {
                "requested_language": alternative_language,
                "status": "failed",
                "error_type": type(error).__name__,
            }
            for seg in segments:
                seg["warnings"].append("alternative_language_check_failed")
                seg["transcription_status"] = "needs_review"
    unit["language_reconciliation"] = provenance
    for seg in segments:
        local = lid.assess(seg["raw_text"])
        # Small fragments use their own audio unit's text, never the speaker's language.
        local_safe = local["strong"] and (
            local["language"] == evidence["language"]
            or len(seg["raw_text"].split()) >= 8
            and {local["language"], evidence["language"]} != {"af", "nl"}
        )
        selected = local if local_safe else evidence
        language, why = resolve_text_language(
            seg["language"], selected, continuity, bool(config["FORCE_LANGUAGE"])
        )
        seg.update(
            detected_language=seg["language"],
            detected_language_confidence=seg["language_confidence"],
            resolved_language_score=selected["score"],
            resolved_language=language,
            language=language,
            language_resolution={
                "reason": why,
                "evidence": selected,
                "scope": "segment" if local_safe else "asr_unit",
            },
        )
        seg["corrected_text"] = corrected(seg["raw_text"], language, config)
        if language != seg["detected_language"]:
            seg.setdefault("diagnostics", []).append("audio_text_language_reconciled")
        if (
            why == "insufficient_text_evidence"
            and selected["score"] >= 0.75
            and selected["language"] != seg["language"]
            and len(text.split()) >= 5
        ):
            seg["warnings"].append("uncertain_language_conflict")
            seg["transcription_status"] = "needs_review"
        if continuity and seg["detected_language"] == "nl":
            seg.setdefault("diagnostics", []).append(
                "af_nl_continuity_primary_text_retained"
            )


def transcribe_unit(
    unit: dict,
    audio: Any,
    backend: ASRBackend,
    config: dict,
    intervals: list[dict],
    exclusive: list[dict] | None = None,
) -> list[dict]:
    duration = len(audio) / 16000
    a = max(0.0, unit["start"] - config["BOUNDARY_PADDING_SECONDS"])
    b = min(duration, unit["end"] + config["BOUNDARY_PADDING_SECONDS"])
    candidate = unit["candidate_language"]
    # A low-confidence candidate is explicit in metadata, never a hidden English fallback.
    pieces, info = backend.transcribe(audio[int(a * 16000) : int(b * 16000)], candidate)
    alternative = []
    compare_warning = False
    if config["VAD_COMPARE"] and isinstance(backend, WhisperBackend):
        old_vad = backend.config["USE_VAD"]
        try:
            backend.config["USE_VAD"] = not old_vad
            other, other_info = backend.transcribe(
                audio[int(a * 16000) : int(b * 16000)], candidate
            )
            alternative = [
                {
                    "start": a + x.start,
                    "end": a + x.end,
                    "text": x.text,
                    "tokens": list(x.tokens),
                }
                for x in other
            ]

            def normalized(text):
                return re.sub(r"\W+", "", text.lower())

            compare_warning = normalized(
                " ".join(x.text for x in pieces)
            ) != normalized(" ".join(x.text for x in other))
            unit["vad_comparison"] = {
                "primary_vad": old_vad,
                "alternative_vad": not old_vad,
                "different": compare_warning,
                "alternative_pieces": alternative,
                "alternative_duration_after_vad": float(other_info.duration_after_vad),
            }
        finally:
            backend.config["USE_VAD"] = old_vad
    unit["asr_info"] = {
        "language": info.language,
        "language_probability": float(info.language_probability),
        "duration_after_vad": float(info.duration_after_vad),
    }
    segments = []
    unit["raw_pieces"] = []
    for piece in pieces:
        words = [
            {
                "start": max(0.0, a + w.start),
                "end": min(duration, a + w.end),
                "word": w.word,
                "probability": float(w.probability),
            }
            for w in (piece.words or [])
        ]
        unit["raw_pieces"].append(
            {
                "start": a + piece.start,
                "end": a + piece.end,
                "text": piece.text,
                "tokens": list(piece.tokens),
                "words": words,
                "avg_logprob": float(piece.avg_logprob),
                "no_speech_prob": float(piece.no_speech_prob),
            }
        )
        owned = [
            w
            for w in words
            if unit["start"] <= (w["start"] + w["end"]) / 2 < unit["end"]
            or unit["end"] == duration
            and (w["start"] + w["end"]) / 2 == duration
        ]
        if words:
            groups = []
            for word in owned:
                speaker, _ = speaker_for(
                    word["start"],
                    max(word["end"], word["start"] + 0.001),
                    exclusive or intervals,
                )
                _, overlap = speaker_for(
                    word["start"], max(word["end"], word["start"] + 0.001), intervals
                )
                if groups and groups[-1][0] == speaker:
                    groups[-1][1].append(word)
                    groups[-1][2].update(overlap)
                else:
                    groups.append((speaker, [word], set(overlap)))
            for speaker, group, overlap in groups:
                start = min(unit["end"] - 0.001, max(unit["start"], group[0]["start"]))
                end = min(unit["end"], max(start + 0.001, group[-1]["end"]))
                if end <= start:
                    continue
                text = "".join(w["word"] for w in group)
                segments.append(
                    make_segment(
                        unit,
                        len(segments),
                        start,
                        end,
                        text,
                        speaker,
                        sorted(overlap),
                        config,
                        group,
                    )
                )
            if "".join(w["word"] for w in words).strip() != piece.text.strip():
                unit.setdefault("warnings", []).append(
                    "word_text_mismatch_original_in_raw_pieces"
                )
        elif piece.text.strip():
            # Missing alignment is never silently discarded. Keep raw piece with a warning.
            start, end = (
                max(unit["start"], a + piece.start),
                min(unit["end"], a + piece.end),
            )
            if end <= start:
                start, end = unit["start"], unit["end"]
            speaker, overlap = speaker_for(start, end, intervals)
            segments.append(
                make_segment(
                    unit,
                    len(segments),
                    start,
                    end,
                    piece.text,
                    speaker,
                    overlap,
                    config,
                    warning="missing_word_alignment_context_may_repeat",
                )
            )
    if not segments:
        speaker, overlap = speaker_for(unit["start"], unit["end"], intervals)
        segments.append(
            make_segment(
                unit, 0, unit["start"], unit["end"], "", speaker, overlap, config
            )
        )
    if compare_warning:
        for seg in segments:
            seg.setdefault("diagnostics", []).append("vad_alternative_differs")
    if unit.get("warnings"):
        for seg in segments:
            seg["transcription_status"] = (
                "needs_review" if seg["raw_text"].strip() else "empty"
            )
            seg["warnings"] += unit.get("warnings", [])
    return segments


def build_translation_groups(segments: list[dict]) -> list[dict]:
    groups = []
    for seg in segments:
        previous = groups[-1] if groups else None
        join = previous is not None and (
            previous["language"] == seg["language"]
            and previous["speaker_id"] == seg["speaker_id"] != "UNKNOWN"
            and bool(seg["raw_text"].strip())
            and bool(previous["raw_text"].strip())
            and -0.05 <= seg["start"] - previous["end"] <= 1.25
            and seg["end"] - previous["start"] <= 24
            and not (
                re.search(r"[.!?。！？][\s\"']*$", previous["raw_text"])
                and len(previous["raw_text"].split()) >= 8
            )
        )
        if not join:
            previous = copy.deepcopy(seg)
            previous.update(
                group_id=f"t{len(groups):05}",
                member_ids=[],
                member_spans=[],
                raw_text="",
                chunks=[],
                translation_ru=None,
                translation_corrected_ru=None,
                translation_status="pending",
                warnings=[],
            )
            groups.append(previous)
        start = len(previous["raw_text"])
        previous["raw_text"] += seg["raw_text"]
        previous["member_ids"].append(seg["segment_id"])
        previous["member_spans"].append(
            {
                "segment_id": seg["segment_id"],
                "start": start,
                "end": len(previous["raw_text"]),
            }
        )
        previous["end"] = seg["end"]
        previous["raw_sha256"] = text_hash(previous["raw_text"])
        seg["translation_group_id"] = previous["group_id"]
    return groups
