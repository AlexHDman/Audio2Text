"""Bounded AF/NL translation quality policy; frozen ASR and exporter stay in pipeline.

Context informs routing only. Encoder inputs never contain adjacent group text.
Coverage probes compare independent translations, not a semantic-certification score.
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

POLICY = "afnl-group-route-clause-coverage-1"
SOFT_FLAGS = {
    "implausible_shortening",
    "short_source_expansion",
    "negation_coverage_review",
    "output_lid_disagreement",
}
BASELINE_SHA = "b77863fc800d6d6216f11a20c329e228f5bdf3dd0b6e53f166c84d624f9cb3ff"
ASR_NAMES = {
    "ASR_LANGUAGES",
    "ASRBackend",
    "UnsupportedZuluBackend",
    "WhisperBackend",
    "prepare_audio",
    "load_audio",
    "normalize_diarization",
    "diarize",
    "speaker_for",
    "initial_units",
    "language_units",
    "TextLanguageValidator",
    "resolve_text_language",
    "reconcile_unit",
    "corrected",
    "script_language",
    "make_segment",
    "transcribe_unit",
    "build_translation_groups",
}
SHORT = {
    "ja": {"ru": "Да.", "en": "Yes."},
    "nee": {"ru": "Нет.", "en": "No."},
    "ok": {"ru": "Хорошо.", "en": "OK."},
    "okay": {"ru": "Хорошо.", "en": "OK."},
    "so ja": {"ru": "Так что да.", "en": "So yes."},
}


def core_hash(api, path):
    nodes = []
    for node in ast.parse(Path(path).read_text("utf-8")).body:
        names = {getattr(node, "name", "")}
        if isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if names & ASR_NAMES:
            nodes.append(ast.dump(node, include_attributes=False))
        if getattr(node, "name", None) == "process":
            # Pin the audio/ASR stage orchestration as well as its called functions.
            for statement in ast.walk(node):
                if isinstance(statement, ast.If):
                    dump = ast.dump(statement, include_attributes=False)
                    if "id='prepare_audio'" in dump and "value='asr_done'" in dump:
                        nodes.append(dump)
                        break
    return api.digest(nodes)


def stage_policy(api):
    return {
        "asr_core": core_hash(api, api.__file__),
        "translation": POLICY,
        "translation_code_sha256": api.file_hash(Path(__file__)),
    }


def asr_identity(api, meta, core):
    cfg = {
        k: v
        for k, v in meta["config"].items()
        if not (k.startswith("TRANSLAT") or k == "CHINESE_SCRIPT")
    }
    runtime = {k: v for k, v in meta["runtime"].items() if k != "translation_device"}
    return api.digest(
        {
            "core": core,
            "config": cfg,
            "runtime": runtime,
            "models": {k: v for k, v in meta["models"].items() if k != "translator"},
            "libraries": {
                k: v
                for k, v in meta["libraries"].items()
                if k not in {"transformers", "tokenizers"}
            },
            **{
                k: meta.get(k)
                for k in [
                    "audio",
                    "language_policy",
                    "text_lid",
                    "translation_group_policy",
                    "limit_seconds",
                ]
            },
        }
    )


def reset_translation(group):
    previous = {
        k: copy.deepcopy(group.get(k))
        for k in [
            "translation_ru",
            "chunks",
            "translation_status",
            "english",
            "warnings",
            "review_notes",
        ]
    }
    group.update(
        translation_ru=None,
        translation_corrected_ru=None,
        chunks=[],
        translation_status="pending",
        warnings=[],
        previous_translation=previous,
    )
    for key in [
        "semantic_validation",
        "source_coverage",
        "review_notes",
        "quality",
        "translation_context",
    ]:
        group.pop(key, None)
    group.pop("english", None)


def reuse_stages(api, base, source, processing):
    """Checksum-validated stage reuse; never writes to the predecessor namespace."""
    import audio_pipeline_cuda_v155_FIXED as old

    current_core = processing["stage_policy"]["asr_core"]
    identity = asr_identity(api, processing, current_core)
    roots = {base, api.ROOT / "temp/v155"}
    candidates = sorted(
        (
            f
            for root in roots
            for f in root.glob(source["sha256"][:20] + "-*/resume.json")
        ),
        key=lambda f: f.stat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates:
        try:
            data = api.read_json(path)
            meta = data["processing"]
            if data["pipeline_version"] == "1.5.5":
                if (
                    meta["algorithm_sha256"] != BASELINE_SHA
                    or api.file_hash(Path(old.__file__)) != BASELINE_SHA
                ):
                    continue
                old.validate_cache(data, source, data["processing_fingerprint"])
                old_core = core_hash(api, old.__file__)
            elif data["pipeline_version"] == api.VERSION:
                api.validate_cache(data, source, data["processing_fingerprint"])
                old_core = meta["stage_policy"]["asr_core"]
            else:
                continue
            if identity != asr_identity(api, meta, old_core):
                continue
            if (
                not data["diarization_done"]
                or not data["units"]
                or any(not u["asr_done"] for u in data["units"])
            ):
                continue
            if not data.get("translation_groups"):
                continue
            same_models = (
                meta["models"]["translator"] == processing["models"]["translator"]
            )
            old_mt = {
                k: v
                for k, v in meta["config"].items()
                if k.startswith("TRANSLAT") or k == "CHINESE_SCRIPT"
            }
            new_mt = {
                k: v
                for k, v in processing["config"].items()
                if k.startswith("TRANSLAT") or k == "CHINESE_SCRIPT"
            }
            same_mt_runtime = all(
                meta["libraries"].get(k) == processing["libraries"].get(k)
                for k in ["transformers", "tokenizers", "torch"]
            )
            reuse_other = same_models and old_mt == new_mt and same_mt_runtime
            previous_fp = data["processing_fingerprint"]
            for group in data["translation_groups"]:
                if group["language"] in {"af", "nl"} or not reuse_other:
                    reset_translation(group)
            data["reuse_provenance"] = {
                "policy": "v156-stage-reuse-1",
                "cache": str(path),
                "previous_fingerprint": previous_fp,
                "previous_state_sha256": data["state_sha256"],
                "asr_identity": identity,
                "asr_reused": True,
                "non_afnl_translation_reused": reuse_other,
            }
            data.update(
                pipeline_version=api.VERSION,
                processing=processing,
                processing_fingerprint=api.digest(processing),
            )
            data.pop("state_sha256", None)
            api.LOG.info(
                "v156: cached ASR/diarization/groups reused; translation policy invalidated independently"
            )
            return data
        except (ValueError, KeyError, TypeError, AttributeError, api.PipelineError):
            api.LOG.warning("Stage cache rejected; predecessor retained: %s", path)
    return None


def context_for(groups, index):
    group = groups[index]
    neighbors = []
    for j in [index - 1, index + 1]:
        if not 0 <= j < len(groups):
            continue
        other = groups[j]
        gap = (
            group["start"] - other["end"]
            if j < index
            else other["start"] - group["end"]
        )
        if (
            other["speaker_id"] != group["speaker_id"]
            or group["speaker_id"] == "UNKNOWN"
            or not -0.05 <= gap <= 2.0
        ):
            continue
        neighbors.append(
            {
                "group_id": other["group_id"],
                "language": other["language"],
                "raw_sha256": other["raw_sha256"],
                "text": other["raw_text"],
                "gap": gap,
            }
        )
    return neighbors


def route(text, original, evidence, neighbors, forced=False):
    words = set(re.findall(r"\w+", text.casefold()))
    af = words & {"nie", "hy", "hom", "hulle", "jou", "ons", "by", "môre"}
    nl = words & {"jij", "hem", "kunnen", "heeft", "zijn", "wij", "niet"}
    selected, reason = original, "preserved_resolved_language"
    flags = []
    if not forced:
        if len(af) >= 4 and len(nl) <= 1 and original == "nl":
            selected, reason = "af", "multiple_af_lexical_markers"
            flags.append("uncertain_source_language")
        elif evidence["strong"] and evidence["language"] in {"af", "nl"}:
            selected, reason = evidence["language"], "strong_group_text_lid"
            if selected != original:
                flags.append("uncertain_source_language")
        elif evidence["strong"] and evidence["language"] not in {"af", "nl"}:
            flags.append("source_language_or_asr_damage")
        elif (
            len(neighbors) == 2
            and len({n["language"] for n in neighbors}) == 1
            and neighbors[0]["language"] == evidence["language"]
            and evidence["language"] in {"af", "nl"}
            and evidence.get("score", 0) >= 0.8
        ):
            selected, reason = (
                evidence["language"],
                "group_lid_supported_by_both_neighbors",
            )
            if selected != original:
                flags.append("uncertain_source_language")
        elif len(words) >= 5 and not (
            evidence["language"] == original and evidence.get("score", 0) >= 0.95
        ):
            flags.append("uncertain_source_language")
    return {
        "original_language": original,
        "source_language": selected,
        "reason": reason,
        "group_lid": evidence,
        "lexical_markers": {"af": sorted(af), "nl": sorted(nl)},
        "neighbors": neighbors,
        "context_policy": "same speaker, immediate neighbors, gap<=2s; routing-only, never encoder input",
        "neighbor_languages": [n["language"] for n in neighbors],
        "flags": flags,
    }


def prepare_routing(api, data, config):
    pending = [
        g
        for g in data["translation_groups"]
        if g["language"] in {"af", "nl"} and "translation_context" not in g
    ]
    if not pending:
        return
    lid = api.TextLanguageValidator()
    for index, group in enumerate(data["translation_groups"]):
        if group not in pending:
            continue
        group["translation_context"] = route(
            group["raw_text"],
            group["language"],
            lid.assess(group["raw_text"]),
            context_for(data["translation_groups"], index),
            bool(config["FORCE_LANGUAGE"]),
        )


def clause_spans(api, text, count, budget):
    # Lossless character spans from group punctuation, never ASR row boundaries.
    cuts = (
        [0]
        + [m.end() for m in re.finditer(r"[,;:，；：.!?。！？]\s*", text)]
        + [len(text)]
    )
    spans = [(a, b) for a, b in zip(sorted(set(cuts)), sorted(set(cuts))[1:]) if b > a]
    # Keep dependent tiny conjunction fragments with the next clause.
    merged = []
    start = None
    for a, b in spans:
        start = a if start is None else start
        if (
            len(re.findall(r"\w+", text[start:b])) >= 4
            or re.search(r"[.!?。！？]\s*$", text[start:b])
            or b == len(text)
        ):
            merged.extend(api.split_budget(text, start, b, count, budget))
            start = None
    return merged


def defects(api, source, result, tokens, target):
    flags = api.generation_defects(source, result, tokens, target)
    out = result["text"]
    src_words = re.findall(r"\w+", source.casefold())
    dst_words = re.findall(r"\w+", out.casefold())
    if not any(c.isalpha() for c in out):
        flags.append("empty_or_punctuation_only")
    if len(src_words) >= 3 and src_words == dst_words:
        flags.append("unchanged_source")
    if re.search(r"<(?:/?s|pad|unk|mask|[^>]*_Latn|[^>]*_Cyrl)>|__(?:[a-z]{3})__", out):
        flags.append("special_token_artifact")
    if len(src_words) >= 8 and len(dst_words) < 0.45 * len(src_words):
        flags.append("implausible_shortening")
    if len(src_words) <= 2 and len(dst_words) > max(3, 3 * len(src_words)):
        flags.append("short_source_expansion")
    clauses = [re.findall(r"\w+", x.casefold()) for x in re.split(r"[,;.!?]", out)]
    if any(
        len(c) >= 3
        and clauses.count(c) > 1
        and source.casefold().count(" ".join(c)) < 2
        for c in clauses
    ):
        flags.append("duplicated_clause")
    if out.count(",") > max(8, 2 * source.count(",") + 2):
        flags.append("excessive_commas")
    for width in range(1, 5):
        if any(
            dst_words[i : i + width] * 4 == dst_words[i : i + 4 * width]
            and src_words.count(dst_words[i]) < 4
            for i in range(max(0, len(dst_words) - 4 * width + 1))
        ):
            flags.append("excessive_repetition")
            break
    if result.get("hit_cap"):
        flags.append("output_cap")
    if not result.get("eos"):
        flags.append("missing_eos")
    if set(src_words) & {"nie", "niet", "geen"}:
        negations = (
            {"not", "no", "never", "without"}
            if target == "en"
            else {"не", "нет", "ни", "без"}
        )
        if not set(dst_words) & negations and not (
            target == "en" and "n't" in out.casefold()
        ):
            flags.append("negation_coverage_review")
    if target == "en" and sum(
        c.isalpha() and not ("a" <= c.casefold() <= "z") for c in out
    ) > max(3, sum("a" <= c.casefold() <= "z" for c in out)):
        flags.append("wrong_target_script")
    return sorted(set(flags))


def validate_quality(api, record, target):
    raw = record["raw_text"]
    for attempt in record.get("quality", {}).get("attempts", []):
        position = 0
        for a, b in attempt["spans"]:
            if a != position or not a < b <= len(raw):
                raise ValueError("invalid quality attempt spans")
            position = b
        if position != len(raw):
            raise ValueError("quality attempt source coverage incomplete")
        chunks = attempt["chunks"]
        for index, chunk in enumerate(chunks):
            if [chunk["start"], chunk["end"]] != attempt["spans"][index]:
                raise ValueError("quality attempt chunk/span mismatch")
        if chunks:
            api.validate_chunks(raw[: chunks[-1]["end"]], chunks, target)
        if attempt.get("complete") and len(chunks) != len(attempt["spans"]):
            raise ValueError("quality attempt marked complete too early")


def anchors(text):
    stop = set(
        "i my me we our you your he his him she her it its they their them a an the and or but so then is are was were to of in on with for at by that this as do did not я мы вы ты он она они мой моя мои его ее их это и а но то в на по с со для к не был была были есть как что".split()
    )
    return {
        w[:4]
        for w in re.findall(r"[^\W\d_]+", text.casefold())
        if len(w) > 2 and w not in stop
    }


def omitted_clauses(probes, candidate):
    full = anchors(candidate)
    return [i for i, p in enumerate(probes) if anchors(p) and not (anchors(p) & full)]


def translate_group(
    api, record, translator, config, checkpoint, retry=False, target="ru"
):
    raw = record["raw_text"]
    field = "translation_" + target
    if api.text_hash(raw) != record["raw_sha256"]:
        raise api.PipelineError("Raw integrity violation")
    if config["TRANSLATE_MODE"] == "off" or not raw.strip():
        api.translate_segment(record, translator, config, checkpoint, retry, target)
        return
    context = record.get("translation_context", {})
    selected = context.get("source_language", record["language"])
    quality = record.setdefault(
        "quality",
        {"policy": POLICY, "attempts": [], "flags": [], "strategy": "pending"},
    )
    if retry and record["translation_status"] in {"failed", "partial"}:
        quality["attempts"] = [
            a
            for a in quality["attempts"]
            if not a.get("flags") and all(c["status"] != "failed" for c in a["chunks"])
        ]
    quality["flags"] = list(context.get("flags", []))
    translator.target_language = target

    def candidate(name, language, spans):
        existing = next((a for a in quality["attempts"] if a["strategy"] == name), None)
        if existing is None:
            existing = {
                "strategy": name,
                "source_language": language,
                "spans": [list(s) for s in spans],
                "chunks": [],
                "complete": False,
            }
            quality["attempts"].append(existing)
        translator.set_language(api.NLLB[language])
        for a, b in spans[len(existing["chunks"]) :]:
            text = raw[a:b]
            ch = api.chunk_record(raw, a, b, translator.count, target)
            try:
                result = translator.generate(text)
                flags = defects(api, text, result, ch["source_token_count"], target)
                if not hasattr(translator, "quality_lid"):
                    translator.quality_lid = api.TextLanguageValidator()
                result["output_lid"] = translator.quality_lid.assess(result["text"])
                if (
                    result["output_lid"]["strong"]
                    and result["output_lid"]["language"] != target
                ):
                    flags.append("output_lid_disagreement")
                ch.update(
                    {
                        field: result["text"],
                        "warnings": flags,
                        "generated_ids": result["generated_ids"],
                        "target_token_count": result["target_token_count"],
                        "status": "needs_review" if not flags else "partial",
                    }
                )
                ch["attempts"] = [
                    {**result, "warnings": flags, "input_sha256": api.text_hash(text)}
                ]
            except Exception as e:
                ch.update(
                    status="failed",
                    warnings=["translation_exception:" + type(e).__name__],
                )
            existing["chunks"].append(ch)
            checkpoint()
        existing["complete"] = True
        existing["text"] = " ".join(
            c.get(field) or "" for c in existing["chunks"]
        ).strip()
        existing["flags"] = sorted(
            {w for c in existing["chunks"] for w in c["warnings"]}
        )
        return existing

    translator.set_language(api.NLLB[record["language"]])
    budget = config["TRANSLATION_TOKEN_BUDGET"]
    spans = (
        [(0, len(raw))]
        if translator.count(raw) <= budget
        else api.semantic_translation_spans(
            raw, translator.count, budget, record["language"]
        )
    )
    primary = candidate("complete_group", record["language"], spans)
    chosen = primary
    if selected != record["language"]:
        translator.set_language(api.NLLB[selected])
        routed_spans = (
            [(0, len(raw))]
            if translator.count(raw) <= budget
            else api.semantic_translation_spans(raw, translator.count, budget, selected)
        )
        alternative = candidate("context_evidence_route", selected, routed_spans)
        if len(alternative["flags"]) <= len(primary["flags"]):
            chosen = alternative
    short = re.sub(r"[^\w\s]", "", raw.casefold()).strip()
    if short in SHORT:
        text = SHORT[short][target]
        ch = api.chunk_record(raw, 0, len(raw), translator.count, target)
        ch.update({field: text, "status": "needs_review"})
        chosen = {
            "strategy": "reviewed_short_utterance_lexicon",
            "text": text,
            "chunks": [ch],
            "flags": [],
        }
    else:
        translator.set_language(api.NLLB[selected])
        parts = clause_spans(api, raw, translator.count, budget)
        sentences = api.sentence_spans(raw)
        sentence_loss = len(sentences) > len(api.sentence_spans(chosen["text"]))
        if len(sentences) > 1:
            # Preserve short but meaningful leading/trailing sentences.
            parts = [
                span
                for a, b in sentences
                for span in api.split_budget(raw, a, b, translator.count, budget)
            ]
        complex_group = len(parts) >= 3 and len(raw.split()) >= 12
        if len(parts) > 1 and (complex_group or len(sentences) > 1 or chosen["flags"]):
            probe = candidate("semantic_clauses", selected, parts)
            missing = omitted_clauses(
                [c.get(field) or "" for c in probe["chunks"]], chosen["text"]
            )
            quality["coverage_probe"] = {
                "method": "independent target lexical anchors; heuristic, not semantic proof",
                "missing_clause_indices": missing,
                "sentence_count_loss": sentence_loss,
            }
            if missing or len(sentences) > 1 or chosen["flags"]:
                if not (set(probe["flags"]) - SOFT_FLAGS):
                    chosen = probe
                    if missing or sentence_loss:
                        quality["flags"].append("clause_retry_semantic_review")
                else:
                    quality["flags"].append("unresolved_omission_or_generation_defect")
    record["chunks"] = copy.deepcopy(chosen["chunks"])
    record[field] = chosen["text"] or None
    record["translation_corrected_" + target] = api.corrected(
        record[field] or "", target, config
    )
    quality["strategy"] = chosen["strategy"]
    quality["flags"] = sorted(set(quality["flags"] + chosen["flags"]))
    record["warnings"] = quality["flags"]
    record["translation_status"] = (
        "partial"
        if "unresolved_omission_or_generation_defect" in quality["flags"]
        else "needs_review"
    )
    hard = set(chosen["flags"]) - SOFT_FLAGS
    if hard:
        # Rejected text is retained in attempts, never presented as a translation.
        record[field] = None
        record["translation_corrected_" + target] = None
        record["translation_status"] = "failed"
    if not record[field]:
        record["translation_status"] = "failed"
    record["source_coverage"] = sum(
        c["end"] - c["start"] for c in record["chunks"]
    ) / len(raw)
    api.validate_chunks(raw, record["chunks"], target)
    checkpoint()
