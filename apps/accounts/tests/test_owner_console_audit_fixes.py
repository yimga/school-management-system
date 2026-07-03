"""Owner Console — audit remediation.

Locks two fixes surfaced by the program audit:
  HOLE #1 — a SUSPENDED owner must lose Owner Console authority (the gate now uses
            SchoolMembership.is_active_owner, which filters suspended_at).
  HOLE #2 — deleting a role bundle with a non-numeric group_id must not 500.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

U = get_user_model()


class OwnerConsoleAuditFixTests(TestCase):
    def setUp(self):
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="New High", subdomain="ocaf-new", slug="ocaf-new", is_active=True,
        )
        self.owner = U.objects.create(username="nina", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN",
            is_school_owner=True, is_primary=True,
        )
        # An owner who has been SUSPENDED to revoke their authority.
        self.suspended = U.objects.create(username="zed", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.suspended, school=self.school, role="ADMIN",
            is_school_owner=True, suspended_at=timezone.now(),
        )

    def _req(self, user, method="get", data=None, path="/authentication/owner/"):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware

        req = getattr(self.rf, method)(path, data or {})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req._messages = FallbackStorage(req)
        req.user = user
        req.school = self.school
        return req

    # ── HOLE #1 ──────────────────────────────────────────────────────────────
    def test_is_active_owner_excludes_suspended(self):
        from apps.schools.models import SchoolMembership

        self.assertTrue(SchoolMembership.is_active_owner(self.owner, self.school))
        self.assertFalse(SchoolMembership.is_active_owner(self.suspended, self.school))
        # the raw check still sees the suspended member as an owner
        self.assertTrue(SchoolMembership.is_owner(self.suspended, self.school))

    def test_active_owner_still_admitted(self):
        from apps.accounts.views_owner_console import is_school_owner, owner_console_overview

        self.assertTrue(is_school_owner(self.owner, self.school))
        self.assertEqual(owner_console_overview(self._req(self.owner)).status_code, 200)

    def test_suspended_owner_denied_console(self):
        from apps.accounts.views_owner_console import is_school_owner, owner_console_overview

        self.assertFalse(is_school_owner(self.suspended, self.school))
        self.assertEqual(owner_console_overview(self._req(self.suspended)).status_code, 403)

    def test_suspended_owner_denied_role_groups(self):
        from apps.accounts.views_owner_console_roles import owner_console_role_groups

        resp = owner_console_role_groups(
            self._req(self.suspended, path="/authentication/owner/role-groups/")
        )
        self.assertEqual(resp.status_code, 403)

    # ── HOLE #2 ──────────────────────────────────────────────────────────────
    def test_delete_nonnumeric_group_id_no_500(self):
        from apps.accounts.views_owner_console_roles import owner_console_role_groups

        resp = owner_console_role_groups(
            self._req(
                self.owner, "post",
                {"action": "delete", "group_id": "not-a-number"},
                path="/authentication/owner/role-groups/",
            )
        )
        self.assertEqual(resp.status_code, 302)  # graceful redirect, never a 500
