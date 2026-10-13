"""Offline contract tests. All writes live under tests/.runtime, never legacy data."""

import copy
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import audio_pipeline_cuda_v155_FIXED as p  # noqa: E402 - project-local module, no installation


class TokenTranslator:
    def __init__(self, mode="normal"):
        self.mode = mode
        self.calls = 0
        self.source = None

    def set_language(self, source):
        self.source = source

    def count(self, text):
        return len(text) + 2

    def generate(self, text):
        self.calls += 1
        if self.mode == "fail":
            raise RuntimeError("simulated")
        if self.mode == "interrupt" and self.calls == 2:
            raise KeyboardInterrupt()
        return {
            "text": "" if self.mode == "empty" else "Русский перевод",
            "target_token_count": 1 if self.mode == "short" else len(text) + 4,
            "eos": self.mode != "no_eos",
            "hit_cap": self.mode == "cap",
            "generated_ids": [2, 3, 2],
        }


def unit(language="en"):
    return {
        "unit_id": "u00000",
        "start": 0.0,
        "end": 5.0,
        "language": language,
        "language_confidence": 0.95,
        "language_method": "whisper_audio_local",
        "candidate_language": language,
        "asr_done": False,
        "segment_ids": [],
        "raw_pieces": [],
    }


def config():
    c = copy.deepcopy(p.DEFAULTS)
    c["RESOLVED_DICTIONARIES"] = []
    return c


def segment(text="First. Second.", language="en"):
    return p.make_segment(unit(language), 0, 0.0, 5.0, text, "A", [], config())


def cache():
    source = {"path": "synthetic", "size": 10, "mtime_ns": 20, "sha256": "a" * 64}
    meta = {"synthetic": True}
    u = unit()
    s = segment()
    u["asr_done"] = True
    u["segment_ids"] = [s["segment_id"]]
    u["raw_pieces_sha256"] = p.digest([])
    data = {
        "schema_version": 2,
        "pipeline_version": p.VERSION,
        "source": source,
        "processing": meta,
        "processing_fingerprint": p.digest(meta),
        "duration": 5.0,
        "diarization": [],
        "units": [u],
        "segments": [s],
        "diarization_done": True,
        "created_at": "synthetic",
        "metrics": {},
    }
    data["state_sha256"] = p.digest(data)
    return data


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        p.validate_config(config())

    def test_real_config(self):
        self.assertEqual(p.load_config()["WHISPER_MODEL"], "large-v3")

    def test_invalid_save_interval(self):
        c = config()
        c["JSON_SAVE_INTERVAL"] = 0
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_invalid_speakers(self):
        c = config()
        c.update(MIN_SPEAKERS=3, MAX_SPEAKERS=2)
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_speakers_123(self):
        for n in (1, 2, 3):
            with self.subTest(n=n):
                c = config()
                c.update(MIN_SPEAKERS=1, MAX_SPEAKERS=n)
                p.validate_config(c)

    def test_no_force_auto_off(self):
        c = config()
        c["AUTO_LANGUAGE"] = False
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_force_codes(self):
        for code in p.ASR_LANGUAGES | {"zu"}:
            c = config()
            c["FORCE_LANGUAGE"] = code
            self.assertEqual(p.validate_config(c)["FORCE_LANGUAGE"], code)

    def test_invalid_force(self):
        c = config()
        c["FORCE_LANGUAGE"] = "xx"
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_nan(self):
        c = config()
        c["LANGUAGE_CONFIDENCE"] = float("nan")
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_dictionary_types(self):
        c = config()
        c["TCM_DICT"] = {"foo": False}
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_rate(self):
        c = config()
        c["SAMPLE_RATE"] = 48000
        with self.assertRaises(p.PipelineError):
            p.validate_config(c)

    def test_malformed_json_location(self):
        with self.temp() as d:
            path = Path(d) / "broken.json"
            path.write_text('{\n "a": }')
            with self.assertRaisesRegex(
                p.PipelineError, r"broken.json: line 2, column"
            ):
                p.read_json(path)

    def temp(self):
        base = ROOT / "tests/.runtime"
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)


