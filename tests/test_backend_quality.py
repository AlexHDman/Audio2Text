"""BE-001 policy regressions. Synthetic text only; no model inference."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backend_contract_v1 as contract
import backend_runtime_v157 as runtime
import backend_quality as quality
import translation_v156 as mt

ROOT = Path(__file__).resolve().parents[1]


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.paths = contract.AppPaths.create()
        self.api = runtime.load_engine(self.paths)
        self.config = quality.configure(copy.deepcopy(self.api.DEFAULTS), ROOT)
        self.terms = quality.Terminology(ROOT / "dictionaries/protected_terms.json")

    def observer(self):
        events = contract.EventStream(io.StringIO())
        observer = runtime.Observer(self.api, self.paths, events, contract.Telemetry(events), self.config)
        observer.data = {"translation_groups": []}
        observer.translation_total = 100
        return observer

    def record(self, text, language):
        return dict(raw_text=text, raw_sha256=self.api.text_hash(text), language=language,
                    translation_status="pending", chunks=[], warnings=[], translation_ru=None)

    def test_russian_terms_do_not_force_mixed(self):
        with self.observer():
            for text in ["Корпорация FOHOW соблюдает GMP и FDA.", "Перевод с помощью NLLB."]:
                self.assertEqual(self.api.script_language(text, "ru", False), ("ru", []))
            self.assertEqual(self.api.script_language("Русская речь and actual English speech", "ru", False)[0], "mixed")
            self.assertEqual(self.api.script_language("Русская речь hello", "ru", False)[0], "mixed")
            self.assertEqual(self.api.script_language("Текст FOHOW", "unknown", False)[0], "mixed")

    def test_contextual_aliases_without_blind_replacement(self):
        value, changes = self.terms.normalize("Корпорация ФОХОУ и концепция ФЕНТОУ")
        self.assertEqual(value, "Корпорация FOHOW и концепция FENDOU")
        self.assertEqual(len(changes), 2)
        self.assertEqual(self.terms.normalize("Phantom is an ordinary title")[0], "Phantom is an ordinary title")
        self.assertEqual(self.terms.normalize("FHOC")[0], "FHOC")
        self.assertEqual(self.terms.normalize("Company XFOCHOUX")[0], "Company XFOCHOUX")
        self.assertEqual(self.terms.normalize("Мария Тестовая в Тестограде")[0], "Мария Тестовая в Тестограде")

    def test_empty_source_not_translation_failure(self):
        record = self.record("", "en")
        with self.observer():
            self.api.translate_segment(record, None, self.config)
        self.assertEqual(record["translation_status"], "not_required")
        self.assertIn("empty_source_no_translation", record["warnings"])
        self.assertEqual(record["raw_sha256"], self.api.text_hash(""))

    def test_unknown_language_has_diagnostic_and_no_fallback(self):
        record = self.record("Unknown speech", "unknown")
        with self.observer():
            self.api.translate_segment(record, None, self.config)
        self.assertEqual(record["translation_status"], "unsupported_language")
        self.assertEqual(record["translation_diagnostic"]["reason"], "unresolved_source_language")

    def test_same_target_bypasses_translation(self):
        for lang in ["ru", "en"]:
            record = self.record("Original source", lang)
            with self.observer():
                self.api.translate_segment(record, None, self.config, target_language=lang)
            self.assertIsNone(record["translation_" + lang])
            self.assertEqual(record["translation_status"], "not_required")

    def test_default_target_single_and_manual_preserved(self):
        with self.observer():
            self.assertEqual(self.config["TARGET_LANGUAGE"], "ru")
        self.config.update(TARGET_LANGUAGE="en", ALLOWED_SOURCE_LANGUAGES=["af", "en"])
        with self.observer():
            self.assertEqual(self.config["TARGET_LANGUAGE"], "en")
            self.assertEqual(self.config["ALLOWED_SOURCE_LANGUAGES"], ["af", "en"])

    def test_raw_integrity_and_missing_terms_fail_closed(self):
        record = self.record("Some source", "ru")
        record["raw_text"] += " changed"
        with self.observer():
            with self.assertRaises(self.api.PipelineError):
                self.api.translate_segment(record, None, self.config)
            result = dict(text="The company", target_token_count=5, generated_ids=[], terminology_missing=["FOHOW"])
            self.assertIn("protected_terminology_missing", self.api.generation_defects("Компания FOHOW", result, 8, "en"))

    def test_only_short_russian_context_packed_losslessly(self):
        text = " Одна мечта. Одна большая команда. FOHOW. FENDOU."
        original = self.api.semantic_translation_spans
        with self.observer():
            self.assertEqual(self.api.semantic_translation_spans(text, lambda s: len(s)//2, 192, "ru"), [(0, len(text))])
            for language in ["en", "af", "nl", "zh"]:
                self.assertEqual(self.api.semantic_translation_spans(text, len, 192, language), original(text, len, 192, language))
            self.assertEqual(self.api.semantic_translation_spans(text, len, 8, "ru"), original(text, len, 8, "ru"))

    def test_generated_evidence_and_exact_phrase_scope(self):
        fake = lambda instance, text: dict(text="Let's get on with it.", generated_ids=[1, 2], target_token_count=2, eos=True, hit_cap=False)
        with patch.object(self.api.Translator, "generate", fake), self.observer():
            translator = self.api.Translator.__new__(self.api.Translator)
            translator.target_language = "en"
            translator.device = "cpu"
            translator.quality_source_language = "ru"
            result = translator.generate("Продолжение следует...")
            self.assertEqual(result["text"], "To be continued.")
            self.assertEqual(result["model_text"], "Let's get on with it.")
            self.assertEqual(result["generated_ids"], [1, 2])
            self.assertEqual(translator.generate("Продолжение следует обсудить завтра.")["text"], "Let's get on with it.")
            self.assertEqual(self.terms.exact_phrase("Одна мечта", "en", "ru"), None)

    def test_policy_enters_stage_reuse_identity(self):
        meta = dict(config={}, runtime={}, models={}, libraries={})
        before = mt.asr_identity(self.api, meta, "frozen")
        meta["config"]["BACKEND_QUALITY"] = self.config["BACKEND_QUALITY"]
        self.assertNotEqual(before, mt.asr_identity(self.api, meta, "frozen"))
        before = mt.asr_identity(self.api, meta, "frozen")
        meta["config"]["BACKEND_QUALITY"] = {**self.config["BACKEND_QUALITY"], "terminology_sha256": "changed"}
        self.assertNotEqual(before, mt.asr_identity(self.api, meta, "frozen"))

    def test_context_does_not_leak_from_russian_into_afnl(self):
        from types import SimpleNamespace
        translator = SimpleNamespace(target_language="en", device="cpu")
        first = self.record("Корпорация ФОХОУ", "ru")
        later = self.record("FHOC", "af")
        def normal(record, translator, *args):
            self.assertEqual(translator.quality_source_language, record["language"])
            record["translation_status"] = "needs_review"
        def grouped(api, record, translator, *args):
            self.assertEqual(translator.quality_context, "FHOC")
            self.assertEqual(translator.quality_source_language, "af")
            self.assertEqual(self.terms.normalize("FHOC", translator.quality_context)[0], "FHOC")
            record["translation_status"] = "needs_review"
        with patch.object(self.api, "translate_segment", normal), patch.object(mt, "translate_group", grouped), self.observer():
            self.api.translate_segment(first, translator, self.config)
            self.assertFalse(hasattr(translator, "quality_context"))
            mt.translate_group(self.api, later, translator, self.config, lambda: None)
            self.assertFalse(hasattr(translator, "quality_source_language"))

    def test_context_restored_after_translation_exception(self):
        from types import SimpleNamespace
        translator = SimpleNamespace(device="cpu", quality_context="caller-owned")
        with patch.object(self.api, "translate_segment", side_effect=RuntimeError("synthetic")), self.observer():
            with self.assertRaises(RuntimeError):
                self.api.translate_segment(self.record("Корпорация FOHOW", "ru"), translator, self.config)
        self.assertEqual(translator.quality_context, "caller-owned")
        self.assertFalse(hasattr(translator, "quality_source_language"))

    def test_corrupt_terminology_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests/.runtime") as folder:
            path = Path(folder) / "terms.json"
            for text in ["{", json.dumps({"version": 99, "terms": []})]:
                path.write_text(text)
                with self.assertRaises(ValueError):
                    quality.Terminology(path)

    def test_sparse_detection_requires_long_speech_not_silence(self):
        unit = {"start": 0, "end": 24}
        rows = [{"raw_text": "A name"}]
        self.assertFalse(quality.sparse_speech(unit, rows, []))
        self.assertTrue(quality.sparse_speech(unit, rows, [{"start": 0, "end": 24}]))
        self.assertFalse(quality.sparse_speech({"start": 0, "end": 4}, rows, [{"start": 0, "end": 4}]))
        self.assertFalse(quality.sparse_speech(unit, [{"raw_text": "word " * 40}], [{"start": 0, "end": 24}]))

    def test_recovery_needs_more_than_longer_text(self):
        primary = [{"raw_text": "Original name"}]
        alternative = [{"raw_text": "word " * 15}]
        old = [{"text": "Original name", "avg_logprob": -0.4}]
        bad = [{"text": "word " * 15, "avg_logprob": -0.5}]
        good = [{"text": "word " * 15, "avg_logprob": -0.1}]
        self.assertFalse(quality.recovery_better(primary, alternative, old, bad))
        self.assertTrue(quality.recovery_better(primary, alternative, old, good))

    def test_context_agreement_rejects_different_or_short_hallucinations(self):
        primary = [{"raw_text": "Credit name"}]
        first = [{"raw_text": "The central office includes a research centre and a production complex with modern equipment"}]
        second = [{"raw_text": "The central office includes a research center and a production complex with modern equipment"}]
        unrelated = [{"raw_text": "Other unrelated words " * 6}]
        self.assertTrue(quality.recovery_agreement(primary, first, second))
        self.assertFalse(quality.recovery_agreement(primary, first, unrelated))
        self.assertFalse(quality.recovery_agreement(primary, primary, primary))

    def test_third_context_requires_confident_corroboration(self):
        import numpy as np
        long_text = "The central office includes a research centre and a production complex with modern equipment"
        for low_confidence in [False, True]:
            with self.subTest(low_confidence=low_confidence):
                unit = dict(unit_id="u0", start=0., end=24.)
                calls = []
                def fake(trial, audio, backend, config, intervals, exclusive=None):
                    padding = config["BOUNDARY_PADDING_SECONDS"]
                    calls.append(padding)
                    substantive = padding in {3., 6.}
                    text = long_text if substantive else "Credit name"
                    trial["raw_pieces"] = [{"text": text, "avg_logprob": -.08 if substantive else -.15,
                                            "no_speech_prob": .99 if low_confidence else .2}]
                    trial["asr_info"] = {"language": "en"}
                    return [dict(segment_id="u0-s0", raw_text=text, start=0., end=24., warnings=[], transcription_status="complete")]
                with patch.object(self.api, "transcribe_unit", fake), self.observer():
                    rows = self.api.transcribe_unit(unit, np.zeros(24 * 16000), None, self.config, [{"start": 0., "end": 24.}])
                recovery = unit["quality_recovery"]
                self.assertEqual(recovery["recovered"], not low_confidence)
                self.assertEqual(len(calls), 3 if low_confidence else 4)
                self.assertEqual(recovery["primary_raw_pieces"][0]["text"], "Credit name")
                if not low_confidence:
                    self.assertTrue(recovery["attempts"][-1]["corroborated"])
                    self.assertEqual(rows[0]["raw_text"], long_text)
                else:
                    self.assertIn("sparse_speech_unresolved", rows[0]["warnings"])

    def test_group_merge_preserves_every_source_character_and_speaker(self):
        def segment(index, start, end, text, speaker="S1"):
            unit = dict(unit_id=f"u{index}", language="ru", language_method="audio", language_confidence=.9)
            return self.api.make_segment(unit, 0, start, end, text, speaker, [], self.config)
        rows = [segment(0, 0, 23, "Центральный офис компании находится в"),
                segment(1, 23, 29, " городе, где работает предприятие."),
                segment(2, 29, 33, " новый говорящий", "S2")]
        raw = "".join(s["raw_text"] for s in rows)
        with self.observer():
            groups = self.api.build_translation_groups(rows)
            self.assertEqual(len(groups), 2)
            self.assertEqual("".join(g["raw_text"] for g in groups), raw)
            self.api.validate_translation_groups({"segments": rows, "translation_groups": groups})

    def test_recovery_archives_primary_and_respects_time_ownership(self):
        import numpy as np
        unit = dict(unit_id="u0", start=0., end=24.)
        def fake(unit, audio, backend, config, intervals, exclusive=None):
            retry = config["BOUNDARY_PADDING_SECONDS"] == 4
            text = "word " * 15 if retry else "Original name"
            unit["raw_pieces"] = [{"text": text, "avg_logprob": -.1 if retry else -.4}]
            unit["asr_info"] = {"language": "en"}
            return [dict(segment_id="u0-s0", raw_text=text, start=0., end=24., warnings=[], transcription_status="complete")]
        with patch.object(self.api, "transcribe_unit", fake), self.observer():
            rows = self.api.transcribe_unit(unit, np.zeros(24 * 16000), None, self.config, [{"start": 0., "end": 24.}])
        self.assertEqual(unit["quality_recovery"]["primary_segments"][0]["raw_text"], "Original name")
        self.assertTrue(unit["quality_recovery"]["recovered"])
        self.assertIn("asr_context_recovered_review", rows[0]["warnings"])
        self.assertEqual(rows[0]["end"], 24.)


if __name__ == "__main__":
    unittest.main()
