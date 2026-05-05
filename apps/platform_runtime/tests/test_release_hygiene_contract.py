from __future__ import annotations

import subprocess
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[3]


class ReleaseHygieneContractTests(SimpleTestCase):
    def test_clean_archive_guide_and_export_ignores_exist(self):
        guide = (ROOT / "docs" / "RELEASE_CLEAN_ARCHIVE.md").read_text(
            encoding="utf-8"
        )
        attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("git archive", guide)
        self.assertIn("artifacts/db_snapshots/ export-ignore", attrs)
        self.assertIn("tmp/screenshots/ export-ignore", attrs)
        self.assertIn("*.sqlite3 export-ignore", attrs)
        self.assertIn("/artifacts/db_snapshots/", ignore)
        self.assertIn("/tmp/screenshots/", ignore)

    def test_no_tracked_release_junk_remains(self):
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        forbidden = []
        for path in proc.stdout.splitlines():
            if (
                path.endswith(".sqlite3")
                or path.endswith(".sqlite3-journal")
                or path.endswith(".log")
                or "/__pycache__/" in path
                or path.startswith(".django_test_dbs/")
                or path.startswith("tmp/screenshots/")
                or path.startswith("artifacts/db_snapshots/")
            ):
                forbidden.append(path)
        self.assertEqual(forbidden, [])
