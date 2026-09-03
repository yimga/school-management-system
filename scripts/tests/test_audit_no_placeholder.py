"""Both directions for audit_no_placeholder: what it must catch, what it must not,
and -- the half that made this gate necessary -- that it can FAIL at all.

Until 2026-09-02 ``main()`` ended in ``return 0`` unconditionally and nothing in
the repository invoked it, so its tracked artifact drifted for 3.5 months while
still reading ``"finding_count": 0``. The tests that matter most here are
therefore the ones that assert a non-zero exit, and the ones that assert an
allow-marker with no reason in it suppresses nothing.
"""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "audit_no_placeholder",
    Path(__file__).resolve().parents[1] / "audit_no_placeholder.py",
)
audit = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(audit)


def kinds(text: str) -> list[str]:
    findings, _ = audit.scan_text("t.html", text)
    return sorted(row["kind"] for row in findings)


def declared(text: str) -> list[dict]:
    _, declarations = audit.scan_text("t.html", text)
    return declarations


class WhatItMustCatchTests(unittest.TestCase):
    def test_bare_placeholder_copy(self):
        self.assertEqual(kinds("<span>Coming soon</span>"), ["coming-soon"])

    def test_lorem_ipsum(self):
        self.assertEqual(kinds("<p>Lorem ipsum dolor</p>"), ["lorem-ipsum"])

    def test_every_registered_pattern_fires_at_least_once(self):
        """A pattern nobody has ever seen fire is not evidence of anything."""
        samples = {
            "lorem-ipsum": "Lorem ipsum dolor",
            "coming-soon": "Coming soon",
            "not-implemented": "Not implemented",
            "replace-me": "Replace me",
            "placeholder-text": "Placeholder text",
            "sample-data": "Sample data",
            "fake-content": "Fake content",
            "under-construction": "Under construction",
            "work-in-progress": "Work in progress",
            "tbd": "TBD",
            "tba": "TBA",
        }
        registered = {kind for _, kind in audit.USER_VISIBLE_PATTERNS}
        self.assertEqual(set(samples), registered, "a pattern gained or lost a sample")
        for kind, sample in samples.items():
            self.assertIn(kind, kinds(f"<p>{sample}</p>"), sample)


class WhatItMustNotFlagTests(unittest.TestCase):
    def test_an_input_placeholder_attribute(self):
        """Documented since day one; not actually implemented until 2026-09-02.

        The stripped string was computed, used for the dev-note test and then
        discarded, so the patterns matched the raw line.
        """
        self.assertEqual(kinds('<input placeholder="Coming soon">'), [])

    def test_a_django_todo_note(self):
        self.assertEqual(kinds("{# TODO: wire this up #}"), [])

    def test_a_comment_block_todo(self):
        self.assertEqual(kinds("{% comment %}TODO: later{% endcomment %}"), [])


class DeclarationTests(unittest.TestCase):
    REASON = "plans are not productized yet and the lede says so"

    def test_marker_on_the_same_line_declares(self):
        text = f'<span>Coming soon</span>{{# placeholder-allow: {self.REASON} #}}'
        self.assertEqual(kinds(text), [])
        self.assertEqual(len(declared(text)), 1)

    def test_marker_on_the_line_above_declares(self):
        text = f"{{# placeholder-allow: {self.REASON} #}}\n<span>Coming soon</span>"
        self.assertEqual(kinds(text), [])
        self.assertEqual(declared(text)[0]["reason"], self.REASON)

    def test_html_comment_marker_declares(self):
        text = f"<!-- placeholder-allow: {self.REASON} -->\n<span>Coming soon</span>"
        self.assertEqual(kinds(text), [])
        self.assertEqual(len(declared(text)), 1)

    def test_an_empty_reason_declares_nothing(self):
        """The marker exists so the next reader learns WHY. Empty is a mute button."""
        text = "{# placeholder-allow: #}\n<span>Coming soon</span>"
        self.assertEqual(kinds(text), ["allow-marker-without-reason"])
        self.assertEqual(declared(text), [])

    def test_a_one_word_reason_declares_nothing(self):
        text = "{# placeholder-allow: later #}\n<span>Coming soon</span>"
        self.assertEqual(kinds(text), ["allow-marker-without-reason"])
        self.assertEqual(declared(text), [])

    def test_a_marker_two_lines_up_does_not_reach(self):
        text = f"{{# placeholder-allow: {self.REASON} #}}\n\n<span>Coming soon</span>"
        self.assertEqual(kinds(text), ["coming-soon", "stale-allow-marker"])

    def test_a_marker_that_governs_nothing_is_stale(self):
        """An excuse must not outlive the copy it was written for."""
        text = f"{{# placeholder-allow: {self.REASON} #}}\n<p>shipped copy</p>"
        self.assertEqual(kinds(text), ["stale-allow-marker"])

    def test_an_unclosed_marker_suppresses_nothing_and_is_reported(self):
        text = f"{{# placeholder-allow: {self.REASON}\n<span>Coming soon</span>"
        self.assertEqual(kinds(text), ["coming-soon", "malformed-allow-marker"])


