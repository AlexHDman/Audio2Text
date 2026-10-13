"""Cache cleanup tests use ONLY disposable synthetic roots, never real jobs."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audio_pipeline_cuda_v156 as engine
import cache_manager_v205 as cm
from test_v155 import cache


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent / ".runtime")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = cache()
        self.data["pipeline_version"] = engine.VERSION
        self.data["source"]["path"] = str(self.root / "input" / "synthetic.wav")
        self.data["translation_groups"] = engine.build_translation_groups(self.data["segments"])
        self.data["export"] = {"status": "complete", "at": "2026-10-13T00:00:00+00:00"}
        self.data["updated_at"] = "2026-10-13T00:00:00+00:00"
        self.folder = self.write_job()
        for protected in ["input", "output", "assets", "frontend", "_internal/models",
                          "_internal/runtime", "_internal/ffmpeg", "venv", "cache/system", "logs"]:
            folder = self.root / protected
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "sentinel").write_text("KEEP", encoding="utf-8")

    def write_job(self, namespace="temp/v157", suffix=""):
        data = self.data
        data["state_sha256"] = engine.digest({k: v for k, v in data.items() if k != "state_sha256"})
        folder = self.root / namespace / (data["source"]["sha256"][:20] + "-" + data["processing_fingerprint"][:20] + suffix)
        folder.mkdir(parents=True, exist_ok=True)
        engine.atomic_write_json(folder / "resume.json", data)
        (folder / "prepared.wav").write_bytes(b"synthetic-audio")
        return folder

    def request(self, allow=False):
        return {"confirmation": "delete_selected",
                "resume_confirmation": "lose_resume" if allow else "",
                "projects": cm.discover(self.root)["projects"]}

    def test_completed_deletion_preserves_all_protected_roots(self):
        result = cm.delete_selected(self.root, self.request())
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["deleted"]), 1)
        self.assertFalse(self.folder.exists())
        self.assertEqual(len(list(self.root.rglob("sentinel"))), 10)
        self.assertTrue(all(p.read_text() == "KEEP" for p in self.root.rglob("sentinel")))

    def test_incomplete_requires_extra_confirmation(self):
        self.data["export"] = {}
        self.write_job()
        with self.assertRaisesRegex(ValueError, "resume_loss"):
            cm.delete_selected(self.root, self.request())
        self.assertTrue(self.folder.exists())
        self.assertFalse(cm.delete_selected(self.root, self.request(True))["errors"])

    def test_active_and_stale_lock_are_protected(self):
        (self.folder / "run.lock").write_text('{"pid":0}')
        self.assertEqual(self.request()["projects"][0]["status"], "ACTIVE")
        with self.assertRaisesRegex(ValueError, "active"):
            cm.delete_selected(self.root, self.request())

    def test_new_lock_after_discovery_is_protected(self):
        request = self.request()
        (self.folder / "run.lock").write_text("{}")
        with self.assertRaises(ValueError):
            cm.delete_selected(self.root, request)
        self.assertTrue((self.folder / "resume.json").exists())

    def test_changed_snapshot_refused(self):
        request = self.request()
        self.data["updated_at"] = "changed"
        self.data["export"]["at"] = "changed"
        self.write_job()
        with self.assertRaisesRegex(ValueError, "changed"):
            cm.delete_selected(self.root, request)

    def test_legacy_unknown_and_extra_files_are_never_removed(self):
        (self.folder / "unrelated.txt").write_text("KEEP")
        catalog = cm.discover(self.root)
        self.assertFalse(catalog["projects"])
        self.assertEqual(len(catalog["unknown"]), 1)

    def test_corrupt_checksum_is_unknown(self):
        d = copy.deepcopy(self.data)
        d["duration"] = 99
        (self.folder / "resume.json").write_text(json.dumps(d))
        self.assertFalse(cm.discover(self.root)["projects"])

    def test_forged_directory_ownership_is_unknown(self):
        self.folder.rename(self.folder.with_name("b" * 20 + "-" + "c" * 20))
        self.assertFalse(cm.discover(self.root)["projects"])

    def test_paths_fail_closed(self):
        for target in ["../output", str(self.folder), "output/" + self.folder.name,
                       "cache/system/" + self.folder.name, "temp/v157/runtime"]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                cm.safe_job(self.root, target)

    def test_future_root_and_multiple_variants_form_one_project(self):
        self.write_job("cache/jobs")
        project = cm.discover(self.root)["projects"][0]
        self.assertEqual(project["filename"], "synthetic.wav")
        self.assertEqual(len(project["variants"]), 2)
        self.assertEqual(project["bytes"], sum(v["bytes"] for v in project["variants"]))
        self.assertEqual(len(cm.discover(self.root)["projects"]), 1)

    def test_missing_variant_in_request_is_refused(self):
        self.write_job("cache/jobs")
        request = self.request()
        request["projects"][0]["variants"].pop()
        with self.assertRaises(ValueError):
            cm.delete_selected(self.root, request)

    def test_missing_confirmation_refused(self):
        with self.assertRaises(ValueError):
            cm.delete_selected(self.root, {"projects": self.request()["projects"]})

    def test_reparse_attribute_refused(self):
        info = type("Info", (), {"st_mode": 0, "st_file_attributes": 0x400})()
        with patch.object(Path, "lstat", return_value=info), self.assertRaises(ValueError):
            cm.checked(self.folder)

    def test_hardlink_content_refused(self):
        original = self.root / "input" / "sentinel"
        (self.folder / "prepared.wav").unlink()
        os.link(original, self.folder / "prepared.wav")
        self.assertFalse(cm.discover(self.root)["projects"])
        self.assertEqual(original.read_text(), "KEEP")

    def test_pin_prevents_directory_rename(self):
        with cm.pin_directory(self.folder), self.assertRaises(OSError):
            self.folder.rename(self.folder.with_name("moved"))
        self.assertTrue(self.folder.exists())

    def test_stale_export_is_incomplete(self):
        self.data["updated_at"] = "2026-10-14T00:00:00+00:00"
        self.write_job()
        self.assertEqual(self.request()["projects"][0]["status"], "INCOMPLETE")

    def test_resume_requires_matching_prepared_checksum(self):
        self.data["prepared_sha256"] = "0" * 64
        self.write_job()
        self.assertFalse(self.request()["projects"][0]["resume"])
