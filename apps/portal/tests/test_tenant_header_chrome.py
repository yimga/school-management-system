"""Regression seal for the tenant header action cluster (2026-08-03).

The tenant header had lost its discrete, at-a-glance affordances: the
notification bell had been folded into the avatar-corner badge only (invisible
unless you knew to look at the avatar), and the Messages icon was suppressed on
copilot-rail pages by an incidental coupling. The global search, meanwhile,
greedily filled the whole actions track (``max-width: min(420px, 35vw)``),
crowding out room for icons.

These asserts lock the restored, RBAC/config-aware header:
  * a discrete Notifications bell linking the full inbox, gated by the
    ``SHOW_HEADER_NOTIFICATIONS`` config flag, whose badge reuses the live-poll
    hook (``data-rmc-unread-badge``) so it updates in place;
  * a Messages icon that is a universal destination and is NO LONGER hidden on
    copilot-rail pages;
  * a search that is capped/responsive, not greedy, in the *effective*
    (last-loaded) sheet — with the shadowed fallback kept in sync.

Pure file-structure asserts (``SimpleTestCase`` — no DB), mirroring the existing
``StudentPortalSidebarGateTests.test_template_gates_student_portal_nav`` pattern.
"""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class TenantHeaderChromeTests(SimpleTestCase):
    def setUp(self):
        self.header = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")

    def test_discrete_notifications_bell_present_and_config_gated(self):
        # A distinct bell icon (not just the avatar-corner badge) linking the inbox.
        self.assertIn('data-rmc-header-bell="1"', self.header)
        self.assertIn("accounts:user_notifications", self.header)
        self.assertIn("bi-bell-fill", self.header)
        # Config/page-aware: only when the platform enables header notifications.
        self.assertIn("{% if SHOW_HEADER_NOTIFICATIONS %}", self.header)
        # Its badge must reuse the live poller's hook so it stays fresh in place.
        self.assertIn("data-rmc-unread-badge", self.header)

    def test_messages_icon_present_and_not_copilot_rail_gated(self):
        self.assertIn("accounts:user_messages", self.header)
        self.assertIn("bi-chat-dots-fill", self.header)
        # The Messages icon must NOT be suppressed on copilot-rail pages anymore.
        # (The flag itself still has a legitimate, unrelated body-attribute use;
        # what must be gone is the `not <flag>` gate that hid the icon.)
        self.assertNotIn("not rmc_page_help_on_copilot_rail", self.header)

    def test_header_search_is_capped_not_greedy(self):
        # rmc-tenant-chrome-finish.css loads LAST on the tenant shell, so its rule
        # is the effective one — it must carry the narrowed cap, not the old greedy one.
        finish = (ROOT / "static/css/rmc-tenant-chrome-finish.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("clamp(180px, 22vw, 300px)", finish)
        self.assertNotIn("min(420px, 35vw)", finish)
        # The shadowed 100x fallback is kept in sync so it can't confuse a reader.
        hundred_x = (ROOT / "static/css/rmc-tenant-header-100x.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("clamp(180px, 22vw, 300px)", hundred_x)


class OperatorHeaderChromeTests(SimpleTestCase):
    """Parity seal for the operator/manager header (manager_operator_topbar.html).

    Unlike the tenant header, the operator header already had a narrow search
    (rmc-cp-header-200x.css caps `.rmc-platform-header__command` at 280px via an
    `!important` that wins the cascade) AND a bell — but that bell is the
    PLATFORM-INCIDENT bell (links the incident console; badge = incident count),
    not the operator's personal notification inbox, which was avatar-only (the
    same gap the tenant had). This locks the restored discrete PERSONAL bell
    without disturbing the incident bell. Messages is intentionally NOT added —
    it is not an operator destination (absent from the operator nav/dropdown).
    """

    def setUp(self):
        self.header = (
            ROOT / "templates/partials/manager_operator_topbar.html"
        ).read_text(encoding="utf-8")

    def test_personal_notifications_bell_present_and_config_gated(self):
        self.assertIn('data-rmc-header-bell="1"', self.header)
        self.assertIn("accounts:user_notifications", self.header)
        # FILLED bell = personal inbox, visually distinct from the incident bell.
        self.assertIn("bi-bell-fill", self.header)
        self.assertIn("{% if SHOW_HEADER_NOTIFICATIONS %}", self.header)
        # badge reuses the live poll hook so it stays fresh in place
        self.assertIn("data-rmc-unread-badge", self.header)

    def test_incident_bell_preserved_and_distinct(self):
        # The platform-incident bell (its own gate) must remain — operators keep
        # the at-a-glance ops signal alongside the new personal bell.
        self.assertIn("cockpit_shell.show.bell", self.header)

    def test_messages_icon_not_added_to_operator_header(self):
        # Messages is a tenant-communication destination, not an operator one; it
        # must NOT be bolted onto the operator header (RBAC-aware parity != copy).
        self.assertNotIn("accounts:user_messages", self.header)
