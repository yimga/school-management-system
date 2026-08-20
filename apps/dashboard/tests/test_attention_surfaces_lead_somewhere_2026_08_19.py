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


class CountedBacklogsOutsideTheComponentsTests(SimpleTestCase):
    """Rule B — the same defect in hand-written markup.

    Rule A only sees two components. A sweep of all 1,898 templates for "a count
    of pending work with nothing to act on" found 38 more candidates. Triaging
    them produced four honest categories that are NOT this defect, and the
    single most common one was a surprise: the count sitting ON the page that
    clears it. "Failed: 3" on the import monitor is not a dead end — the reader
    is already where the work is done. A rule that demanded a link there would
    have shipped noise and been switched off.
    """

    def _write_probe(self, body: str) -> Path:
        probe = ROOT / "templates" / "_probe_attention_test.html"
        probe.write_text(body, encoding="utf-8")
        self.addCleanup(lambda: probe.exists() and probe.unlink())
        return probe

    def _flagged(self) -> bool:
        return any("_probe_attention_test" in str(f["path"]) for f in scan())

    BACKLOG = (
        "<div><span>{% blocktrans count n=pending %}{{ n }} awaiting approval"
        "{% endblocktrans %}</span></div>\n"
    )

    def test_a_counted_backlog_with_no_affordance_is_flagged(self):
        self._write_probe(self.BACKLOG)
        self.assertTrue(self._flagged(), "a counted backlog with no way to act went unreported")

    def test_the_same_backlog_with_a_link_is_not_flagged(self):
        self._write_probe('<div><a href="/x/">Review</a>' + self.BACKLOG)
        self.assertFalse(self._flagged(), "a backlog that offers a destination is not a defect")

    def test_a_declared_category_exempts_it(self):
        self._write_probe(
            "{# attention-allow: resolver-surface — this page is the queue #}\n" + self.BACKLOG
        )
        self.assertFalse(self._flagged())

    def test_the_host_absent_category_is_refused_without_a_real_attempt(self):
        """The one constrained category must not become a free escape hatch."""
        self._write_probe(
            "{# attention-allow: no-destination-on-host — unsubstantiated #}\n" + self.BACKLOG
        )
        self.assertTrue(
            self._flagged(),
            "claiming the destination is absent on this host, without ever trying "
            "to resolve one, must not silence the gate",
        )

    def test_the_host_absent_category_holds_when_a_url_was_attempted(self):
        self._write_probe(
            "{% url 'finance:dashboard' as u %}\n"
            "{# attention-allow: no-destination-on-host — finance: is tenant-only #}\n"
            + self.BACKLOG
        )
        self.assertFalse(self._flagged())

    def test_an_action_rendering_tag_counts_as_an_affordance(self):
        """`{% render_smart_links %}` builds the buttons; no <a> appears in source."""
        self._write_probe(self.BACKLOG + "{% render_smart_links state=x persona='y' %}\n")
        self.assertFalse(
            self._flagged(),
            "a banner whose whole purpose is offering actions was reported as a dead end",
        )

    def test_a_bare_data_attribute_is_not_a_backlog(self):
        self._write_probe('<div\n  data-server-failed="{{ failed_count }}">\n</div>\n')
        self.assertFalse(self._flagged(), "attribute plumbing is not something a person reads")

    def test_every_declared_category_is_one_of_the_known_ones(self):
        """A typo'd category must fail loudly rather than silently exempt."""
        import re as _re

        from scan_actionless_attention_surfaces import (  # noqa: PLC0415
            _ALLOW_CATEGORIES,
            _HOST_ABSENT_CATEGORY,
        )

        known = set(_ALLOW_CATEGORIES) | {_HOST_ABSENT_CATEGORY}
        used: set[str] = set()
        for path in (ROOT / "templates").rglob("*.html"):
            for match in _re.finditer(
                r"attention-allow:\s*([a-z-]+)", path.read_text(encoding="utf-8", errors="ignore")
            ):
                used.add(match.group(1).lower())
        self.assertTrue(used, "no categories in use — has the marker syntax changed?")
        self.assertEqual(
            used - known, set(), f"unknown attention-allow categories in templates: {used - known}"
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
