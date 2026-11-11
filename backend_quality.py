"""BE-001 candidate policy around immutable v1.5.6 inference primitives.

No model, raw ASR text, GUI selection or predecessor cache is rewritten.
"""

from __future__ import annotations

import copy
import contextlib
import difflib
import hashlib
import json
import re
import time
from pathlib import Path

POLICY = "be001-quality-1"


class Terminology:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.data = json.loads(raw)
        if self.data.get("version") != 1 or not isinstance(self.data.get("terms"), list):
            raise ValueError("invalid_protected_terminology")
        self.entries = []
        seen = set()
        for entry in self.data["terms"]:
            values = [entry["canonical"], *entry["aliases"]]
            if not all(isinstance(v, str) and v.strip() for v in values):
                raise ValueError("invalid_terminology_entry")
            for value in values:
                if value.casefold() in seen:
                    raise ValueError("ambiguous_terminology_alias")
                seen.add(value.casefold())
            pattern = r"(?<!\w)(?:" + "|".join(
                re.escape(v) for v in sorted(values, key=len, reverse=True)
            ) + r")(?!\w)"
            self.entries.append((entry, re.compile(pattern, re.IGNORECASE)))

    def normalize(self, text, context=""):
        # An approved spelling is always retained; variants require domain context.
        corpus = (context + " " + text).casefold()
        domain = any(w.casefold() in corpus for w in self.data["context_words"])
        changes = []
        for entry, pattern in self.entries:
            def replace(match):
                original = match.group()
                canonical = entry["canonical"]
                if entry["context_required"] and not domain and original.casefold() != canonical.casefold():
                    return original
                if original != canonical:
                    changes.append({"original": original, "canonical": canonical})
                return canonical
            text = pattern.sub(replace, text)
        return text, changes

    def script_text(self, text):
        # Mask only approved Latin spellings/aliases, never arbitrary Latin prose.
        for entry, pattern in self.entries:
            text = pattern.sub(lambda m: " " if m.group().isascii() else m.group(), text)
        return text

    def expected(self, text):
        return [e["canonical"] for e, _ in self.entries if re.search(
            r"(?<!\w)" + re.escape(e["canonical"]) + r"(?!\w)", text, re.IGNORECASE)]

    def exact_phrase(self, text, source, target):
        key = re.sub(r"[.!?…]+$", "", text.strip()).strip().casefold()
        return next((p["translation"] for p in self.data.get("exact_phrases", [])
                     if (p["source"], p["target"], p["text"].casefold()) == (source, target, key)), None)


def configure(config, code_root):
    terms = Terminology(Path(code_root) / "dictionaries/protected_terms.json")
    config["BACKEND_QUALITY"] = {
        "policy": POLICY,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "terminology_sha256": terms.sha256,
    }
    return config


def sparse_speech(unit, segments, intervals):
    duration = unit["end"] - unit["start"]
    words = len(re.findall(r"\w+", " ".join(s["raw_text"] for s in segments)))
    # Diarization is evidence of speech, not its linguistic content. Union overlaps.
    spans = sorted((max(unit["start"], p["start"]), min(unit["end"], p["end"]))
                   for p in intervals if p["end"] > unit["start"] and p["start"] < unit["end"])
    covered, end = 0.0, unit["start"]
    for a, b in spans:
        covered += max(0, b - max(a, end))
        end = max(end, b)
    return duration >= 12 and covered >= duration * 0.5 and words < duration * 0.35


def recovery_better(primary, alternative, old_pieces, new_pieces):
    old_words = len(re.findall(r"\w+", " ".join(s["raw_text"] for s in primary)))
    new_words = len(re.findall(r"\w+", " ".join(s["raw_text"] for s in alternative)))
    def score(pieces):
        weights = [max(1, len(p["text"].split())) for p in pieces]
        return sum(p["avg_logprob"] * w for p, w in zip(pieces, weights)) / max(1, sum(weights))
    return (new_words >= max(12, old_words * 3) and new_pieces and old_pieces
            and score(new_pieces) > score(old_pieces) + 0.12)


def recovery_agreement(primary, first, second):
    """Corroborate a long recovery across context boundaries; never certify meaning."""
    words = lambda rows: re.findall(r"\w+", " ".join(s["raw_text"] for s in rows).casefold())
    old, left, right = words(primary), words(first), words(second)
    return (min(len(left), len(right)) >= max(12, 3 * len(old))
            and difflib.SequenceMatcher(a=left, b=right, autojunk=False).ratio() >= 0.85)


