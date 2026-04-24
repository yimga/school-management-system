from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.repo_tree import write_repo_file
from apps.platform_runtime.tests.support.script_loading import load_repo_script


class LintGileadResidueScriptTests(SimpleTestCase):
    def _load_script_module(self):
        return load_repo_script(
            "scripts/lint_gilead_residue.py",
            "lint_gilead_residue_script_test_module",
        )

    def test_passes_when_gilead_only_in_skipped_docs(self):
        mod = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir(parents=True, exist_ok=True)
            write_repo_file(repo, "docs/legacy.md", "Gilead legacy doc ok\n")
            with patch.object(mod, "_tracked_file_relpaths", return_value=frozenset({"docs/legacy.md"})):
                rc = mod.main(["--base", str(repo)])
        self.assertEqual(rc, 0)

    def test_fails_when_gilead_in_runtime_template(self):
        mod = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir(parents=True, exist_ok=True)
            write_repo_file(repo, "templates/runtime.html", "Welcome to Gilead!\n")
            with patch.object(
                mod, "_tracked_file_relpaths", return_value=frozenset({"templates/runtime.html"})
            ):
                rc = mod.main(["--base", str(repo)])
        self.assertEqual(rc, 1)

    def test_falls_back_to_rglob_when_git_tracking_missing(self):
        mod = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            # no .git → _tracked_file_relpaths returns None, so rglob path is used
            write_repo_file(repo, "templates/runtime.html", "Welcome to Gilead!\n")
            rc = mod.main(["--base", str(repo)])
        self.assertEqual(rc, 1)
