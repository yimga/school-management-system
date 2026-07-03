"""Owner Console — slice 1: first-login owner confirmation card.

The very first time a school creator lands on their backend dashboard they see a
one-time "you're the owner" card (confirm / assign a superadmin / decide later).
It reflects authority they already hold and never grants ``is_staff``.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


def _landing_request(rf, user, school):
    """A request that looks like the owner's backend-dashboard landing."""
    req = rf.get("/authentication/backend/")
    req.user = user
    req.school = school
    req.resolver_match = SimpleNamespace(view_name="accounts:backend_dashboard")
    return req


class OwnerFirstLoginCardTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="New High School",
            subdomain="ofl-newhigh",
            slug="ofl-newhigh",
            is_active=True,
        )
        self.owner = U.objects.create(username="nina", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner,
            school=self.school,
            role="ADMIN",
            is_school_owner=True,
            is_primary=True,
        )
        self.member = U.objects.create(username="sam", role="TEACHER")
        SchoolMembership.objects.create(
            user=self.member,
            school=self.school,
            role="TEACHER",
            is_school_owner=False,
        )

    # ── the card gate ────────────────────────────────────────────────────────
    def test_card_shown_for_new_owner(self):
        from apps.accounts.owner_first_login import build_owner_first_login_card

        card = build_owner_first_login_card(
            _landing_request(self.rf, self.owner, self.school)
        )
        self.assertIsNotNone(card)
        self.assertEqual(card["school_name"], "New High School")
        self.assertIn("Owner", str(card["role_label"]))
        self.assertTrue(card["confirm_url"])

    def test_card_hidden_for_non_owner(self):
        from apps.accounts.owner_first_login import build_owner_first_login_card

        card = build_owner_first_login_card(
            _landing_request(self.rf, self.member, self.school)
        )
        self.assertIsNone(card)

    def test_card_hidden_off_the_landing(self):
        from apps.accounts.owner_first_login import build_owner_first_login_card

        req = self.rf.get("/somewhere/else/")
        req.user = self.owner
        req.school = self.school
        req.resolver_match = SimpleNamespace(view_name="portal:teacher_dashboard_alias")
        self.assertIsNone(build_owner_first_login_card(req))

    def test_card_hidden_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        from apps.accounts.owner_first_login import build_owner_first_login_card

        req = self.rf.get("/authentication/backend/")
        req.user = AnonymousUser()
        req.school = self.school
        req.resolver_match = SimpleNamespace(view_name="accounts:backend_dashboard")
        self.assertIsNone(build_owner_first_login_card(req))

    # ── the confirm endpoint ─────────────────────────────────────────────────
    def test_confirm_records_ack_and_hides_card(self):
        from apps.accounts.owner_first_login import (
            build_owner_first_login_card,
            owner_role_acknowledged,
        )
        from apps.accounts.views_onboarding import owner_confirm_role

        req = self.rf.post(
            "/authentication/backend/confirm-owner/",
            {"decision": "confirm"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        req.user = self.owner
        req.school = self.school
        resp = owner_confirm_role(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(owner_role_acknowledged(self.owner, self.school))
        self.assertIsNone(
            build_owner_first_login_card(
                _landing_request(self.rf, self.owner, self.school)
            )
        )

    def test_defer_records_deferred_and_hides_card(self):
        from apps.accounts.owner_first_login import (
            ACK_DEFERRED,
            build_owner_first_login_card,
            owner_ack_key,
            owner_role_acknowledged,
        )
        from apps.accounts.views_onboarding import owner_confirm_role
        from apps.runtime_blueprints.models import DashboardUserPreference

        req = self.rf.post("/x/", {"decision": "defer"})
        req.user = self.owner
        req.school = self.school
        owner_confirm_role(req)

        pref = DashboardUserPreference.objects.get(user=self.owner)
        self.assertEqual(
            pref.dashboard_layout.get(owner_ack_key(self.school)), ACK_DEFERRED
        )
        self.assertTrue(owner_role_acknowledged(self.owner, self.school))
        self.assertIsNone(
            build_owner_first_login_card(
                _landing_request(self.rf, self.owner, self.school)
            )
        )

    def test_non_owner_cannot_record_ack(self):
        """Defence in depth: the endpoint must refuse a non-owner even if reached."""
        from apps.accounts.owner_first_login import owner_role_acknowledged
        from apps.accounts.views_onboarding import owner_confirm_role

        req = self.rf.post("/x/", {"decision": "confirm"})
        req.user = self.member
        req.school = self.school
        owner_confirm_role(req)
        self.assertFalse(owner_role_acknowledged(self.member, self.school))

    def test_confirm_grants_no_staff_or_superuser(self):
        """The card only reflects existing authority — it never elevates the user."""
        from apps.accounts.views_onboarding import owner_confirm_role

        req = self.rf.post(
            "/x/", {"decision": "confirm"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        req.user = self.owner
        req.school = self.school
        owner_confirm_role(req)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_staff)
        self.assertFalse(self.owner.is_superuser)
