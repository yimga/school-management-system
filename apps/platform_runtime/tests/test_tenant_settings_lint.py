"""
CI gate: no SiteSettings.get_solo() in tenant-facing code.
Runs scripts/lint_tenant_settings.py --check-get-solo-only and fails if any hits.
Uses unittest so it can run without Django (e.g. pytest from repo root).
"""
import subprocess
import sys
import unittest
from pathlib import Path


class TenantSettingsLintTests(unittest.TestCase):
    """Enforce tenant code uses runtime/helpers instead of SiteSettings.get_solo()."""

    def test_no_get_solo_in_tenant_apps(self):
        """Lint must report zero get_solo() hits in tenant apps (CI blocks new violations)."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        script = root / "scripts" / "lint_tenant_settings.py"
        if not script.is_file():
            self.skipTest("scripts/lint_tenant_settings.py not found")
        result = subprocess.run(
            [sys.executable, str(script), "--check-get-solo-only", "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"lint_tenant_settings (get_solo only) failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
