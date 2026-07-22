"""Stdlib tests for verify_eager_filter_arg_completion (static rows)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_eager_filter_arg_completion.py"


def _load():
    name = "verify_eager_filter_arg_completion_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class VerifyEagerFilterArgCompletionStaticTests(unittest.TestCase):
    def test_static_only_rows_all_pass(self):
        mod = _load()
        rows = [
            mod.check_static_scanner(),
            mod.check_banned_patterns(),
            mod.check_scanner_unit_tests(),
            mod.check_wiring(),
            mod.check_prompt_present(),
            mod.check_ops_consumers_clean(),
        ]
        failed = [r for r in rows if not r.ok]
        self.assertEqual(
            failed,
            [],
            msg="; ".join(f"{r.check_id}:{r.proof}" for r in failed),
        )

    def test_prompt_file_exists(self):
        path = ROOT / "docs/prompts/EAGER_FILTER_ARG_COMPLETION_PROMPT.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("EAGER_FILTER_ARG_COMPLETION_PASS", text)
        self.assertIn("verify_eager_filter_arg_completion.py", text)


if __name__ == "__main__":
    unittest.main()