class CorpusTests(unittest.TestCase):
    def test_the_corpus_includes_app_template_dirs(self):
        """settings.TEMPLATES has APP_DIRS: True; scanning templates/ alone is blind."""
        roots = [str(r) for r in audit.template_roots()]
        suffix = str(Path("apps") / "athletics" / "templates")
        self.assertTrue(any(r.endswith(suffix) for r in roots), roots)
        self.assertGreater(len(roots), 1, roots)

    def test_the_corpus_is_not_empty(self):
        """A zero over an empty corpus is not a zero."""
        self.assertGreater(len(audit.iter_templates()), 1000)


class TheGateItselfTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = audit.main(argv)
        return code, buffer.getvalue()

    def test_self_check_passes(self):
        code, _ = self._run(["--self-check"])
        self.assertEqual(code, 0)

    def test_the_real_tree_is_clean_under_strict(self):
        code, out = self._run(["--strict"])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_strict_writes_nothing(self):
        """The pre-push hook runs this on every push; it must not dirty the tree."""
        before = audit.OUT_PATH.read_bytes()
        self._run(["--strict"])
        self.assertEqual(audit.OUT_PATH.read_bytes(), before)

    def test_strict_fails_on_an_undeclared_finding(self):
        """The property the artifact claimed for 3.5 months while nothing checked it."""
        live = audit.run_scan()
        planted = {
            "file": "templates/_planted.html",
            "line": 1,
            "kind": "lorem-ipsum",
            "snippet": "<p>Lorem ipsum</p>",
        }
        with mock.patch.object(
            audit, "run_scan", return_value=(live[0], [planted], live[2])
        ):
            code, out = self._run(["--strict"])
        self.assertEqual(code, 1, out)
        self.assertIn("undeclared lorem-ipsum", out)

    def test_strict_fails_when_the_artifact_no_longer_matches_the_tree(self):
        """The actual 2026-09-02 defect: a certificate for a tree that moved on."""
        live = audit.run_scan()
        with mock.patch.object(
            audit, "run_scan", return_value=(live[0], live[1], [])
        ):
            code, out = self._run(["--strict"])
        self.assertEqual(code, 1, out)
        self.assertIn("still records a declaration that is gone", out)

    def test_strict_refuses_to_report_when_its_own_classifier_regresses(self):
        broken = tuple(list(audit.SELF_CHECK_CASES) + [("planted", "<p>Coming soon</p>", [], 0)])
        with mock.patch.object(audit, "SELF_CHECK_CASES", broken):
            code, out = self._run(["--strict"])
        self.assertEqual(code, 1, out)
        self.assertIn("self-check", out)

    def test_strict_fails_on_an_empty_corpus(self):
        with mock.patch.object(audit, "run_scan", return_value=(0, [], [])):
            code, out = self._run(["--strict"])
        self.assertEqual(code, 1, out)
        self.assertIn("EMPTY", out)

    def test_the_committed_artifact_matches_the_live_scan(self):
        count, findings, declarations = audit.run_scan()
        live = audit.signature(audit.build_payload(count, findings, declarations))
        stored = audit.signature(json.loads(audit.OUT_PATH.read_text(encoding="utf-8")))
        self.assertEqual(live, stored)


if __name__ == "__main__":
    unittest.main()
