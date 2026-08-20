"""Every chip in the always-on action strip must lead somewhere on THIS host.

R5 of the dead-end spec. The Action Hub is included from ``portal_base.html``,
so it renders on every portal page for every persona. Six of the ten chips that
actually rendered returned 404 on a real tenant host, and the entire student
strip was dead.

The mechanism is worth keeping in mind, because it will recur anywhere a path
is written as a literal:

  * ``UrlConfSwitcherMiddleware`` hands a local/dev host ``config.urls``, which
    mounts the full URL surface. A school on a subdomain gets
    ``config.tenant_urls``, which does not. ``/parent/finance/`` resolves on
    the first and 404s on the second, so the defect is invisible in dev.
  * A literal ``href`` never raises. ``reverse()`` on a moved route does.

So these tests run under ``config.tenant_urls`` — the urlconf a paying school
is actually on — and click every chip the kernel can emit.

Two further silent failures are pinned here, because both deleted alerts
without a trace rather than showing a broken one:

  * ``_resolve_hub_href`` called ``get_smart_links(token)`` with no persona.
    The registry is keyed by ``(state, persona)`` and the default persona's
    fallback is a no-op, so every ``state_token`` chip — safeguarding,
    admissions, overdue balance, transcript hold, i.e. the danger-severity
    ones — resolved to nothing and was dropped.
  * ``non_empty_actions`` dropped every chip with ``count == 0`` that was not
    severity ``info``, which is exactly the shape of a boolean-state alert.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase, override_settings
from django.urls import Resolver404, resolve

from apps.platform_runtime.action_hub_kernel import (
    build_parent_hub,
    build_student_hub,
    build_teacher_hub,
    build_tenant_admin_hub,
    resolve_hub_for_audience,
)
from apps.platform_runtime.click_budget import clicks_saved_for_path
from apps.platform_runtime.templatetags.zero_click_tags import render_action_hub

TENANT_URLCONF = "config.tenant_urls"
_CHIP = re.compile(
    r'class="rmc-action-hub__chip" href="([^"]+)"'
    r' data-rmc-severity="[^"]*" data-rmc-clicks-saved="(\d+)"'
)

# Every builder driven with counts on, so no chip hides behind a false branch.
LOADED = {
    "tenant_admin": lambda: build_tenant_admin_hub(
        pending_admissions=3,
        open_safeguarding=2,
        urgent_dsl_inbox=1,
        overdue_invoices=12,
        storage_warning=True,
    ),
    "teacher": lambda: build_teacher_hub(
        classes_today=4,
        attendance_pending_classes=2,
        overdue_homework_review=7,
        pending_messages=3,
    ),
    "teacher_all_clear": lambda: build_teacher_hub(
        classes_today=4, attendance_pending_classes=0
    ),
    "parent": lambda: build_parent_hub(
        outstanding_balance_currency="N",
        outstanding_balance_amount="42000",
        unread_messages=2,
        upcoming_events=1,
        records_hold_active=True,
    ),
    "student": lambda: build_student_hub(
        homework_due_count=5, upcoming_exams=2, unread_messages=1
    ),
}
BASELINE_AUDIENCES = ("tenant_admin", "teacher", "parent", "student")


def _chips(hub):
    return _CHIP.findall(str(render_action_hub(hub)))


@override_settings(ROOT_URLCONF=TENANT_URLCONF)
class EveryRenderedChipResolvesOnTheTenantHostTests(SimpleTestCase):
    def test_the_always_on_strip_has_no_dead_chips(self):
        """No counts anywhere: this is what every portal page renders today."""
        dead = []
        for audience in BASELINE_AUDIENCES:
            for href, _saved in _chips(resolve_hub_for_audience(audience)):
                try:
                    resolve(href.split("?")[0], urlconf=TENANT_URLCONF)
                except Resolver404:
                    dead.append(f"{audience}: {href}")
        self.assertEqual(dead, [], "action-hub chips that 404 on a tenant host")

    def test_no_chip_leads_nowhere_once_counts_arrive(self):
        dead = []
        for name, build in LOADED.items():
            for href, _saved in _chips(build()):
                try:
                    resolve(href.split("?")[0], urlconf=TENANT_URLCONF)
                except Resolver404:
                    dead.append(f"{name}: {href}")
        self.assertEqual(dead, [], "action-hub chips that 404 on a tenant host")

    def test_the_student_strip_is_not_empty(self):
        """Both student chips 404'd, so a student's strip was entirely dead."""
        self.assertTrue(
            _chips(resolve_hub_for_audience("student")),
            "the student action strip renders no reachable chip at all",
        )

    def test_no_chip_is_silently_dropped(self):
        """A dropped chip is invisible: the state exists, the affordance doesn't."""
        for name, build in LOADED.items():
            hub = build()
            with self.subTest(persona=name):
                self.assertEqual(
                    len(_chips(hub)),
                    len(hub.non_empty_actions),
                    f"{name}: a chip resolved to nothing and vanished from the strip",
                )


