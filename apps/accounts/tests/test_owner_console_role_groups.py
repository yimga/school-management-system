"""Owner Console — Role bundles (RoleGroup).

Define a named bundle of access roles once, then apply it to many people at once
(additive). Owner-gated, school-scoped, no cross-tenant leakage. Applying a bundle
never strips a member's existing roles.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


class OwnerConsoleRoleGroupsTests(TestCase):
    def setUp(self):
        from apps.accounts.models import AccessRole
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="New High School", subdomain="ocrg-newhigh", slug="ocrg-newhigh", is_active=True,
        )
        self.owner = U.objects.create(username="nina", role="ADMIN")
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role="ADMIN", is_school_owner=True, is_primary=True,
        )
        self.u1 = U.objects.create(username="amy", role="TEACHER")
        self.u2 = U.objects.create(username="ben", role="TEACHER")
        for u in (self.u1, self.u2):
            SchoolMembership.objects.create(user=u, school=self.school, role="TEACHER")
        self.member = U.objects.create(username="sam", role="TEACHER")
        SchoolMembership.objects.create(user=self.member, school=self.school, role="TEACHER")

        self.r1 = AccessRole.objects.create(school=self.school, code="form_teacher", name="Form Teacher")
        self.r2 = AccessRole.objects.create(school=self.school, code="exams_officer", name="Exams Officer")

    def _req(self, user, method="get", data=None):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware

        req = getattr(self.rf, method)("/authentication/owner/role-groups/", data or {})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        req._messages = FallbackStorage(req)
        req.user = user
        req.school = self.school
        return req

    def _view(self):
        from apps.accounts.views_owner_console_roles import owner_console_role_groups

        return owner_console_role_groups

    # ── gate ─────────────────────────────────────────────────────────────────
    def test_owner_renders(self):
        resp = self._view()(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("Role bundles", html)

    def test_non_owner_forbidden(self):
        self.assertEqual(self._view()(self._req(self.member)).status_code, 403)

    def test_nav_includes_rolegroups(self):
        from apps.accounts.views_owner_console import _console_sections

        sections = _console_sections("rolegroups")
        keys = {s["key"] for s in sections}
        self.assertIn("rolegroups", keys)
        self.assertTrue(all(s["url"] for s in sections))
        self.assertTrue(next(s for s in sections if s["key"] == "rolegroups")["active"])

    # ── create ───────────────────────────────────────────────────────────────
    def test_create_bundle(self):
        from apps.accounts.models import RoleGroup

        resp = self._view()(
            self._req(self.owner, "post", {
                "action": "create", "name": "Form Teacher", "roles": [self.r1.pk, self.r2.pk],
            })
        )
        self.assertEqual(resp.status_code, 302)
        g = RoleGroup.objects.get(school=self.school, code="form_teacher")
        self.assertEqual(g.name, "Form Teacher")
        self.assertEqual(set(g.roles.values_list("code", flat=True)), {"form_teacher", "exams_officer"})

    def test_create_duplicate_name_rejected(self):
        from apps.accounts.models import RoleGroup

        for _i in range(2):
            self._view()(
                self._req(self.owner, "post", {
                    "action": "create", "name": "Leadership", "roles": [self.r1.pk],
                })
            )
        self.assertEqual(RoleGroup.objects.filter(school=self.school, code="leadership").count(), 1)

    def test_create_by_non_owner_refused(self):
        from apps.accounts.models import RoleGroup

        resp = self._view()(
            self._req(self.member, "post", {
                "action": "create", "name": "Sneaky", "roles": [self.r1.pk],
            })
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(RoleGroup.objects.filter(school=self.school).exists())

    # ── apply ────────────────────────────────────────────────────────────────
    def test_apply_bundle_additive(self):
        from apps.accounts.models import RoleGroup

        group = RoleGroup.objects.create(school=self.school, code="form_teacher", name="Form Teacher")
        group.roles.set([self.r1, self.r2])
        resp = self._view()(
            self._req(self.owner, "post", {
                "action": "apply", "group": group.pk, "users": [self.u1.pk, self.u2.pk],
            })
        )
        self.assertEqual(resp.status_code, 302)
        # additive on top of the auto-synced scalar-role AccessRole
        for u in (self.u1, self.u2):
            codes = set(u.roles.values_list("code", flat=True))
            self.assertTrue({"form_teacher", "exams_officer"}.issubset(codes))

    # ── delete ───────────────────────────────────────────────────────────────
    def test_delete_bundle_keeps_assigned_roles(self):
        from apps.accounts.models import RoleGroup

        group = RoleGroup.objects.create(school=self.school, code="form_teacher", name="Form Teacher")
        group.roles.set([self.r1])
        self.u1.roles.add(self.r1)
        self._view()(
            self._req(self.owner, "post", {"action": "delete", "group_id": group.pk})
        )
        self.assertFalse(RoleGroup.objects.filter(pk=group.pk).exists())
        # deleting the bundle must not strip a role already granted to a member
        self.assertIn("form_teacher", set(self.u1.roles.values_list("code", flat=True)))

    def test_template_compiles(self):
        from django.template.loader import get_template

        get_template("accounts/owner_console/role_groups.html")
