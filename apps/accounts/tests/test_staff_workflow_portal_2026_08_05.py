"""Must-fire tests: operational staff get a 'My Workflow' portal (2026-08-05).

Pre-fix, teacher/parent/student each had a per-role workflow portal but the ~20
non-admin operational roles (bursar, HOD, secretary, …) had none — they fell to a
bare 'Home' link. These assert the new staff launcher exists, admits operational
staff (not parents/students), builds real entitled cards, and is wired into nav.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.views_workflow import (
    _is_tenant_staff_member,
    _staff_workflow_cards,
)
from apps.siteconfig.tests._template_nodes import assert_markup

TENANT_PRIMARY_NAV = Path("templates/partials/tenant_primary_nav.html")


class StaffWorkflowGateTests(TestCase):
    def test_bursar_is_a_tenant_staff_member(self):
        bursar = User.objects.create_user(
            username="bursar_wf", password="x", role="BURSAR"
        )
        self.assertTrue(_is_tenant_staff_member(bursar))

    def test_parent_and_student_are_not(self):
        parent = User.objects.create_user(username="par_wf", password="x", role="PARENT")
        student = User.objects.create_user(
            username="stu_wf", password="x", role="STUDENT"
        )
        self.assertFalse(_is_tenant_staff_member(parent))
        self.assertFalse(_is_tenant_staff_member(student))

    def test_anonymous_is_not(self):
        self.assertFalse(_is_tenant_staff_member(None))


class StaffWorkflowCardsTests(TestCase):
    def test_bursar_gets_entitled_cards(self):
        bursar = User.objects.create_user(
            username="bursar_cards", password="x", role="BURSAR"
        )
        cards = _staff_workflow_cards(SimpleNamespace(user=bursar, school=None))
        # A bursar can reach the approval hub, so at least the Approvals card is built.
        self.assertTrue(cards)
        labels = {str(c["label"]) for c in cards}
        self.assertIn("Approvals", labels)


class StaffWorkflowRoutingTests(SimpleTestCase):
    def test_url_resolves(self):
        # Pre-fix there was no such route.
        self.assertTrue(reverse("accounts:staff_workflow"))

    def test_nav_has_staff_workflow_pill(self):
        nav = TENANT_PRIMARY_NAV.read_text(encoding="utf-8")
        # The route name is a {% url %} ARGUMENT -- template code no parse and no
        # render can see -- so that assertion stays a source read. The PILL is
        # markup, though, and "nav has a pill" is a claim about the page: the
        # lightning glyph is carried only by the Workflow links, so a nav whose
        # body has been commented out emits it nowhere.
        assert_markup(
            self,
            TENANT_PRIMARY_NAV,
            'data-rmc-tenant-primary-nav="1"',
            "bi-lightning-charge",
        )
        self.assertIn("accounts:staff_workflow", nav)
