"""The readiness bar counted only the steps it could evaluate, so it read high.

    progress_pct = int(round(100.0 * passed / evaluated))

``evaluated`` is the suite's count of rows it actually RAN. Every step skipped for the
host, and every step the read-only preview never asks about, left the denominator --
and the bar went UP. Measured on the live Gilead tenant before the fix:

    operator console (manager host)   bar said 20%   true 11%   7 of 17 steps hidden
    box                               bar said 43%   true 35%   3 of 17 steps hidden

The error runs one way (always optimistic) and is largest exactly where the reader can
see least. Somebody reads that bar to decide whether they are nearly done.

WHY THESE READ THE RENDERED PAGE. ``response.context`` is ``None`` throughout this
suite -- Django's template instrumentation is not active here, which is why every
existing test in this app asserts on ``response.content``. That turns out to be the
better test anyway: a number that is correct in the context and absent from the page
has not fixed anything, and these assertions fail if the template stops printing it.
"""
from __future__ import annotations

import re
import uuid
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.lifecycle import edge_onboarding as eo
from apps.lifecycle import views_edge_onboarding as views
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass
from apps.test_utils.http_clients import login_manager_client

MANAGER_HOST = "manager.runmycampus.com"

#: "6 of 17 steps complete (35%)" -- what the reader actually sees.
_BAR_TEXT = re.compile(r"(\d+)\s+of\s+(\d+)\s+steps complete\s*\((\d+)%\)")
_ARIA_NOW = re.compile(r'aria-valuenow="(\d+)"')


def _make_school(slug, name):
    with rls_bypass():
        School.objects.filter(slug=slug).delete()
    return School.objects.create(
        id=uuid.uuid4(),
        name=name,
        slug=slug,
        subdomain=slug,
        is_active=False,
        is_approved=True,
        country_code="CM",
        settings={},
    )


