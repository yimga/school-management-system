"""An attention surface that reports work must say where the work is handled.

A tenant admin's dashboard rendered:

    (!) What needs you
        6 access requests awaiting approval

with no link and no button. The count was right, the screen that resolves it
existed (``requests:dashboard``), and the row component had accepted
``dh_go_href`` since it was written — the invoice row two lines above rendered a
working "Chase" link off exactly that parameter. The approvals row just omitted
it, so the reader had to go hunting for a page the platform could have named.

Four such rows existed across the tenant and role dashboards. These tests pin
the rule that closes the class, and the two failure modes that make it subtle.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
SCANNER = ROOT / "scripts" / "scan_actionless_attention_surfaces.py"

sys.path.insert(0, str(ROOT / "scripts"))
from scan_actionless_attention_surfaces import (  # noqa: E402
    ATTENTION_COMPONENTS,
    EXEMPTION_PARAM,
    scan,
)


class NoAttentionRowIsADeadEndTests(SimpleTestCase):
    def test_the_platform_has_no_actionless_attention_rows(self):
        findings = scan()
        self.assertEqual(
            findings,
            [],
            "an attention row reports a backlog with no way to act on it:\n"
            + "\n".join(f"  {f['path']}:{f['line']} missing {f['missing']}" for f in findings),
        )

    def test_the_gate_actually_fails_when_a_dead_end_exists(self):
        """A gate that cannot go red proves nothing."""
        result = subprocess.run(
            [sys.executable, str(SCANNER), "--json"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, "scanner reports findings on a clean tree")
        self.assertIn("[]", result.stdout, "expected an empty JSON finding list")

    def test_the_photographed_row_now_names_its_destination(self):
        source = (ROOT / "templates" / "accounts" / "_rmc_dh_admin_overview.html").read_text(
            encoding="utf-8"
        )
        row = next(
            line for line in source.splitlines() if "access request awaiting approval" in line
        )
        self.assertIn(
            "dh_go_href",
            row,
            "the access-requests row still reports a count with nowhere to go",
        )
        self.assertIn(
            "ov_requests_url",
            row,
            "the row must point at the page that resolves access requests",
        )
        self.assertRegex(
            source,
            r"\{%\s*url\s+'requests:dashboard'\s+as\s+ov_requests_url\s*%\}",
            "ov_requests_url is used but never resolved, so the href renders empty",
        )

    def test_a_cleared_row_may_opt_out_but_must_say_so(self):
        """'Queue clear' has nowhere to go — that is correct, and must be stated."""
        source = (ROOT / "templates" / "student" / "_rmc_dh_student_home.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            EXEMPTION_PARAM,
            source,
            "the no-work branch must declare its exemption in the template, not "
            "be suppressed in a scanner baseline where no reviewer sees it",
        )

    def test_the_exemption_is_not_a_blanket_escape(self):
        """If every row could opt out silently the gate would be decorative."""
        for component in ATTENTION_COMPONENTS:
            body = (ROOT / "templates" / component).read_text(encoding="utf-8")
            self.assertIn(
                "href",
                body,
                f"{component} no longer renders a destination at all",
            )


class DestinationsActuallyResolveTests(SimpleTestCase):
    """``{% url 'x' as y %}`` does NOT raise when the name is wrong — it sets "".

    So a typo in a destination produces ``href=""``: a link that is present,
    focusable, and goes nowhere. That is a dead end the include-level gate
    cannot see, because the parameter IS passed. These names must therefore be
    reversed for real, on both the tenant and the operator URLconf.
    """

    NAMES = (
        "requests:dashboard",
        "analytics:at_risk_dashboard",
        "finance:dashboard",
        "evals:teacher_marks_entry",
    )

    def test_every_attention_destination_reverses_on_both_hosts(self):
        from django.test import override_settings
        from django.urls import clear_url_caches, reverse

        for urlconf in ("config.tenant_urls", "config.urls"):
            with override_settings(ROOT_URLCONF=urlconf):
                clear_url_caches()
                for name in self.NAMES:
                    with self.subTest(urlconf=urlconf, name=name):
                        path = reverse(name)
                        self.assertTrue(
                            path.startswith("/"),
                            f"{name} did not reverse to a path on {urlconf}",
                        )


class ClearedRowsAreDistinguishableFromBrokenOnesTests(SimpleTestCase):
    """The nastier half of the defect: an alert that looks like reassurance.

    ``urgent_queue`` rows carried only ``url``, and consumers treated a missing
    url as the "nothing to do" variant — a check-circle and calm copy. So a REAL
    alert whose producer forgot a url was rendered as though everything were
    fine. For an attention surface that is the worst possible failure: silence
    where there should be a warning.
    """

    def test_cleared_rows_are_flagged_explicitly(self):
        source = (ROOT / "apps" / "dashboard" / "decision_surface_context.py").read_text(
            encoding="utf-8"
        )
        blocks = re.findall(r"urgent\.append\(\s*\{.*?\}\s*\)", source, re.S)
        self.assertTrue(blocks, "no urgent-queue rows found — has the builder moved?")
        for block in blocks:
            self.assertIn(
                "cleared",
                block,
                "an urgent-queue row does not state whether it is real work or an "
                "empty-queue reassurance, so a consumer must guess from the url",
            )

    def test_an_actionable_row_never_ships_without_a_destination(self):
        source = (ROOT / "apps" / "dashboard" / "decision_surface_context.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "fallback_url",
            source,
            "a priority-queue item whose producer omits a url still becomes a dead "
            "end at runtime; it must fall back to the role's own home",
        )

    def test_only_the_empty_queue_rows_are_marked_cleared(self):
        source = (ROOT / "apps" / "dashboard" / "decision_surface_context.py").read_text(
            encoding="utf-8"
        )
        cleared_true = source.count('"cleared": True')
        cleared_false = source.count('"cleared": False')
        self.assertEqual(
            cleared_true,
            2,
            "expected exactly the two empty-queue reassurance rows to be cleared",
        )
        self.assertGreaterEqual(
            cleared_false, 2, "real work rows must be explicitly not-cleared"
        )