class DiarizationTests(unittest.TestCase):
    def annotation(self, spans):
        return types.SimpleNamespace(
            itertracks=lambda yield_label: iter(
                (types.SimpleNamespace(start=a, end=b), None, s) for a, b, s in spans
            )
        )

    def test_short_turns(self):
        r, _ = p.normalize_diarization(
            self.annotation([(0, 0.2, "A"), (0.3, 0.8, "B")]), 1
        )
        self.assertEqual(len(r), 2)
        self.assertEqual(r[1]["speaker_id"], "B")

    def test_overlap_no_shortening(self):
        r, _ = p.normalize_diarization(
            self.annotation([(0, 10, "A"), (4, 4.8, "B")]), 10
        )
        self.assertEqual(r[0]["end"], 10)
        self.assertEqual(len(r), 2)

    def test_output_wrapper(self):
        a = self.annotation([(0, 1, "A")])
        r, e = p.normalize_diarization(
            types.SimpleNamespace(
                speaker_diarization=a, exclusive_speaker_diarization=a
            ),
            1,
        )
        self.assertEqual(r, e)

    def test_invalid_output(self):
        with self.assertRaises(p.PipelineError):
            p.normalize_diarization(None, 1)

    def test_ambiguous_attribution(self):
        speaker, overlap = p.speaker_for(
            0.5,
            1,
            [
                {"start": 0, "end": 2, "speaker_id": "A"},
                {"start": 0.4, "end": 1, "speaker_id": "B"},
            ],
        )
        self.assertEqual(set(overlap), {"A", "B"})

    def test_no_global_speaker_language(self):
        a = segment("Hello", "en")
        b = segment("Привет", "ru")
        self.assertEqual(a["speaker_id"], b["speaker_id"])
        self.assertNotEqual(a["language"], b["language"])

    def test_full_timeline(self):
        import numpy as np

        audio = np.zeros(16000 * 31, dtype="float32")
        units = p.initial_units(audio, config())
        self.assertEqual(units[0]["start"], 0)
        self.assertAlmostEqual(units[-1]["end"], 31)
        for a, b in zip(units, units[1:]):
            self.assertEqual(a["end"], b["start"])

    def test_local_language_switch(self):
        import numpy as np

        c = config()
        c["ASR_UNIT_SECONDS"] = 12
        audio = np.concatenate([np.zeros(6 * 16000), np.ones(6 * 16000)])

        class B:
            def detect(self, a):
                return ("ru" if float(a.mean()) < 0.5 else "en", 0.99)

        units = p.language_units(audio, B(), c)
        self.assertEqual({u["language"] for u in units}, {"ru", "en"})

    def test_low_confidence_not_english(self):
        import numpy as np

        b = types.SimpleNamespace(detect=lambda a: ("fr", 0.1))
        units = p.language_units(np.zeros(16000 * 3), b, config())
        self.assertEqual(units[0]["language"], "unknown")
        self.assertEqual(units[0]["candidate_language"], "fr")

    def test_zulu_explicit(self):
        with self.assertRaisesRegex(p.PipelineError, "Zulu ASR unsupported"):
            p.UnsupportedZuluBackend().transcribe([], "zu")


