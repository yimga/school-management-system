"""World Engine §11 i18n CI verifier smoke."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class WorldEngineI18nCiVerifierTests(SimpleTestCase):
    def test_world_engine_i18n_ci_passes_on_repo_tree(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_world_engine_i18n_ci.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=(proc.stdout or "") + (proc.stderr or ""),
        )
        self.assertIn("WORLD_ENGINE_I18N_CI_PASS", proc.stdout)
