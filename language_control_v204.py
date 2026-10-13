"""Opt-in source-language and target policy around the frozen inference engine."""

from __future__ import annotations

import copy
import re
from pathlib import Path

LANGUAGES = {"ru", "en", "af", "nl", "de", "fr", "it", "zh", "he"}


def configure(config, source=None, target=None):
    """Omitted options preserve the existing CLI contract and AUTO caches."""
    if source is not None:
        codes = source.lower().split(",") if source.lower() != "auto" else []
        if (
            len(codes) > 3
            or len(set(codes)) != len(codes)
            or any(code not in LANGUAGES for code in codes)
        ):
            raise ValueError("invalid_source_languages")
        if codes and config.get("FORCE_LANGUAGE"):
            raise ValueError("source_languages_conflict_with_force_language")
        if codes:
            config["ALLOWED_SOURCE_LANGUAGES"] = sorted(codes)
    if target is not None:
        if target not in {"ru", "en"}:
            raise ValueError("invalid_target_language")
        config["TARGET_LANGUAGE"] = target
    return config


def select_audio(probabilities, allowed):
    # Retain absolute model confidence: a low-mass allowed candidate is NOT certain.
    ranked = sorted(
        ((code, float(p)) for code, p in probabilities if code in allowed),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        raise ValueError("missing_allowed_language_probabilities")
    return ranked[0]


def resolve(audio_language, evidence, text, allowed):
    language = evidence["language"]
    if evidence["strong"]:
        if language in allowed:
            return language, "allowed_text_evidence"
        # Dutch-like ASR is never renamed blindly. Only independent lexical evidence
        # can establish Afrikaans; otherwise retain the text and request review.
        markers = set(re.findall(r"\w+", text.casefold())) & {
            "nie",
            "hy",
            "hom",
            "hulle",
            "jou",
            "ons",
            "môre",
            "baie",
            "julle",
        }
        if language == "nl" and "af" in allowed and len(markers) >= 2:
            return "af", "allowed_af_lexical_evidence"
        return "unknown", "uncertain_language"
    if audio_language in allowed:
        return audio_language, "allowed_audio_evidence"
    return "unknown", "uncertain_language"


def install(observer):
    api, config = observer.api, observer.config
    allowed = config.get("ALLOWED_SOURCE_LANGUAGES", [])
    target = config.get("TARGET_LANGUAGE")
    if not allowed and not target:
        return
    original_metadata = api.processing_metadata

    def metadata(*args):
        value = original_metadata(*args)
        value["language_control"] = {
            "version": 1,
            "allowed_source_languages": allowed,
            "target_language": target,
            "sha256": api.file_hash(Path(__file__)),
        }
        # Also enter stage-reuse identity; predecessor migration must not bypass policy.
        value["config"]["LANGUAGE_CONTROL_SHA256"] = value["language_control"]["sha256"]
        value["translation_channels"] = [target] if target else ["ru", "en"]
        return value

    observer.hook(api, "processing_metadata", metadata)
    if allowed:

        def detect(instance, audio):
            _, _, probabilities = instance.model.detect_language(
                audio=audio, vad_filter=False
            )
            return select_audio(probabilities, allowed)

        observer.hook(api.WhisperBackend, "detect", detect)

        def reconcile(unit, segments, units, index, audio, backend, lid, config):
            text = "".join(s["raw_text"] for s in segments)
            evidence = lid.assess(text)
            language, reason = resolve(unit["language"], evidence, text, allowed)
            unit["language_reconciliation"] = {
                "detected_language": unit["language"],
                "text_evidence": evidence,
                "resolved_language": language,
                "reason": reason,
                "allowed_source_languages": allowed,
                "raw_selection": "primary_preserved",
            }
            for segment in segments:
                local = lid.assess(segment["raw_text"])
                selected = local if local["strong"] else evidence
                resolved, why = resolve(
                    unit["language"],
                    selected,
                    segment["raw_text"] if local["strong"] else text,
                    allowed,
                )
                segment.update(
                    detected_language=segment["language"],
                    detected_language_confidence=segment["language_confidence"],
                    resolved_language_score=selected["score"],
                    resolved_language=resolved,
                    language=resolved,
                    corrected_text=api.corrected(segment["raw_text"], resolved, config),
                    language_resolution={
                        "reason": why,
                        "evidence": selected,
                        "allowed_source_languages": allowed,
                    },
                )
                if resolved == "unknown":
                    segment["warnings"].append("uncertain_language")
                    segment["transcription_status"] = "needs_review"

        observer.hook(api, "reconcile_unit", reconcile)

    import translation_v156 as mt

    original_route = mt.prepare_routing

    def route(api, data, config):
        original_route(api, data, config)
        for group in data["translation_groups"]:
            context = group.get("translation_context")
            if allowed and context and context["source_language"] not in allowed:
                # Refuse an out-of-whitelist translation route; retain all evidence.
                context["rejected_source_language"] = context["source_language"]
                context["source_language"] = group["language"]
                context["flags"] = sorted(
                    set(context.get("flags", []) + ["uncertain_source_language"])
                )
            if target:
                group.setdefault(
                    "english",
                    {
                        "target_language": "en",
                        "language": group["language"],
                        "raw_text": group["raw_text"],
                        "raw_sha256": group["raw_sha256"],
                        "translation_context": copy.deepcopy(
                            group.get("translation_context", {})
                        ),
                        "translation_en": None,
                        "translation_status": "pending",
                        "chunks": [],
                        "warnings": [],
                    },
                )
                excluded = group["english"] if target == "ru" else group
                excluded.update(
                    translation_status="not_required",
                    chunks=[],
                    target_not_selected=True,
                )
                excluded["translation_en" if target == "ru" else "translation_ru"] = (
                    None
                )

    observer.hook(mt, "prepare_routing", route)
