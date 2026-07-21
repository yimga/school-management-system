"""PII redaction must not be skippable by caller metadata.

THE DEFECT THIS GUARDS
----------------------
``services/ai_helpers.py`` redacted a prompt only when::

    looks_like_pii(prompt, user_query) and md.get("content_sensitivity") != "low_pii_ok"

so a caller could opt out of redaction *precisely at the moment PII had been
detected*. The flag had exactly two users: ``apps/siteconfig/support_ai_triage``
and ``support_ai_reply`` -- the one surface whose prompt is a support-ticket
body, i.e. arbitrary free text a parent typed. That is where a child's name,
a medical disclosure or a safeguarding concern is most likely to appear, and it
was the one place redaction was turned off.

The deny-by-default external-tier guard limited the blast radius, but it was the
only thing standing between that text and a third-party model. Two independent
controls had to fail for a leak; one of them was wired backwards.

These tests assert the opt-out is gone and cannot come back. They are must-fire:
restore the ``!= "low_pii_ok"`` condition and they go red.
"""

from __future__ import annotations

import ast
import pathlib

from django.test import SimpleTestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_AI_HELPERS = _REPO_ROOT / "services" / "ai_helpers.py"
_TRIAGE = _REPO_ROOT / "apps" / "siteconfig" / "support_ai_triage.py"
_REPLY = _REPO_ROOT / "apps" / "siteconfig" / "support_ai_reply.py"


def _redaction_guard_conditions() -> list[ast.expr]:
    """Every ``if`` test in ai_helpers that gates a ``redact_pii`` call."""
    tree = ast.parse(_AI_HELPERS.read_text(encoding="utf-8"))
    guards: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        calls = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "redact_pii"
        ]
        if calls:
            guards.append(node.test)
    return guards


class RedactionHasNoOptOutTests(SimpleTestCase):
    def test_redaction_guards_exist_at_all(self):
        """If the guards vanish, every other assertion here passes vacuously."""
        guards = _redaction_guard_conditions()
        self.assertGreaterEqual(
            len(guards),
            2,
            "Expected redaction on both the streaming and non-streaming paths.",
        )

    def test_no_redaction_guard_consults_caller_metadata(self):
        """A redaction guard may test for PII. It may not test caller intent.

        Anything reading ``md``/``metadata`` inside the condition is an opt-out
        by another name -- rename ``low_pii_ok`` to anything else and this still
        fails, which is the point.
        """
        for guard in _redaction_guard_conditions():
            names = {
                n.id for n in ast.walk(guard) if isinstance(n, ast.Name)
            }
            offending = names & {"md", "metadata", "meta"}
            self.assertEqual(
                offending,
                set(),
                "A redact_pii guard reads caller-supplied metadata "
                f"({sorted(offending)}). Redaction must depend only on whether "
                "PII is present, never on what the caller asserts about it.",
            )

    def test_low_pii_ok_is_not_load_bearing_anywhere(self):
        """The literal may survive in prose, but not in executable code."""
        tree = ast.parse(_AI_HELPERS.read_text(encoding="utf-8"))
        literals = [
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and n.value == "low_pii_ok"
        ]
        self.assertEqual(
            literals,
            [],
            'The string "low_pii_ok" is still evaluated in services/ai_helpers.py. '
            "It must not appear outside a comment.",
        )

    def test_support_ticket_surfaces_do_not_request_an_opt_out(self):
        for path in (_TRIAGE, _REPLY):
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                literals = [
                    n.value
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Constant)
                    and n.value in {"low_pii_ok", "content_sensitivity"}
                ]
                self.assertEqual(
                    literals,
                    [],
                    f"{path.name} still passes a content_sensitivity opt-out. "
                    "A support-ticket body is unbounded parent free text; it is "
                    "the last place redaction should be negotiable.",
                )
