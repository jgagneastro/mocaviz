"""Run SPHEREx request/transaction tests while denying all filesystem mutations.

Usage: PYTHONDONTWRITEBYTECODE=1 python -B scripts/check_spherex_no_files.py
Imports happen before the guard, just as at worker startup. Request handling,
fitting, write-preview, simulated transactions and undo run under the guard.
No live MOCAdb credentials or database writes are used.
"""
import os
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import test_spherex_review

violations = []


def audit(event, args):
    mutation = event in {
        "os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.link", "os.symlink",
        "os.truncate", "tempfile.mkstemp", "tempfile.mkdtemp",
    }
    if event == "open":
        mode, flags = args[1:3]
        mutation = (
            isinstance(mode, str) and any(c in mode for c in "wax+")
            or isinstance(flags, int) and flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            )
        )
    if mutation:
        violations.append(event)
        raise AssertionError("Filesystem mutation during review request: " + event)


sys.addaudithook(audit)
result = unittest.TextTestRunner(verbosity=1).run(
    unittest.defaultTestLoader.loadTestsFromModule(test_spherex_review)
)
print("Filesystem mutation attempts:", len(violations))
raise SystemExit(0 if result.wasSuccessful() and not violations else 1)
