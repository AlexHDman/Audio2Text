"""Regression tests for defects discovered in self-review and the LIVE smoke."""

import copy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v155 import cache, config, segment, TokenTranslator
import audio_pipeline_cuda_v155_FIXED as p


class ReviewTests(unittest.TestCase):
    def test_language_switch_in_middle_not_just_edges(self):
        import numpy as np

        audio = np.concatenate(
            [np.zeros(6 * 16000), np.ones(6 * 16000), np.zeros(12 * 16000)]
        )

        class Backend:
            def detect(self, clip):
                return ("ru" if clip.mean() > 0.5 else "en", 0.99)

        spans = p.language_units(audio, Backend(), config())
        self.assertEqual([u["language"] for u in spans], ["en", "ru", "en"])
        self.assertEqual(spans[0]["start"], 0)
        self.assertEqual(spans[-1]["end"], 24)
        for left, right in zip(spans, spans[1:]):
            self.assertEqual(left["end"], right["start"])

    def test_role_scope(self):
        c = config()
        c["SPEAKER_ROLES"] = {"a" * 64 + ":" + "b" * 64: {"A": "ДОКЛАДЧИК"}}
        p.validate_config(c)
        c["SPEAKER_ROLES"] = {"a" * 64: {"A": "ДОКЛАДЧИК"}}
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_no_ignored_model(self):
        c = config()
        c["WHISPER_MODEL"] = "tiny"
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_state_checksum(self):
        d = cache()
        d["segments"][0]["translation_ru"] = "tampered"
        with self.assertRaisesRegex(ValueError, "checksum"):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_raw_piece_integrity(self):
        d = cache()
        d["units"][0]["raw_pieces"] = [{"text": "changed"}]
        d["state_sha256"] = p.digest(
            {k: v for k, v in d.items() if k != "state_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "raw ASR pieces"):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_timeline_gap(self):
        d = cache()
        d["units"][0]["start"] = 1
        d["state_sha256"] = p.digest(
            {k: v for k, v in d.items() if k != "state_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "timeline"):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_complete_requires_review(self):
        d = cache()
        d["segments"][0]["translation_status"] = "complete"
        d["state_sha256"] = p.digest(
            {k: v for k, v in d.items() if k != "state_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "semantic review"):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_recovery_resumes(self):
        base = p.ROOT / "tests/.runtime"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            folder = Path(temp) / "base"
            folder.mkdir()
            (folder / "resume.json").write_text("[]")
            d = cache()
            source = d["source"]
            fp = d["processing_fingerprint"]
            _, recovery = p.read_cache(folder, source, fp)
            p.atomic_write_json(recovery / "resume.json", d)
            found, where = p.read_cache(folder, source, fp)
            self.assertEqual(where, recovery)
            self.assertEqual(found, d)

    def test_retry_children_interrupt(self):
        class T(TokenTranslator):
            def generate(self, text):
                self.calls += 1
                if self.calls == 3:
                    raise KeyboardInterrupt()
                return {
                    "text": "Переведённое предложение",
                    "target_token_count": 1 if self.calls == 1 else len(text) + 5,
                    "eos": True,
                    "hit_cap": False,
                    "generated_ids": [2, 3, 2],
                }

        s = segment("A fairly long sentence that needs a retry.")
        t = T()
        snapshots = []
        with self.assertRaises(KeyboardInterrupt):
            p.translate_segment(
                s, t, config(), lambda: snapshots.append(copy.deepcopy(s))
            )
        ch = s["chunks"][0]
        self.assertTrue(ch["children"])
        self.assertEqual(ch["children"][0]["status"], "needs_review")
        self.assertTrue(p.pending_chunk(ch))
        t2 = TokenTranslator()
        p.translate_segment(s, t2, config())
        self.assertEqual(t2.calls, 1)
        self.assertFalse(p.pending_chunk(ch))

    def test_failed_child_retry(self):
        s = segment("A long statement with enough words.")
        c = config()
        c["TRANSLATION_RETRY_DEPTH"] = 1

        class T(TokenTranslator):
            def generate(self, text):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError()
                return {
                    "text": "Часть",
                    "target_token_count": 1,
                    "eos": True,
                    "hit_cap": False,
                    "generated_ids": [2],
                }

        p.translate_segment(s, T(), c)
        self.assertEqual(s["translation_status"], "partial")
        t = TokenTranslator()
        p.translate_segment(s, t, c, retry=True)
        self.assertEqual(s["translation_status"], "needs_review")

    def test_local_context_retry(self):
        import numpy as np

        class B:
            def __init__(self):
                self.i = 0

            def detect(self, a):
                self.i += 1
                return ("en", 0.4 if self.i == 1 else 0.9)

        c = config()
        c["ASR_UNIT_SECONDS"] = 24
        u = p.language_units(np.zeros(16000 * 4), B(), c)[0]
        self.assertEqual(u["language"], "en")
        self.assertIn("full_unit", u["language_method"])

    def test_actual_token_boundaries(self):
        from tokenizers import Tokenizer

        path = p.model_path(
            "facebook/nllb-200-distilled-600M", None, ("tokenizer.json",)
        )
        tokenizer = Tokenizer.from_file(str(path / "tokenizer.json"))
        tokenizer.no_truncation()

        def count(text):
            return len(tokenizer.encode(text).ids)

        for target in (511, 512, 513, 1002):
            text = ("word " * (target - 2)).strip()
            self.assertEqual(count(text), target)
            spans = p.translation_spans(text, count, 512)
            self.assertEqual("".join(text[a:b] for a, b in spans), text)
            self.assertTrue(all(count(text[a:b]) <= 512 for a, b in spans))

    def test_cuda_unavailable_fallback(self):
        fake = types.SimpleNamespace(
            set_num_threads=lambda n: None,
            cuda=types.SimpleNamespace(is_available=lambda: False),
            version=types.SimpleNamespace(cuda=None),
            __version__="synthetic",
        )
        with patch.dict(sys.modules, {"torch": fake}):
            r = p.runtime_info(config())
            self.assertEqual(r["device"], "cpu")
            self.assertEqual(r["compute_type"], "int8")
            c = config()
            c["DEVICE"] = "cuda"
            with self.assertRaises(p.PipelineError):
                p.runtime_info(c)

    def test_final_export_contract(self):
        from zipfile import ZipFile
        from lxml import etree

        base = p.ROOT / "tests/.runtime"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            d = cache()
            s = d["segments"][0]
            s.update(
                language="ru",
                raw_text="Русский текст",
                raw_sha256=p.text_hash("Русский текст"),
                corrected_text="Русский текст",
                translation_status="not_required",
            )
            # Separate Hebrew record exercises actual bidi/complex font markup.
            he = segment("שלום. הפגישה מתחילה מחר.", "he")
            he["segment_id"] = "he"
            he["translation_status"] = "disabled"
            d["segments"].append(he)
            paths = p.export_all(d, config(), Path(temp))
            payload = p.read_json(paths[0])
            sha = payload.pop("export_sha256")
            self.assertEqual(sha, p.digest(payload))
            self.assertNotIn("state_sha256", payload)
            self.assertEqual(payload["artifact_type"], "transcript")
            txt = paths[1].read_text(encoding="utf-8")
            self.assertIn("Русский текст", txt)
            self.assertNotIn("AI перевод:", txt)
            with ZipFile(paths[2]) as z:
                xml = etree.fromstring(z.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            self.assertEqual(len(xml.findall(".//w:bidi", ns)), 1)
            rtl = xml.find(".//w:bidi/..", ns)
            self.assertEqual(rtl.find("w:jc", ns).get("{" + ns["w"] + "}val"), "start")


class LiveRegressionTests(unittest.TestCase):
    def test_runaway_translation_is_retained_but_not_presented_as_translation(self):
        class LoopTranslator:
            def generate(self, text):
                return {
                    "text": "Они любили его. " + "they loved him " * 50,
                    "generated_ids": [2, 4, 5, 6] * 50,
                    "target_token_count": 199,
                    "hit_cap": True,
                    "eos": False,
                }

        c = config()
        c["TRANSLATION_RETRY_DEPTH"] = 0
        ch = p.chunk_record("they loved him", 0, 14, lambda text: 7)
        p.translate_chunk(ch, LoopTranslator(), c)
        self.assertEqual(ch["status"], "failed")
        self.assertIsNone(ch["translation_ru"])
        self.assertEqual(ch["source_text"], "they loved him")
        self.assertIn("they loved him " * 50, ch["attempts"][0]["text"])

    def test_intentional_source_repetition_is_not_removed(self):
        self.assertFalse(p.degenerate_translation("yes " * 30, "да " * 30))
        self.assertFalse(p.degenerate_translation("Yes.", "Да да."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
