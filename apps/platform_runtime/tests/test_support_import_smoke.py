"""Ensure platform_runtime test support modules stay importable (packaging / path regressions)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support import (
    load_repo_script,
    repo_root,
    write_repo_file,
)
from apps.platform_runtime.tests.support.paths import repo_root as repo_root_direct
from apps.platform_runtime.tests.support.script_loading import load_repo_script as lrs


class PlatformRuntimeTestSupportImportSmokeTests(SimpleTestCase):
    def test_repo_root_is_inside_workspace(self):
        root = repo_root()
        self.assertTrue((root / "manage.py").is_file() or (root / "apps").is_dir())

    def test_repo_root_matches_direct_import(self):
        self.assertEqual(repo_root(), repo_root_direct())

    def test_packaged_support_exports_match_script_loading(self):
        self.assertIs(lrs, load_repo_script)

    def test_write_repo_file_creates_nested_path(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_repo_file(base, "apps/demo/x.txt", "ok\n")
            self.assertEqual((base / "apps" / "demo" / "x.txt").read_text(encoding="utf-8"), "ok\n")