@override_settings(ALLOWED_HOSTS=["*"])
class TheBarMustCountEveryStepTests(TestCase):
    SLUG = "edge-progress-school"
    PASSWORD = "testpass123"

    def setUp(self):
        self.operator = User.objects.create_user(
            username="edge_progress_operator",
            password=self.PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(self.operator, password=self.PASSWORD)
        self.school = _make_school(self.SLUG, "Edge Progress High School")
        self.url = reverse("super:edge_onboarding_runbook")

    def _body(self):
        response = self.client.get(
            self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def _rendered_bar(self):
        match = _BAR_TEXT.search(self._body())
        self.assertIsNotNone(match, "the page no longer prints the step count")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    def test_the_denominator_on_the_page_is_every_step(self):
        # The whole bug in one assertion. A fresh inactive school on a manager host
        # has steps the console cannot evaluate; they must stay in the total.
        _done, total, _pct = self._rendered_bar()
        self.assertEqual(total, len(eo.EDGE_ONBOARDING_STEPS))

    def test_the_old_formula_would_have_reported_a_higher_number(self):
        # Runs the OLD formula against the same school and pins the relationship, so
        # this fails if anybody reverts the denominator.
        runbook = views._safe_runbook(self.school, host_kind="manager")
        progress = runbook["progress"]
        verification = runbook["verification"]
        evaluated = int(verification.get("evaluated") or verification.get("total") or 0)
        passed = int(verification.get("passed") or 0)
        old = int(round(100.0 * passed / evaluated)) if evaluated else 0
        self.assertLess(
            evaluated,
            progress["total"],
            "this fixture no longer exercises the bug -- it needs unevaluated steps",
        )
        self.assertLess(
            progress["percent"],
            old,
            "the honest percentage must be lower than the one that hid steps",
        )
        _done, _total, rendered_pct = self._rendered_bar()
        self.assertEqual(rendered_pct, progress["percent"])

    def test_the_bar_fill_and_the_text_agree(self):
        # A fill computed from one number over text computed from another is the
        # failure this whole change exists to prevent.
        #
        # Scoped to OUR bar deliberately: the shell renders two other progressbars
        # (the lifecycle journey navigator, and the sidebar resize handle, which
        # announces its pixel width as aria-valuenow="280"). An unscoped search
        # reads whichever appears first in the document, which is how this test
        # first failed -- comparing a sidebar width against a percentage.
        _done, _total, pct = self._rendered_bar()
        body = self._body()
        anchor = body.index('id="edge-onboarding-progress-h"')
        aria = _ARIA_NOW.search(body, anchor)
        self.assertIsNotNone(aria, "the onboarding bar lost its aria-valuenow")
        self.assertEqual(int(aria.group(1)), pct)

    def test_the_counts_partition_the_steps(self):
        progress = views._safe_runbook(self.school, host_kind="manager")["progress"]
        self.assertEqual(
            progress["done"]
            + progress["todo"]
            + progress["skipped"]
            + progress["not_checked"],
            progress["total"],
        )
        self.assertGreater(progress["skipped"] + progress["not_checked"], 0)

    def test_the_page_explains_the_steps_it_could_not_check(self):
        # Being in the denominator is not enough. If a reader cannot see WHY the bar
        # is short, the fix just turns an optimistic bar into a stuck one.
        self.assertIn("only be checked on the box", self._body())

    def test_the_page_says_how_many_remaining_steps_need_a_person(self):
        # The number that decides whether any of this is self-service.
        progress = views._safe_runbook(self.school, host_kind="manager")["progress"]
        self.assertEqual(
            progress["needs_a_person"], progress["todo"] - progress["healable_todo"]
        )
        self.assertIn("need a person", self._body())

    def test_the_bar_and_the_list_come_from_one_run(self):
        # Recomputing from the step list must reproduce the header exactly.
        runbook = views._safe_runbook(self.school, host_kind="manager")
        self.assertEqual(eo.runbook_progress(runbook["steps"]), runbook["progress"])

    def test_the_bar_is_announced_to_a_screen_reader(self):
        body = self._body()
        self.assertIn('role="progressbar"', body)
        self.assertIn('aria-valuenow="', body)

    def test_the_suite_runs_once_per_request_not_twice(self):
        # It used to run twice: bare for the runbook, again for the readiness panel.
        # Beyond the wasted work, that is what allowed the two to disagree.
        real = eo.run_verification_suite
        with mock.patch.object(eo, "run_verification_suite", side_effect=real) as spy:
            self._body()
        self.assertEqual(spy.call_count, 1, "the suite ran %d times" % spy.call_count)

    def test_a_GET_still_records_no_sync_run(self):
        # The page now reaches the suite through generate_runbook. If that ever
        # switched to include_gate=True, opening a tab would write an EdgeSyncRun and
        # an operator could not tell their own gate result from somebody browsing.
        from apps.sync_engine.models import EdgeSyncRun

        with rls_bypass():
            before = EdgeSyncRun.objects.count()
        self._body()
        with rls_bypass():
            self.assertEqual(EdgeSyncRun.objects.count(), before)

    def test_a_failure_to_build_the_runbook_still_renders_a_page(self):
        # The surface must never 500 over a read. The failure path also has to supply
        # a progress block, or the template renders a bar with no numbers -- which
        # looks like a confident 0%, not like "we could not tell".
        with mock.patch.object(
            eo, "generate_runbook", side_effect=RuntimeError("boom")
        ):
            response = self.client.get(
                self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
            )
        self.assertEqual(response.status_code, 200)
        fallback = views._safe_runbook(self.school, host_kind="manager")
        self.assertIn("progress", fallback)

    def test_the_failure_path_supplies_the_whole_progress_shape(self):
        # A missing key renders as an empty bar segment, which reads as a confident
        # zero. The failure path must produce the same keys as the success path.
        with mock.patch.object(
            eo, "generate_runbook", side_effect=RuntimeError("boom")
        ):
            broken = views._safe_runbook(self.school, host_kind="manager")
        good = views._safe_runbook(self.school, host_kind="manager")
        self.assertEqual(set(broken["progress"]), set(good["progress"]))
        self.assertEqual(broken["progress"]["total"], 0)


@override_settings(ALLOWED_HOSTS=["*"])
class TheTextRenderingStillWorksTests(TestCase):
    """``?format=txt`` shares the changed data path and must not have broken."""

    SLUG = "edge-progress-txt"
    PASSWORD = "testpass123"

    def setUp(self):
        self.operator = User.objects.create_user(
            username="edge_progress_txt_op",
            password=self.PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(self.operator, password=self.PASSWORD)
        _make_school(self.SLUG, "Edge Progress Text School")
        self.url = reverse("super:edge_onboarding_runbook")

    def test_the_plain_text_runbook_still_renders_its_readiness_lines(self):
        response = self.client.get(
            self.url, {"school": self.SLUG, "format": "txt"}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Readiness preview", body)
        self.assertIn("RUNBOOK (run each command on the host in runs_on)", body)
        # The flags still render: the txt path reads the suite that now arrives
        # attached to the runbook instead of coming from its own second call.
        self.assertRegex(body, r"\[(PASS|FAIL|SKIP)\] ")