class TranslationTests(unittest.TestCase):
    def test_all_mappings(self):
        for lang, code in p.NLLB.items():
            with self.subTest(language=lang):
                s = segment("Synthetic source.", lang)
                s["language"] = lang
                t = TokenTranslator()
                p.translate_segment(
                    s, t, config(), target_language="en" if lang == "ru" else "ru"
                )
                self.assertEqual(t.source, code)

    def test_ru_bypass(self):
        s = segment("Русский текст", "ru")
        t = TokenTranslator()
        p.translate_segment(s, t, config())
        self.assertEqual(t.calls, 0)
        self.assertIsNone(s["translation_ru"])
        self.assertEqual(s["translation_status"], "not_required")

    def test_off(self):
        s = segment()
        c = config()
        c["TRANSLATE_MODE"] = "off"
        p.translate_segment(s, None, c)
        self.assertEqual(s["translation_status"], "disabled")

    def test_unknown_not_english(self):
        s = segment(language="unknown")
        t = TokenTranslator()
        p.translate_segment(s, t, config())
        self.assertEqual(t.calls, 0)
        self.assertEqual(s["translation_status"], "unsupported_language")

    def test_short_chinese(self):
        s = segment("你好", "zh")
        t = TokenTranslator()
        p.translate_segment(s, t, config())
        self.assertEqual(t.calls, 1)

    def test_raw_immutable(self):
        c = config()
        c["TERMS"] = {"合谷": "Хэ Гу", "very very": "very"}
        for raw, lang in [
            ("合谷", "zh"),
            ("very very good", "en"),
            ("Thank you. Look at the token.", "en"),
        ]:
            s = p.make_segment(unit(lang), 0, 0, 2, raw, "A", [], c)
            p.translate_segment(s, TokenTranslator(), c)
            self.assertEqual(s["raw_text"], raw)
            self.assertEqual(s["corrected_text"], raw)

    def test_sentences(self):
        text = "First. Second! Third?  "
        spans = p.sentence_spans(text)
        self.assertEqual("".join(text[a:b] for a, b in spans), text)
        self.assertEqual(len(spans), 3)

    def test_abbreviation_decimal(self):
        text = "Dr. Smith measured 2.5 cm. Next."
        spans = p.sentence_spans(text)
        self.assertEqual(len(spans), 2)

    def test_budgets(self):
        for length in (509, 510, 511, 512, 513, 1001, 1800):
            with self.subTest(length=length):
                text = "甲" * length
                t = TokenTranslator()
                spans = p.translation_spans(text, t.count, 512)
                self.assertEqual("".join(text[a:b] for a, b in spans), text)
                self.assertTrue(all(t.count(text[a:b]) <= 512 for a, b in spans))

    def test_unpunctuated_coverage(self):
        text = "word " * 400
        t = TokenTranslator()
        spans = p.translation_spans(text, t.count, 192)
        self.assertEqual("".join(text[a:b] for a, b in spans), text)

    def test_eos_not_complete(self):
        s = segment()
        p.translate_segment(s, TokenTranslator(), config())
        self.assertEqual(s["translation_status"], "needs_review")
        self.assertEqual(s["source_coverage"], 1)

    def test_shortening_retry(self):
        s = segment("A fairly long sentence with a lot of words.")
        t = TokenTranslator("short")
        p.translate_segment(s, t, config())
        self.assertGreater(t.calls, 1)
        self.assertNotEqual(s["translation_status"], "complete")

    def test_cap_partial(self):
        s = segment()
        p.translate_segment(s, TokenTranslator("cap"), config())
        self.assertEqual(s["translation_status"], "partial")

    def test_empty_generation(self):
        s = segment()
        p.translate_segment(s, TokenTranslator("empty"), config())
        self.assertEqual(s["translation_status"], "failed")

    def test_failed_generation(self):
        s = segment()
        p.translate_segment(s, TokenTranslator("fail"), config())
        self.assertEqual(s["translation_status"], "failed")

    def test_missing_eos(self):
        s = segment()
        p.translate_segment(s, TokenTranslator("no_eos"), config())
        self.assertEqual(s["translation_status"], "partial")

    def test_interrupt_resume(self):
        s = segment()
        t = TokenTranslator("interrupt")
        saved = []
        with self.assertRaises(KeyboardInterrupt):
            p.translate_segment(s, t, config(), lambda: saved.append(copy.deepcopy(s)))
        self.assertEqual(len(saved), 1)
        self.assertEqual(s["chunks"][0]["status"], "needs_review")
        t2 = TokenTranslator()
        p.translate_segment(s, t2, config())
        self.assertEqual(t2.calls, 1)

    def test_raw_tamper(self):
        s = segment()
        s["raw_text"] = "modified"
        with self.assertRaises(p.PipelineError):
            p.translate_segment(s, TokenTranslator(), config())

    def test_gap_validation(self):
        ch = p.chunk_record("abc", 1, 3, TokenTranslator().count)
        with self.assertRaises(ValueError):
            p.validate_chunks("abc", [ch])

    def test_chinese_script(self):
        c = config()
        c["CHINESE_SCRIPT"] = "Hant"
        self.assertEqual(p.nllb_source("zh", "漢字", c)[0], "zho_Hant")


