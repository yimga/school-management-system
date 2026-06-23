"""Page-aware tenant "Your flow": ``apply_page_awareness`` contract.

Pins that the tenant action list reorders by relevance to the CURRENT page and
never re-offers the page the user is already on — while genuinely urgent
(high base-priority) actions still lead. Pure: no DB, no URLconf.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.action_engine import (
    SystemAction,
    _current_path,
    _page_segments,
    apply_page_awareness,
)


def _a(title, url, priority=40, *, type="navigation", source="role_default", audience="all"):
    return SystemAction(
        type=type,
        title=title,
        description=title,
        action_url=url,
        priority=priority,
        audience=audience,
        source=source,
    )


class PageSegmentTests(SimpleTestCase):
    def test_segments_strip_query_hash_and_blanks(self):
        self.assertEqual(
            _page_segments("/portal/teacher/attendance/?x=1#top"),
            ["portal", "teacher", "attendance"],
        )
        self.assertEqual(_page_segments(""), [])
        self.assertEqual(_page_segments(None), [])

    def test_current_path_handles_missing_request_and_strips_query(self):
        self.assertEqual(_current_path(None), "")

        class NoPath:
            pass

        self.assertEqual(_current_path(NoPath()), "")

        class WithPath:
            path = "/finance/invoices/?p=2"

        self.assertEqual(_current_path(WithPath()), "/finance/invoices/")


class AffinityOrderingTests(SimpleTestCase):
    def test_same_section_action_outranks_off_section_equal_priority(self):
        fin = _a("Finance pulse", "/finance/dashboard/", priority=40)
        other = _a("Help center", "/feedback/help/", priority=40)
        out = apply_page_awareness([other, fin], "/finance/invoices/", single=False)
        self.assertEqual([x.title for x in out], ["Finance pulse", "Help center"])

    def test_reorders_differently_per_page(self):
        fin = _a("Finance pulse", "/finance/dashboard/", priority=40)
        rep = _a("Reports", "/analytics/dashboard/", priority=40)
        on_finance = apply_page_awareness([rep, fin], "/finance/x/", single=False)
        on_reports = apply_page_awareness([rep, fin], "/analytics/y/", single=False)
        self.assertEqual(on_finance[0].title, "Finance pulse")
        self.assertEqual(on_reports[0].title, "Reports")
        self.assertNotEqual(
            [a.title for a in on_finance], [a.title for a in on_reports]
        )

    def test_deeper_shared_path_wins_over_shallower(self):
        deep = _a("Marks", "/portal/teacher/marks/", priority=40)
        shallow = _a("Portal home", "/portal/home/", priority=40)
        out = apply_page_awareness(
            [shallow, deep], "/portal/teacher/classes/", single=False
        )
        self.assertEqual(out[0].title, "Marks")

    def test_boost_is_bounded_and_never_beats_urgent_state(self):
        # A high-priority onboarding step must still lead even when an off-section
        # role default sits on its own section page (affinity is bounded).
        onboarding = _a(
            "Finish activation",
            "/setup/activate/",
            priority=95,
            type="onboarding",
            source="onboarding_steps",
        )
        role = _a("Finance pulse", "/finance/dashboard/", priority=40)
        out = apply_page_awareness([role, onboarding], "/finance/x/", single=False)
        self.assertEqual(out[0].title, "Finish activation")


class ExcludeCurrentPageTests(SimpleTestCase):
    def test_drops_the_page_you_are_on(self):
        here = _a("Family home", "/portal/parent/", priority=35)
        fees = _a("Fees", "/portal/parent/finance/", priority=32)
        out = apply_page_awareness([here, fees], "/portal/parent/", single=False)
        titles = [a.title for a in out]
        self.assertNotIn("Family home", titles)
        self.assertIn("Fees", titles)

    def test_exclude_only_exact_page_not_section_siblings(self):
        # Same section but a different page must survive — only the EXACT current
        # page is dropped.
        sibling = _a("Invoices", "/finance/invoices/", priority=30)
        out = apply_page_awareness([sibling], "/finance/dashboard/", single=False)
        self.assertEqual([a.title for a in out], ["Invoices"])

    def test_exclude_current_false_keeps_everything(self):
        here = _a("Family home", "/portal/parent/", priority=35)
        out = apply_page_awareness(
            [here], "/portal/parent/", single=False, exclude_current=False
        )
        self.assertEqual([a.title for a in out], ["Family home"])

    def test_no_path_is_a_noop_priority_sort(self):
        high = _a("High", "/a/", priority=90)
        low = _a("Low", "/b/", priority=10)
        out = apply_page_awareness([low, high], "", single=False)
        self.assertEqual([a.title for a in out], ["High", "Low"])


class SingleActionTierTests(SimpleTestCase):
    def test_single_mode_keeps_conversion_tier_primary(self):
        # onboarding tier (0) must precede a higher-priority + page-affine action.
        onboarding = _a(
            "Step",
            "/x/",
            priority=10,
            type="onboarding",
            source="onboarding_steps",
        )
        revenue = _a("Pay", "/finance/pay/", priority=88, type="payments", source="finance")
        out = apply_page_awareness(
            [revenue, onboarding], "/finance/dashboard/", single=True
        )
        self.assertEqual(out[0].title, "Step")
