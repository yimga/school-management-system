"""Stdlib tests for verify_critical_msgid_depth."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "verify_critical_msgid_depth.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_critical_msgid_depth", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class CriticalMsgidDepthTests(unittest.TestCase):
    def test_live_tree_passes(self):
        mod = _load()
        # Avoid unittest's argv (-v) confusing argparse.
        old = sys.argv
        try:
            sys.argv = [str(MOD_PATH)]
            self.assertEqual(mod.main(), 0)
        finally:
            sys.argv = old

    def test_parse_po_unescapes_quotes(self):
        mod = _load()
        text = 'msgid "He said \\"hi\\""\nmsgstr "Il a dit \\"salut\\""\n'
        entries = mod._parse_po_entries(text)
        self.assertEqual(entries.get('He said "hi"'), 'Il a dit "salut"')


if __name__ == "__main__":
    unittest.main()