class CacheTests(unittest.TestCase):
    def test_valid(self):
        d = cache()
        p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_incompatibility(self):
        for field, value in [
            ("schema_version", 1),
            ("pipeline_version", "old"),
            ("processing_fingerprint", "wrong"),
        ]:
            d = cache()
            source = copy.deepcopy(d["source"])
            fp = d["processing_fingerprint"]
            d[field] = value
            with self.assertRaises(ValueError):
                p.validate_cache(d, source, fp)

    def test_wrong_source(self):
        d = cache()
        source = copy.deepcopy(d["source"])
        source["sha256"] = "other"
        with self.assertRaises(ValueError):
            p.validate_cache(d, source, d["processing_fingerprint"])

    def test_invalid_done(self):
        d = cache()
        d["units"][0]["asr_done"] = "false"
        with self.assertRaises(ValueError):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_bad_raw(self):
        d = cache()
        d["segments"][0]["raw_text"] = "different"
        with self.assertRaises(ValueError):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_nan_time(self):
        d = cache()
        d["segments"][0]["start"] = float("nan")
        with self.assertRaises(ValueError):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_duplicate_ids(self):
        d = cache()
        d["segments"].append(copy.deepcopy(d["segments"][0]))
        with self.assertRaises(ValueError):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_missing_asr(self):
        d = cache()
        d["segments"] = []
        with self.assertRaises(ValueError):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_metadata_tamper(self):
        d = cache()
        d["processing"]["synthetic"] = False
        with self.assertRaises(ValueError):
            p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_fingerprint_changes(self):
        base = {
            "pipeline": "1",
            "whisper": "large-v3",
            "translation": "nllb",
            "language": "auto",
            "speakers": 2,
            "source": "sha",
            "decode": 5,
            "dict": "a",
            "audio": "16k",
        }
        for key in base:
            changed = {**base, key: "different"}
            self.assertNotEqual(p.digest(base), p.digest(changed))

    def test_corrupt_preserved(self):
        root = ROOT / "tests/.runtime"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            f = Path(tmp)
            (f / "resume.json").write_text("[]")
            data, new = p.read_cache(f, {}, "x")
            self.assertIsNone(data)
            self.assertNotEqual(new, f)
            self.assertEqual((f / "resume.json").read_text(), "[]")

    def test_atomic_roundtrip(self):
        root = ROOT / "tests/.runtime"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            file = Path(tmp) / "cache.json"
            p.atomic_write_json(file, {"hello": "世界"})
            self.assertEqual(p.read_json(file), {"hello": "世界"})
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_path_escape(self):
        with self.assertRaises(p.PipelineError):
            p.inside_root(ROOT.parent / "escaped")


class ExportTests(unittest.TestCase):
    def test_hours(self):
        self.assertEqual(p.format_time(3661), "01:01:01")

    def test_heading(self):
        s = segment()
        s.update(start=3661, end=3663, speaker_role="ДОКЛАДЧИК")
        self.assertIn("01:01:01", p.segment_heading(s))
        self.assertIn("ДОКЛАДЧИК", p.segment_heading(s))

    def test_no_false_complete(self):
        d = cache()
        d["segments"][0]["translation_status"] = "needs_review"
        self.assertEqual(p.exported_status(d), "needs_review")

    def test_empty_visible_status(self):
        d = cache()
        d["segments"][0]["transcription_status"] = "empty"
        self.assertEqual(p.exported_status(d), "partial")


if __name__ == "__main__":
    unittest.main(verbosity=2)