def install(observer):
    api, config = observer.api, observer.config
    terms = Terminology(observer.paths.code / "dictionaries/protected_terms.json")
    original_script = api.script_language

    def script_language(text, detected, forced):
        return original_script(terms.script_text(text) if detected == "ru" else text, detected, forced)

    observer.hook(api, "script_language", script_language)
    original_corrected = api.corrected

    def corrected(text, language, cfg):
        value = original_corrected(text, language, cfg)
        return terms.normalize(value)[0]

    observer.hook(api, "corrected", corrected)
    original_transcribe = api.transcribe_unit

    def transcribe(unit, audio, backend, cfg, intervals, exclusive=None):
        primary = original_transcribe(unit, audio, backend, cfg, intervals, exclusive)
        if not sparse_speech(unit, primary, intervals):
            return primary
        original_unit = copy.deepcopy(unit)
        attempts = []
        selected = primary
        corroboration = None
        for padding, trailing in [(4.0, True), (3.0, False), (6.0, True)]:
            if padding == 6.0 and corroboration is None:
                break  # Third pass is only for corroborating a substantive candidate.
            trial = copy.deepcopy(original_unit)
            options = {**cfg, "BOUNDARY_PADDING_SECONDS": padding, "VAD_COMPARE": False}
            # Cropping affects detection context only; word ownership stays in unit.
            sample = audio if trailing else audio[:int(unit["end"] * 16000)]
            started = time.perf_counter()
            try:
                alternative = original_transcribe(trial, sample, backend, options, intervals, exclusive)
                accepted = (not sparse_speech(unit, alternative, intervals) and recovery_better(
                    primary, alternative, original_unit["raw_pieces"], trial["raw_pieces"]))
                corroborated = (corroboration is not None and not sparse_speech(unit, alternative, intervals)
                                and recovery_agreement(primary, corroboration, alternative))
                # Agreement needs actual speech confidence too; no blind longest text.
                if corroborated:
                    corroborated = all(p.get("no_speech_prob", 1) < cfg["NO_SPEECH_THRESHOLD"] and p["avg_logprob"] > -.25
                                       for p in trial["raw_pieces"])
                accepted = accepted or corroborated
                attempts.append({"padding": padding, "trailing_context": trailing,
                                 "seconds": time.perf_counter() - started,
                                 "raw_pieces": trial["raw_pieces"], "segments": alternative,
                                 "selected": bool(accepted), "corroborated": bool(corroborated)})
                if accepted:
                    selected = alternative
                    unit["raw_pieces"] = trial["raw_pieces"]
                    unit["asr_info"] = trial["asr_info"]
                    break
                if (not sparse_speech(unit, alternative, intervals)
                        and all(p.get("no_speech_prob", 1) < cfg["NO_SPEECH_THRESHOLD"] and p["avg_logprob"] > -.25
                                for p in trial["raw_pieces"])):
                    corroboration = alternative
            except Exception as error:
                attempts.append({"padding": padding, "trailing_context": trailing,
                                 "error_type": type(error).__name__, "selected": False})
        recovered = selected is not primary
        unit["quality_recovery"] = {"policy": POLICY, "primary_segments": copy.deepcopy(primary),
                                    "primary_raw_pieces": original_unit["raw_pieces"],
                                    "attempts": attempts, "recovered": recovered,
                                    "semantic_validation": "unreviewed"}
        for row in selected:
            row["transcription_status"] = "needs_review" if row["raw_text"].strip() else "empty"
            row["warnings"].append("asr_context_recovered_review" if recovered else "sparse_speech_unresolved")
        return selected

    observer.hook(api, "transcribe_unit", transcribe)
    original_groups = api.build_translation_groups

    def groups(segments):
        values = original_groups(segments)
        merged = []
        for value in values:
            prev = merged[-1] if merged else None
            if (prev and prev["language"] == value["language"] == "ru"
                    and prev["speaker_id"] == value["speaker_id"] != "UNKNOWN"
                    and 0 <= value["start"] - prev["end"] <= 1.25
                    and value["end"] - prev["start"] <= 40
                    and prev["raw_text"].strip() and value["raw_text"].strip()
                    and not re.search(r'[.!?。！？][\s"\']*$', prev["raw_text"])
                    and value["raw_text"].lstrip()[0].islower()):
                offset = len(prev["raw_text"])
                prev["raw_text"] += value["raw_text"]
                prev["raw_sha256"] = api.text_hash(prev["raw_text"])
                prev["end"] = value["end"]
                prev["member_ids"] += value["member_ids"]
                prev["member_spans"] += [{**span, "start": span["start"] + offset,
                                           "end": span["end"] + offset} for span in value["member_spans"]]
            else:
                merged.append(value)
        by_id = {s["segment_id"]: s for s in segments}
        for index, value in enumerate(merged):
            value["group_id"] = f"t{index:05}"
            for sid in value["member_ids"]:
                by_id[sid]["translation_group_id"] = value["group_id"]
        return merged

    observer.hook(api, "build_translation_groups", groups)
    original_spans = api.semantic_translation_spans

    def spans(text, count, budget, language):
        parts = api.sentence_spans(text)
        if (language == "ru" and len(parts) > 1
                and all(len(text[a:b].split()) <= 6 for a, b in parts)
                and count(text) <= min(64, budget)):
            return [(0, len(text))]
        return original_spans(text, count, budget, language)

    observer.hook(api, "semantic_translation_spans", spans)
    original_generate, original_count = api.Translator.generate, api.Translator.count

    def count(instance, text):
        normalized, _ = terms.normalize(text, getattr(instance, "quality_context", ""))
        return original_count(instance, normalized)

    def generate(instance, text):
        context = getattr(instance, "quality_context", "")
        normalized, changes = terms.normalize(text, context)
        result = original_generate(instance, normalized)
        result["encoder_text"] = normalized
        result["terminology_changes"] = changes
        # Keep generated text/IDs as evidence when an explicit phrase rule applies.
        source = getattr(instance, "quality_source_language", None)
        exact = terms.exact_phrase(text, source, instance.target_language)
        value, output_changes = terms.normalize(result["text"], normalized)
        expected = terms.expected(normalized)
        # Only source-supported term corrections may touch generated output.
        if output_changes and any(c["canonical"] not in expected for c in output_changes):
            value = result["text"]
        if exact or value != result["text"]:
            result["model_text"] = result["text"]
            result["text"] = exact or value
            result["postprocess"] = "exact_phrase_glossary" if exact else "source_supported_terminology"
        result["terminology_missing"] = [t for t in expected if t not in terms.expected(result["text"])]
        return result

    observer.hook(api.Translator, "count", count)
    observer.hook(api.Translator, "generate", generate)
    original_defects = api.generation_defects

    def defects(source, result, tokens, target="ru"):
        flags = original_defects(source, result, tokens, target)
        if result.get("terminology_missing"):
            flags.append("protected_terminology_missing")
        return flags

    observer.hook(api, "generation_defects", defects)
    original_translate = api.translate_segment

    @contextlib.contextmanager
    def record_context(translator, record):
        keys = ("quality_context", "quality_source_language")
        previous = {key: getattr(translator, key) for key in keys if translator is not None and hasattr(translator, key)}
        if translator is not None:
            translator.quality_context = record["raw_text"]
            translator.quality_source_language = record["language"]
        try:
            yield
        finally:
            if translator is not None:
                for key in keys:
                    if key in previous:
                        setattr(translator, key, previous[key])
                    elif hasattr(translator, key):
                        delattr(translator, key)

    def translate(record, translator, cfg, checkpoint=lambda: None, retry=False, target_language="ru"):
        raw = record["raw_text"]
        if api.text_hash(raw) != record["raw_sha256"]:
            raise api.PipelineError("Raw ASR integrity violation")
        if not raw.strip():
            record.update(translation_status="not_required", chunks=[])
            record["translation_" + target_language] = None
            record.setdefault("warnings", []).append("empty_source_no_translation")
            checkpoint()
            return
        with record_context(translator, record):
            original_translate(record, translator, cfg, checkpoint, retry, target_language)
        if record["translation_status"] == "unsupported_language":
            record["translation_diagnostic"] = {
                "reason": "unresolved_source_language" if record["language"] in {"mixed", "unknown"} else "source_language_not_mapped",
                "source_language": record["language"], "target_language": target_language,
            }
        # Technical checks never certify semantic completeness or hide review flags.
        record["technical_validation"] = "passed" if record["translation_status"] in {"needs_review", "not_required"} and not any(
            c.get("warnings") for c in record.get("chunks", [])) else "review"
        checkpoint()

    observer.hook(api, "translate_segment", translate)

    import translation_v156 as mt

    original_group_translate = mt.translate_group

    def translate_group(api, record, translator, cfg, checkpoint, retry=False, target="ru"):
        with record_context(translator, record):
            return original_group_translate(api, record, translator, cfg, checkpoint, retry, target)

    observer.hook(mt, "translate_group", translate_group)

