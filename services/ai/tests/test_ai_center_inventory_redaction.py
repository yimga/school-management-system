"""AI Center inventory must stay metadata-only (no secret leakage)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class AICenterInventoryRedactionTests(SimpleTestCase):
    def test_generate_inventory_redacts_secret_keys(self):
        proc = subprocess.run(
            [sys.executable, "scripts/generate_ai_center_inventory.py", "--write"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=proc.stderr or proc.stdout,
        )
        data = json.loads(
            (ROOT / "docs/generated/ai_center_platform_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(data.get("metadata_only"))
        self.assertTrue(data.get("pii_free"))
        self.assertTrue(data.get("secrets_redacted"))
        self.assertGreater(data.get("app_count", 0), 0)
        check = subprocess.run(
            [sys.executable, "scripts/generate_ai_center_inventory.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(check.returncode, 0, msg=check.stderr or check.stdout)
