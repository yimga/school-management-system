import subprocess
import sys
import unittest
from pathlib import Path


class PublicApiLintTests(unittest.TestCase):
    def _run_lint(self, script_name: str) -> subprocess.CompletedProcess[str]:
        root = Path(__file__).resolve().parent.parent.parent.parent
        script = root / "scripts" / script_name
        if not script.is_file():
            self.skipTest(f"{script_name} not found")
        return subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_csrf_exempt_usage_is_reviewed(self):
        result = self._run_lint("lint_csrf_exempt_usage.py")
        self.assertEqual(
            result.returncode,
            0,
            f"lint_csrf_exempt_usage failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_allow_any_usage_is_reviewed(self):
        result = self._run_lint("lint_allow_any_usage.py")
        self.assertEqual(
            result.returncode,
            0,
            f"lint_allow_any_usage failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
