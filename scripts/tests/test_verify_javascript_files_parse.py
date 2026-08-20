"""Tests for the JavaScript floor gate — the sibling the Python one asked for.

``verify_python_files_parse.py`` was written on 2026-08-19 after a truncated module
reached ``main``; its own report named the remaining hole and stopped there — nothing
checked that JavaScript parses. That gap is worse than it sounds, because the two fail
differently: a Python module that does not compile fails loudly at import, while a
JavaScript file that does not parse fails SILENTLY in the browser. The script tag 200s,
the engine throws into a console nobody is watching, and the page renders looking normal
with one feature dead.

The live-tree test at the bottom doubles as calibration — if this gate ever reports a
finding on a clean checkout, it is the gate that is wrong, not the tree.
"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_javascript_files_parse as gate  # noqa: E402


_HAS_NODE = shutil.which("node") is not None


@unittest.skipUnless(_HAS_NODE, "node is required to parse JavaScript")
class _TempTree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._real_root = gate.REPO_ROOT
        gate.REPO_ROOT = self.root
        (self.root / "static" / "js").mkdir(parents=True)

    def tearDown(self):
        gate.REPO_ROOT = self._real_root
        self._tmp.cleanup()

    def _write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with io.open(path, "w", encoding="utf8", newline="\n") as fh:
            fh.write(text)
        return path


class JavaScriptParseGateTests(_TempTree):
    def test_a_clean_file_is_not_a_finding(self):
        self._write("static/js/ok.js", "function f() { return 1; }\n")
        checked, findings = gate.scan(("static/js",))
        self.assertEqual(checked, 1)
        self.assertEqual(findings, [])

    def test_a_syntax_error_is_caught(self):
        self._write("static/js/bad.js", "function broken( {\n  return 1;\n")
        _checked, findings = gate.scan(("static/js",))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0][0], "static/js/bad.js")

    def test_an_es_module_is_not_a_false_positive(self):
        """`import`/`export` at top level is a SyntaxError for a classic script. Reporting
        those would make the gate unusable on a tree that ships both module systems — and
        a gate that cries wolf gets switched off."""
        self._write(
            "static/js/mod.js",
            "export const x = 1;\nexport default function () { return x; }\n",
        )
        _checked, findings = gate.scan(("static/js",))
        self.assertEqual(findings, [])

    def test_modern_syntax_is_accepted(self):
        """Optional chaining, nullish coalescing, async/await, class fields — the gate
        must not quietly ban the language the codebase already uses."""
        self._write(
            "static/js/modern.js",
            "class A { #p = 1; static s = 2; }\n"
            "const v = a?.b ?? c;\n"
            "async function go() { for await (const x of y) {} }\n",
        )
        _checked, findings = gate.scan(("static/js",))
        self.assertEqual(findings, [])

    def test_vendor_and_minified_drops_are_skipped(self):
        """A minified third-party bundle we did not write is a packaging problem, not a
        source defect, and flagging it teaches people to ignore the gate."""
        self._write("static/js/thing.min.js", "this is ( not javascript")
        self._write("static/js/vendor/lib.js", "also ( not javascript")
        self._write("static/js/node_modules/dep.js", "nope (")
        checked, findings = gate.scan(("static/js",))
        self.assertEqual((checked, findings), (0, []))

    def test_a_missing_root_is_not_an_error(self):
        self.assertEqual(gate.scan(("does_not_exist",)), (0, []))

    def test_main_exits_nonzero_on_a_finding(self):
        self._write("static/js/bad.js", "function broken( {\n")
        self.assertEqual(gate.main(["--roots", "static/js"]), 1)

    def test_main_exits_zero_when_clean(self):
        self._write("static/js/ok.js", "var x = 1;\n")
        self.assertEqual(gate.main(["--roots", "static/js"]), 0)


@unittest.skipUnless(_HAS_NODE, "node is required to parse JavaScript")
class LiveTreeTests(unittest.TestCase):
    def test_the_shipped_javascript_parses(self):
        """Calibration: a clean checkout must be clean."""
        checked, findings = gate.scan()
        self.assertGreater(checked, 100, "the gate is not finding the shipped JavaScript")
        self.assertEqual(
            findings,
            [],
            "files that do not parse:\n  "
            + "\n  ".join(f"{r}:{n}: {m}" for r, n, m in findings),
        )

    def test_the_service_worker_is_covered(self):
        """The single highest-cost file to break: a SyntaxError there kills registration,
        so the offline shell an appliance depends on silently stops updating."""
        files = [p.as_posix() for p in gate._iter_js_files(gate.SCAN_ROOTS)]
        self.assertTrue(
            any(f.endswith("static/js/service-worker.js") for f in files),
            "the service worker is not inside the gate's scan roots",
        )


if __name__ == "__main__":
    unittest.main()
