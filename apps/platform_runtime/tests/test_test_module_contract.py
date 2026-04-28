"""Test module map verifier writes contract JSON/MD."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class TestModuleContractScriptTests(SimpleTestCase):
    def test_script_ok_and_outputs_exist(self):
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_test_module_contract.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(r.returncode, 0, msg=(r.stderr or r.stdout)[:2000])
        js = REPO / "docs" / "generated" / "test_module_contract.json"
        self.assertTrue(js.is_file())
        data = json.loads(js.read_text(encoding="utf-8"))
        self.assertIn("ok", data)
