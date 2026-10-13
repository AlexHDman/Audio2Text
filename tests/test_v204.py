"""Language policy regression tests: real adapter, no inference or shared cache."""

import copy
import io
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import backend_contract_v1 as contract
import backend_runtime_v157 as runtime
import language_control_v204 as policy
import translation_v156 as mt


class LanguageControlTests(unittest.TestCase):
    def setUp(self):
        self.paths = contract.AppPaths.create()
        self.api = runtime.load_engine(self.paths)
        self.config = copy.deepcopy(self.api.DEFAULTS)

    def observer(self):
        events = contract.EventStream(io.StringIO())
        return runtime.Observer(
            self.api, self.paths, events, contract.Telemetry(events), self.config
        )

    def test_auto_leaves_inference_functions_unchanged(self):
        original = self.api.reconcile_unit
        policy.configure(self.config, "auto")
        with self.observer() as observer:
            self.assertNotIn("ALLOWED_SOURCE_LANGUAGES", self.config)
            self.assertNotIn("TARGET_LANGUAGE", self.config)
            # The existing observer transparently wraps the same reconciliation.
            self.assertIsNotNone(observer)
        self.assertIs(self.api.reconcile_unit, original)

    def test_invalid_selection_is_rejected(self):
        for selection in ("", "af,af", "af,en,nl,ru", "xx", "en, af"):
            with self.assertRaises(ValueError):
                policy.configure(copy.deepcopy(self.config), selection)
        with self.assertRaises(ValueError):
            policy.configure(self.config, "auto", "xx")
        self.config["FORCE_LANGUAGE"] = "af"
        with self.assertRaises(ValueError):
            policy.configure(self.config, "af,en")

    def test_audio_candidates_constrained_without_inflating_confidence(self):
        self.assertEqual(
            policy.select_audio(
                [("nl", 0.98), ("af", 0.015), ("en", 0.005)], ["af", "en"]
            ),
            ("af", 0.015),
        )
        with self.assertRaises(ValueError):
            policy.select_audio([("nl", 1)], ["en"])

    def test_dutch_not_blindly_renamed(self):
        nl = {"language": "nl", "strong": True, "score": 0.99}
        self.assertEqual(
            policy.resolve("af", nl, "Wij hebben het niet gezien", ["af", "en"])[0],
            "unknown",
        )
        self.assertEqual(
            policy.resolve(
                "unknown", nl, "Hy het nie hulle woorde gehoor nie", ["af", "en"]
            )[0],
            "af",
        )
        self.assertEqual(
            policy.resolve(
                "en", {"language": "de", "strong": True}, "Deutsch", ["af", "en"]
            )[0],
            "unknown",
        )

    def test_reconciliation_preserves_raw_and_requests_review(self):
        policy.configure(self.config, "af,en", "ru")
        seg = {
            "raw_text": "Wij hebben het niet gezien",
            "raw_sha256": "immutable",
            "language": "af",
            "language_confidence": 0.1,
            "warnings": [],
            "transcription_status": "complete",
        }
        unit = {"unit_id": "u1", "language": "unknown"}
        lid = SimpleNamespace(
            assess=lambda text: {"language": "nl", "strong": True, "score": 0.99}
        )
        with self.observer():
            self.api.reconcile_unit(
                unit, [seg], [unit], 0, None, None, lid, self.config
            )
        self.assertEqual(seg["language"], "unknown")
        self.assertEqual(seg["resolved_language"], "unknown")
        self.assertEqual(seg["raw_text"], "Wij hebben het niet gezien")
        self.assertEqual(seg["raw_sha256"], "immutable")
        self.assertIn("uncertain_language", seg["warnings"])
        self.assertEqual(seg["transcription_status"], "needs_review")

    def test_whitelist_and_target_enter_processing_and_stage_identity(self):
        base = {
            "config": {},
            "runtime": {},
            "models": {},
            "libraries": {},
            "translation_channels": ["ru", "en"],
        }
        identities = []
        for source, target in [
            ("auto", "ru"),
            ("af,en", "ru"),
            ("af,en", "en"),
            ("af,nl", "ru"),
        ]:
            self.config = copy.deepcopy(self.api.DEFAULTS)
            policy.configure(self.config, source, target)
            with patch.object(
                self.api,
                "processing_metadata",
                lambda *a: {
                    **copy.deepcopy(base),
                    "config": copy.deepcopy(self.config),
                },
            ):
                with self.observer():
                    meta = self.api.processing_metadata()
            identities.append(
                (self.api.digest(meta), mt.asr_identity(self.api, meta, "core"))
            )
        self.assertEqual(len({i[0] for i in identities}), 4)
        self.assertEqual(len({i[1] for i in identities}), 4)

    def test_target_ru_disables_en_and_blocks_nl_route(self):
        policy.configure(self.config, "af,en", "ru")
        group = {
            "language": "af",
            "raw_text": "Hy het nie gehoor nie",
            "raw_sha256": "hash",
            "translation_status": "pending",
            "translation_context": {"source_language": "nl", "flags": []},
        }
        data = {"translation_groups": [group]}
        with self.observer():
            mt.prepare_routing(self.api, data, self.config)
        self.assertEqual(group["translation_context"]["source_language"], "af")
        self.assertEqual(group["english"]["translation_status"], "not_required")
        self.assertIsNone(group["english"]["translation_en"])
        self.assertEqual(group["translation_status"], "pending")

    def test_russian_source_bypasses_ru_translation(self):
        policy.configure(self.config, "ru,af,en", "ru")
        raw = "Русский исходный текст"
        group = {
            "group_id": "g1",
            "speaker_id": "S1",
            "language": "ru",
            "raw_text": raw,
            "raw_sha256": self.api.text_hash(raw),
            "translation_status": "pending",
            "chunks": [],
            "warnings": [],
        }
        with self.observer():
            mt.prepare_routing(self.api, {"translation_groups": [group]}, self.config)
            self.api.translate_segment(group, None, self.config)
            self.assertFalse(self.api.group_needs_review(group, {}))
        self.assertEqual(group["translation_status"], "not_required")
        self.assertIsNone(group["translation_ru"])
        self.assertEqual(group["raw_text"], raw)

    def test_unselected_channel_does_not_hide_selected_translation_or_asr_defects(self):
        group = {
            "language": "af",
            "speaker_id": "S1",
            "translation_ru": "Текст",
            "translation_status": "needs_review",
            "chunks": [],
            "warnings": [],
            "english": {"translation_status": "not_required"},
        }
        self.assertFalse(runtime.selected_channel_needs_review(group, {}, "ru"))
        group["warnings"].append("uncertain_language")
        self.assertTrue(runtime.selected_channel_needs_review(group, {}, "ru"))
        group["warnings"] = []
        group["translation_ru"] = None
        self.assertTrue(runtime.selected_channel_needs_review(group, {}, "ru"))


if __name__ == "__main__":
    unittest.main()
