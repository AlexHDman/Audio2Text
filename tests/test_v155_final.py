"""Final-pass regression contracts; all writes are project-local fixtures."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audio_pipeline_cuda_v155_FIXED as p
from test_v155 import cache, config, segment, TokenTranslator


def evidence(language, strong=True):
    return {"language": language, "strong": strong, "score": 0.999 if strong else 0.4}


def adjacent(texts, language="af"):
    result = []
    for i, text in enumerate(texts):
        s = segment(text, language)
        s.update(segment_id=f"s{i}", start=float(i * 2), end=float(i * 2 + 1.9))
        result.append(s)
    return result


class FinalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lid = p.TextLanguageValidator()

    def test_af_nl_af_continuity_requires_text_evidence(self):
        self.assertEqual(
            p.resolve_text_language("nl", evidence("af"), True),
            ("af", "afrikaans_text_and_continuity"),
        )
        self.assertEqual(
            p.resolve_text_language("nl", evidence("af", False), True)[0], "nl"
        )

    def test_actual_dutch_not_forced_to_af_by_neighbors(self):
        e = self.lid.assess(
            "Dit is een Nederlandse tekst. Morgen gaan wij samen naar de vergadering."
        )
        self.assertEqual(e["language"], "nl")
        self.assertTrue(e["strong"])
        self.assertEqual(p.resolve_text_language("nl", e, True)[0], "nl")
        self.assertEqual(p.NLLB["nl"], "nld_Latn")
        self.assertIn("nl", p.ASR_LANGUAGES)

    def test_actual_af_text(self):
        e = self.lid.assess(
            "Ons is saam met jou en ons sal jou help. Ek kan nie vandag kom nie, maar ek sal jou môre bel."
        )
        self.assertEqual(e["language"], "af")
        self.assertTrue(e["strong"])

    def test_af_audio_english_raw_conflict(self):
        text = "My whole family is actually very sad, the children is also because, you know, they loved him."
        e = self.lid.assess(text)
        self.assertTrue(e["strong"])
        self.assertEqual(
            p.resolve_text_language("af", e, False), ("en", "statistical_text_conflict")
        )

    def test_no_universal_english_fallback(self):
        self.assertEqual(
            p.resolve_text_language("af", evidence("en", False), False)[0], "af"
        )
        self.assertEqual(
            p.resolve_text_language("unknown", evidence("en"), False)[0], "unknown"
        )
        self.assertEqual(p.resolve_text_language("af", evidence("zu"), False)[0], "af")
        self.assertEqual(
            p.resolve_text_language("af", evidence("en"), False, True)[0], "af"
        )

    def test_short_af_segments_group_without_timestamp_changes(self):
        ss = adjacent(
            [
                " En nou wat jy nou",
                " my meisieke",
                " is by my, ons is",
                " in die kombuis.",
            ]
        )
        before = [(s["raw_text"], s["start"], s["end"], s["raw_sha256"]) for s in ss]
        groups = p.build_translation_groups(ss)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["raw_text"], "".join(x[0] for x in before))
        self.assertEqual(
            before, [(s["raw_text"], s["start"], s["end"], s["raw_sha256"]) for s in ss]
        )
        p.validate_translation_groups({"segments": ss, "translation_groups": groups})

    def test_different_speakers_not_grouped(self):
        ss = adjacent([" Hallo", " daar"])
        ss[1]["speaker_id"] = "B"
        self.assertEqual(len(p.build_translation_groups(ss)), 2)

    def test_different_languages_not_grouped(self):
        ss = adjacent([" Hallo", " hello"])
        ss[1]["language"] = "en"
        self.assertEqual(len(p.build_translation_groups(ss)), 2)

    def test_pause_and_unknown_speaker_not_grouped(self):
        ss = adjacent([" Hello", " again"])
        ss[1].update(start=4.0, end=5.0)
        self.assertEqual(len(p.build_translation_groups(ss)), 2)
        ss = adjacent([" Hello", " again"])
        for s in ss:
            s["speaker_id"] = "UNKNOWN"
        self.assertEqual(len(p.build_translation_groups(ss)), 2)

    def test_af_clause_context_not_split_at_every_comma(self):
        text = "Ek is hier, ons is saam, dit is my familie, ek sal jou môre bel."
        spans = p.semantic_translation_spans(
            text, lambda t: len(t.split()) + 2, 192, "af"
        )
        self.assertEqual(spans, [(0, len(text))])

    def test_group_source_tamper_rejected(self):
        ss = adjacent([" Hallo", " daar"])
        gg = p.build_translation_groups(ss)
        gg[0]["member_spans"][0]["end"] += 1
        with self.assertRaises(ValueError):
            p.validate_translation_groups({"segments": ss, "translation_groups": gg})

    def test_group_resume_reuses_finished_chunks(self):
        ss = adjacent([" Hallo", " daar"])
        gg = p.build_translation_groups(ss)
        t = TokenTranslator()
        p.translate_segment(gg[0], t, config())
        calls = t.calls
        d = {"segments": ss, "translation_groups": gg}
        p.sync_group_status(d)
        p.translate_segment(gg[0], t, config())
        self.assertEqual(t.calls, calls)
        p.validate_translation_groups(d)

    def test_generation_defects(self):
        cases = [
            ("you know,", "Вы знаете" + "," * 40, [2, 4, 2]),
            ("they loved him", "они любили его " * 35, [2, 4, 2]),
            ("short phrase", "Перевод", [4, 5] * 60),
            ("short", "абвгдежзийклмнопрсту" * 20, [2]),
            ("This has three words", "...", [2]),
            ("I like to cook and eat", "I like to cook, моя семья", [2]),
        ]
        for source, text, ids in cases:
            with self.subTest(source=source, text=text[:15]):
                r = {"text": text, "generated_ids": ids, "target_token_count": len(ids)}
                self.assertTrue(p.generation_defects(source, r, 6))

    def test_names_and_legitimate_repeats_preserved(self):
        r = {
            "text": "Да, да, это сказал Alex.",
            "generated_ids": [2, 7, 2],
            "target_token_count": 9,
        }
        self.assertFalse(p.generation_defects("Yes, yes, Alex said that.", r, 9))

    def test_punctuation_garbage_not_published_as_translation(self):
        class T(TokenTranslator):
            def generate(self, text):
                return {
                    "text": "Вы знаете" + "," * 50,
                    "eos": True,
                    "hit_cap": False,
                    "generated_ids": [2, 4, 2],
                    "target_token_count": 30,
                }

        s = segment("you know,")
        p.translate_segment(s, T(), config())
        self.assertEqual(s["translation_status"], "failed")
        self.assertIsNone(s["translation_ru"])
        self.assertIn("," * 50, s["chunks"][0]["attempts"][0]["text"])

    def test_vad_diagnostic_is_not_partial(self):
        d = cache()
        d["segments"][0].update(
            transcription_status="complete",
            translation_status="not_required",
            diagnostics=["vad_alternative_differs"],
        )
        self.assertEqual(p.exported_status(d), "complete")
        d["segments"][0]["translation_status"] = "partial"
        self.assertEqual(p.exported_status(d), "partial")

    def test_flat_output_and_clean_group_export(self):
        base = p.ROOT / "tests/.runtime"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            d = cache()
            ss = adjacent([" Eerste deel", " tweede deel."])
            d["segments"] = ss
            d["translation_groups"] = p.build_translation_groups(ss)
            g = d["translation_groups"][0]
            g.update(
                translation_ru="Перевод всей фразы.", translation_status="needs_review"
            )
            for s in ss:
                s["diagnostics"] = ["vad_alternative_differs"]
            p.sync_group_status(d)
            paths = p.publish_exports(d, config(), Path(temp))
            self.assertEqual({x.parent for x in paths}, {Path(temp)})
            self.assertEqual(len(list(Path(temp).iterdir())), 3)
            txt = paths[1].read_text(encoding="utf-8")
            self.assertEqual(txt.count("Перевод всей фразы."), 1)
            self.assertNotIn("vad_", txt)
            self.assertEqual(p.load_config()["OUTPUT"], "output")

    def test_atomic_replace_failure_restores_previous_files(self):
        base = p.ROOT / "tests/.runtime"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            out = Path(temp)
            d = cache()
            original = p.publish_exports(d, config(), out)
            before = {x: x.read_bytes() for x in original}
            real = p.os.replace

            def fail_docx(source, target):
                if Path(target).parent == out and Path(target).suffix == ".docx":
                    raise PermissionError("simulated Word lock")
                return real(source, target)

            with patch.object(p.os, "replace", side_effect=fail_docx):
                with self.assertRaises(p.PipelineError):
                    p.publish_exports(d, config(), out)
            self.assertEqual(before, {x: x.read_bytes() for x in original})

    def test_old_processing_fingerprint_invalidated(self):
        old = cache()
        old["processing"] = {
            "algorithm_sha256": "previous-build",
            "language_policy": 2,
            "mapping_version": 1,
        }
        old["processing_fingerprint"] = p.digest(old["processing"])
        old["state_sha256"] = p.digest(
            {k: v for k, v in old.items() if k != "state_sha256"}
        )
        new = copy.deepcopy(old["processing"])
        new.update(
            language_policy=3,
            mapping_version=2,
            translation_group_policy=1,
            build=p.BUILD,
        )
        with self.assertRaises(ValueError):
            p.validate_cache(old, old["source"], p.digest(new))

    def test_launcher_utf8_and_target(self):
        text = (p.ROOT / "START_V155.bat").read_text(encoding="utf-8")
        self.assertIn("chcp 65001", text)
        self.assertIn('"PYTHONUTF8=1"', text)
        self.assertIn('"audio_pipeline_cuda_v155_FIXED.py"', text)
        self.assertNotIn("output\\v155", text)

    def test_real_nllb_encoder_language_tokens(self):
        path = p.model_path(
            "facebook/nllb-200-distilled-600M",
            None,
            ("tokenizer.json", "config.json", "pytorch_model.bin"),
        )
        translator = p.Translator.__new__(p.Translator)
        translator.tokenizer = p.load_nllb_tokenizer(path)
        prefixes = set()
        for language in (*p.NLLB.values(), "rus_Cyrl", "zho_Hant"):
            translator.set_language(language)
            ids = translator.tokenizer("This is a test.", truncation=False)["input_ids"]
            self.assertEqual(
                ids[0], translator.tokenizer.convert_tokens_to_ids(language)
            )
            self.assertEqual(ids[-1], translator.tokenizer.eos_token_id)
            self.assertNotEqual(ids[0], translator.tokenizer.unk_token_id)
            prefixes.add(ids[0])
        self.assertEqual(
            len(prefixes), len(set(p.NLLB.values()) | {"rus_Cyrl", "zho_Hant"})
        )

    def test_bounded_alternative_failure_preserves_primary(self):
        import numpy as np

        class Backend:
            calls = 0

            def transcribe(self, audio, language):
                self.calls += 1
                raise RuntimeError("simulated alternative failure")

        backend = Backend()
        text = (
            "My whole family is actually very sad and the children are also very sad."
        )
        seg = segment(text, "af")
        u = {"start": 0, "end": 5, "language": "af"}
        p.reconcile_unit(u, [seg], [u], 0, np.zeros(80000), backend, self.lid, config())
        self.assertEqual(backend.calls, 1)
        self.assertEqual(seg["raw_text"], text)
        self.assertEqual(seg["raw_sha256"], p.text_hash(text))
        self.assertEqual(seg["language"], "en")
        self.assertEqual(seg["detected_language"], "af")
        self.assertIn("alternative_language_check_failed", seg["warnings"])


if __name__ == "__main__":
    unittest.main()
