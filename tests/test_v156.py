"""Translation-only upgrade contracts; no network or ASR inference."""

import copy
import tempfile
import unittest
from pathlib import Path

import audio_pipeline_cuda_v155_FIXED as old
import audio_pipeline_cuda_v156 as p
import translation_v156 as mt
from test_v155 import config, segment


class Backend:
    def __init__(self, output=None):
        self.calls = []
        self.output = output

    def set_language(self, language):
        self.language = language

    def count(self, text):
        return len(text.split()) + 2

    def generate(self, text):
        self.calls.append((text, self.language, self.target_language))
        value = (
            self.output(text)
            if self.output
            else (
                "Мы встретимся завтра вместе."
                if self.target_language == "ru"
                else "We will meet together tomorrow."
            )
        )
        return {
            "text": value,
            "generated_ids": [2, 3, 2],
            "target_token_count": len(value.split()) + 2,
            "eos": True,
            "hit_cap": False,
        }


def record(text="Ons sal môre saam vergader.", language="af", target="en"):
    r = segment(text, language)
    if target == "en":
        r["translation_en"] = None
    r["translation_context"] = {"source_language": language, "flags": []}
    return r


class V156Tests(unittest.TestCase):
    def test_wrong_lid_score_does_not_reject_valid_russian(self):
        class WrongLID:
            def assess(self, text):
                return {"strong": True, "language": "bg"}

        t = Backend(
            lambda text: "Тогда я не отвечаю на его звонок, затем он звонит мне снова."
        )
        t.quality_lid = WrongLID()
        r = record("Dan vat ek nie sy oproep nie.")
        mt.translate_group(p, r, t, config(), lambda: None, target="ru")
        self.assertIsNotNone(r["translation_ru"])
        self.assertEqual(r["translation_status"], "needs_review")
        self.assertIn("output_lid_disagreement", r["quality"]["flags"])

    def test_negation_loss_is_concrete_review_reason(self):
        result = {
            "text": "We will do this tomorrow.",
            "generated_ids": [],
            "target_token_count": 8,
            "eos": True,
            "hit_cap": False,
        }
        self.assertIn(
            "negation_coverage_review",
            mt.defects(p, "Ons sal dit nie doen nie.", result, 9, "en"),
        )

    def test_quality_attempt_tamper_is_rejected(self):
        r = record()
        mt.translate_group(p, r, Backend(), config(), lambda: None, target="en")
        r["quality"]["attempts"][0]["chunks"][0]["source_text"] += " changed"
        with self.assertRaises(ValueError):
            mt.validate_quality(p, r, "en")

    def test_reviewed_group_status_is_propagated_without_asr_change(self):
        from test_v155 import cache

        d = cache()
        d["pipeline_version"] = p.VERSION
        d["translation_groups"] = p.build_translation_groups(d["segments"])
        d["translation_groups"][0].update(
            translation_status="complete", semantic_validation="reviewed"
        )
        before = d["segments"][0]["raw_text"]
        p.sync_group_status(d)
        self.assertEqual(d["segments"][0]["semantic_validation"], "reviewed")
        self.assertEqual(d["segments"][0]["raw_text"], before)
        d["state_sha256"] = p.digest(
            {k: v for k, v in d.items() if k != "state_sha256"}
        )
        p.validate_cache(d, d["source"], d["processing_fingerprint"])

    def test_second_sentence_is_not_silently_dropped(self):
        text = "A first sentence. Another complete thought."
        r = record(text)
        t = Backend(
            lambda s: "Первая фраза."
            if s != "Another complete thought."
            else "Другая законченная мысль."
        )
        mt.translate_group(p, r, t, config(), lambda: None, target="ru")
        self.assertEqual(r["translation_ru"], "Первая фраза. Другая законченная мысль.")
        self.assertTrue(r["quality"]["coverage_probe"]["sentence_count_loss"])

    def test_tiny_first_sentence_is_kept_separate(self):
        text = "Special way. Another longer sentence with extra context."
        spans = mt.clause_spans(p, text, Backend().count, 192)
        self.assertEqual(text[slice(*spans[0])], "Special way. ")

    def test_rejected_generation_stays_in_attempts_not_reading_channel(self):
        r = record("Ons praat oor die vergadering.")
        mt.translate_group(
            p,
            r,
            Backend(lambda _: "<unk> !!!!!!!!!!"),
            config(),
            lambda: None,
            target="en",
        )
        self.assertEqual(r["translation_status"], "failed")
        self.assertIsNone(r["translation_en"])
        self.assertIn("<unk>", r["quality"]["attempts"][0]["text"])

    def test_baseline_is_frozen(self):
        self.assertEqual(p.file_hash(Path(old.__file__)), mt.BASELINE_SHA)
        self.assertEqual(mt.core_hash(p, p.__file__), mt.core_hash(p, old.__file__))
        import ast

        def body(module, name):
            return ast.dump(
                next(
                    n
                    for n in ast.parse(Path(module.__file__).read_text("utf8")).body
                    if getattr(n, "name", None) == name
                ),
                include_attributes=False,
            )

        self.assertEqual(body(p, "export_all"), body(old, "export_all"))

    def test_entire_group_reaches_model(self):
        r = record()
        t = Backend()
        mt.translate_group(p, r, t, config(), lambda: None, target="en")
        self.assertEqual(t.calls[0][0], r["raw_text"])
        self.assertEqual(r["source_coverage"], 1)

    def test_af_and_nl_routes(self):
        for lang in ["af", "nl"]:
            r = record(language=lang)
            t = Backend()
            mt.translate_group(p, r, t, config(), lambda: None, target="en")
            self.assertEqual(t.calls[0][1], p.NLLB[lang])

    def test_independent_ru_en(self):
        t = Backend()
        for target in ["ru", "en"]:
            r = record(target=target)
            mt.translate_group(p, r, t, config(), lambda: None, target=target)
        self.assertEqual([x[0] for x in t.calls], [r["raw_text"]] * 2)
        self.assertEqual([x[2] for x in t.calls], ["ru", "en"])

    def test_afnl_conflict_never_changes_original(self):
        evidence = {"strong": True, "language": "nl"}
        r = mt.route("en ons het nie hom geken maar hy was uniek", "nl", evidence, [])
        self.assertEqual(r["original_language"], "nl")
        self.assertEqual(r["source_language"], "af")
        self.assertIn("uncertain_source_language", r["flags"])
        dutch = mt.route(
            "jij kunt hem zien en wij hebben zijn documenten", "nl", evidence, []
        )
        self.assertEqual(dutch["source_language"], "nl")

    def test_context_is_bounded_same_speaker(self):
        groups = [
            {
                "group_id": str(i),
                "speaker_id": "A",
                "language": "af",
                "raw_sha256": "h",
                "raw_text": "neighbor",
                "start": i * 3,
                "end": i * 3 + 2,
            }
            for i in range(3)
        ]
        self.assertEqual(len(mt.context_for(groups, 1)), 2)
        groups[0]["speaker_id"] = "B"
        groups[2]["start"] = 100
        self.assertFalse(mt.context_for(groups, 1))

    def test_context_route_cannot_leak_neighbor(self):
        r = record(language="nl")
        r["translation_context"] = {
            "source_language": "af",
            "flags": [],
            "neighbors": [{"text": "SECRET NEIGHBOR TEXT"}],
        }
        t = Backend()
        mt.translate_group(p, r, t, config(), lambda: None, target="en")
        self.assertEqual(len(t.calls), 2)
        self.assertTrue(all(c[0] == r["raw_text"] for c in t.calls))

    def test_missing_beginning_detected_and_retried(self):
        text = "I love cooking food, my wife stays here, we share this kitchen, he calls me later."

        def output(src):
            if src == text:
                return "My wife stays here, we share this kitchen, he calls me later."
            return src.strip()

        # Use distinct translations so source-copy detection does not dominate the test.
        mapping = {
            "I love cooking food, ": "I enjoy preparing meals.",
            "my wife stays here, ": "My partner stays here.",
            "we share this kitchen, ": "We use this kitchen.",
            "he calls me later.": "He phones me later.",
        }

        def translate(src):
            return output(src) if src == text else mapping[src]

        r = record(text)
        t = Backend(translate)
        mt.translate_group(p, r, t, config(), lambda: None, target="en")
        self.assertEqual(r["quality"]["coverage_probe"]["missing_clause_indices"], [0])
        self.assertEqual(r["quality"]["strategy"], "semantic_clauses")
        self.assertTrue(r["translation_en"].startswith("I enjoy preparing meals."))
        self.assertEqual("".join(c["source_text"] for c in r["chunks"]), text)

    def test_rejects_bad_outputs(self):
        values = [
            ".............",
            "yes " * 30,
            "<unk> translation",
            "Only.",
            "this original source contains a number of separate words",
        ]
        source = "this original source contains a number of separate words"
        for value in values:
            with self.subTest(value=value):
                result = {
                    "text": value,
                    "generated_ids": [2],
                    "target_token_count": len(value.split()),
                    "eos": True,
                    "hit_cap": False,
                }
                self.assertTrue(mt.defects(p, source, result, 20, "en"))

    def test_short_reply_does_not_invent_subject(self):
        r = record("Ja,")
        t = Backend(lambda _: "Yes, I did.")
        mt.translate_group(p, r, t, config(), lambda: None, target="en")
        self.assertEqual(r["translation_en"], "Yes.")
        self.assertEqual(len(r["quality"]["attempts"]), 1)

    def test_no_silent_token_truncation(self):
        text = "First complete clause. Second complete clause. Third complete clause."
        t = Backend()
        spans = mt.clause_spans(p, text, t.count, 7)
        self.assertEqual("".join(text[a:b] for a, b in spans), text)
        self.assertTrue(all(t.count(text[a:b]) <= 7 for a, b in spans))

    def test_interruption_reuses_completed_attempt(self):
        r = record(
            "First complete clause, second complete clause, third complete clause, last complete clause."
        )
        t = Backend()
        original = t.generate

        def interrupt(text):
            if len(t.calls) == 2:
                raise KeyboardInterrupt
            return original(text)

        t.generate = interrupt
        with self.assertRaises(KeyboardInterrupt):
            mt.translate_group(p, r, t, config(), lambda: None, target="en")
        done = len(t.calls)
        t.generate = original
        mt.translate_group(p, r, t, config(), lambda: None, target="en")
        self.assertEqual(t.calls[0][0], r["raw_text"])
        self.assertEqual(sum(c[0] == r["raw_text"] for c in t.calls), 1)
        self.assertGreater(len(t.calls), done)

    def test_asr_identity_ignores_translation_but_not_decoding(self):
        meta = {
            "config": {"BEAM_SIZE": 5, "TRANSLATION_BEAMS": 4},
            "runtime": {"device": "cuda", "translation_device": "cpu"},
            "models": {"whisper": "same", "translator": "old"},
            "libraries": {"torch": "same", "transformers": "old"},
        }
        h = mt.asr_identity(p, meta, "core")
        new = copy.deepcopy(meta)
        new["models"]["translator"] = "new"
        new["config"]["TRANSLATION_BEAMS"] = 8
        self.assertEqual(h, mt.asr_identity(p, new, "core"))
        new["config"]["BEAM_SIZE"] = 6
        self.assertNotEqual(h, mt.asr_identity(p, new, "core"))
        self.assertNotEqual(h, mt.asr_identity(p, meta, "changed-core"))

    def test_cache_reuses_accepted_asr(self):
        from unittest.mock import patch
        from test_v155 import cache

        # A checksum-valid v155 predecessor, entirely owned by this test.
        fixture = cache()
        fixture["segments"][0] = segment("Ons sal môre saam vergader.", "af")
        fixture["units"][0]["language"] = "af"
        fixture["diarization"] = [{"start": 0.0, "end": 5.0, "speaker_id": "A"}]
        fixture["translation_groups"] = old.build_translation_groups(fixture["segments"])
        fixture["translation_groups"][0].update(translation_status="needs_review", translation_ru="Старый перевод")
        fixture["processing"] = {
            "config": config(), "runtime": {"device": "cpu"},
            "models": {"translator": "synthetic-nllb"}, "libraries": {},
            "algorithm_sha256": mt.BASELINE_SHA,
        }
        fixture["processing_fingerprint"] = old.digest(fixture["processing"])
        fixture["state_sha256"] = old.digest({k: v for k, v in fixture.items() if k != "state_sha256"})
        old.validate_cache(fixture, fixture["source"], fixture["processing_fingerprint"])
        meta = copy.deepcopy(fixture["processing"])
        meta.update(stage_policy=mt.stage_policy(p), pipeline_version=p.VERSION,
                    algorithm_sha256=p.file_hash(Path(p.__file__)))
        with tempfile.TemporaryDirectory(dir=p.ROOT / "tests/.runtime") as tmp:
            isolated = Path(tmp)
            base = isolated / "temp/v156"
            predecessor = isolated / "temp/v155" / (fixture["source"]["sha256"][:20] + "-synthetic")
            predecessor.mkdir(parents=True)
            saved = predecessor / "resume.json"
            old.atomic_write_json(saved, fixture)
            original = saved.read_bytes()
            with patch.object(p, "ROOT", isolated):
                result = mt.reuse_stages(p, base, fixture["source"], meta)
                self.assertIsNotNone(result)
                self.assertEqual(result["units"], fixture["units"])
                self.assertEqual(result["diarization"], fixture["diarization"])
                for before, after in zip(fixture["segments"], result["segments"], strict=True):
                    self.assertEqual(before, after)
                self.assertEqual(len(result["translation_groups"]), 1)
                group = result["translation_groups"][0]
                self.assertEqual(group["raw_text"], fixture["segments"][0]["raw_text"])
                self.assertEqual(group["translation_status"], "pending")
                self.assertIsNone(group["translation_ru"])
                self.assertEqual(group["previous_translation"]["translation_ru"], "Старый перевод")
                self.assertEqual(group["chunks"], [])
                self.assertTrue(result["reuse_provenance"]["asr_reused"])
                self.assertEqual(Path(result["reuse_provenance"]["cache"]), saved)
                self.assertEqual(saved.read_bytes(), original)
                # A changed ASR setting and corrupt checksum must both reject reuse.
                changed = copy.deepcopy(meta)
                changed["config"]["BEAM_SIZE"] += 1
                self.assertIsNone(mt.reuse_stages(p, base, fixture["source"], changed))
                fixture["segments"][0]["raw_text"] += " tampered"
                old.atomic_write_json(saved, fixture)
                self.assertIsNone(mt.reuse_stages(p, base, fixture["source"], meta))


if __name__ == "__main__":
    unittest.main()
