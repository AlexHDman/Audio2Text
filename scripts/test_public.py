"""Run the publishable synthetic Python suite; no inference or private fixtures."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "test_v155", "test_v155_final", "test_v155_review", "test_v155_ux",
    "test_v156", "test_v204", "test_cache_manager_v205", "test_backend_quality",
)


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    (ROOT / "tests/.runtime").mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