@override_settings(ROOT_URLCONF=TENANT_URLCONF)
class DestinationsAreNamedRoutesNotLiteralPathsTests(SimpleTestCase):
    def test_the_kernel_holds_no_literal_paths(self):
        src = Path("apps/platform_runtime/action_hub_kernel.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            'href="/',
            src,
            "a literal path is back; use url_name so a moved route breaks a test",
        )

    def test_a_state_token_chip_still_finds_its_link(self):
        """Persona must reach the registry or every such chip resolves to None."""
        hub = build_tenant_admin_hub(pending_admissions=3)
        self.assertTrue(
            _chips(hub),
            "the admissions chip resolved to nothing — is persona being passed "
            "through to get_smart_links?",
        )

    def test_an_alert_without_a_count_still_reaches_the_strip(self):
        hrefs = [href for href, _ in _chips(build_parent_hub(records_hold_active=True))]
        self.assertTrue(hrefs, "a danger-severity transcript hold rendered nothing")


@override_settings(ROOT_URLCONF=TENANT_URLCONF)
class ClicksSavedIsDerivedNotAssertedTests(SimpleTestCase):
    def test_a_deeper_destination_saves_more(self):
        self.assertEqual(clicks_saved_for_path("/portal/teacher/homework/gradebook/"), 3)
        self.assertEqual(clicks_saved_for_path("/authentication/messages/"), 1)

    def test_a_querystring_is_not_a_navigation_step(self):
        self.assertEqual(
            clicks_saved_for_path("/finance/invoices/?status=OVERDUE"),
            clicks_saved_for_path("/finance/invoices/"),
        )

    def test_no_destination_saves_nothing(self):
        self.assertEqual(clicks_saved_for_path(""), 0)
        self.assertEqual(clicks_saved_for_path("/"), 0)

    def test_every_rendered_chip_reports_what_it_saved(self):
        for name, build in LOADED.items():
            for href, saved in _chips(build()):
                with self.subTest(persona=name, href=href):
                    self.assertGreater(
                        int(saved),
                        0,
                        "a chip that leads somewhere must report a saving",
                    )

    def test_the_daily_ops_registry_reports_a_saving_for_every_role(self):
        from apps.platform_runtime.tenant_daily_ops import (
            WORKFLOW_ACTIONS,
            next_best_actions_for_role,
            resolve_action_urls,
        )

        class _User:
            role = ""

        for role in WORKFLOW_ACTIONS:
            user = _User()
            user.role = role
            rows = resolve_action_urls(next_best_actions_for_role(None, user))
            with self.subTest(role=role):
                self.assertTrue(rows, f"{role} has no surviving next-best action")
                for row in rows:
                    self.assertGreater(row["clicks_saved"], 0, row["key"])

    def test_no_hand_written_saving_creeps_back(self):
        """A number nobody can recompute is the aspiration wearing a digit."""
        src = Path("apps/platform_runtime/tenant_daily_ops.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            '"clicks_saved":',
            src,
            "clicks_saved is derived in click_budget; do not assign it by hand",
        )
