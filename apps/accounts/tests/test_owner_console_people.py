"""Owner Console — slice 3: People & Roles (bulk multi-role assignment).

Select many people, apply many roles at once — additive (existing roles kept),
owner-gated, no migration (uses the existing User.roles M2M to AccessRole).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

U = get_user_model()


class OwnerConsolePeopleTests(TestCase):
    def setUp(self):
        from apps.accounts.models import AccessRole
        from apps.schools.models import School, SchoolMembership

        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="New High School", subdomain="ocp-newhigh", slug="ocp-newhigh", is_active=True,
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

        req = getattr(self.rf, method)("/authentication/owner/people/", data or {})
        SessionMiddleware(lambda r: None).process_request(req)
        req.session.save()
        # the POST path flashes messages — attach a storage (as MessageMiddleware would)
        req._messages = FallbackStorage(req)
        req.user = user
        req.school = self.school
        return req

    def test_owner_renders_people(self):
        from apps.accounts.views_owner_console_people import owner_console_people

        resp = owner_console_people(self._req(self.owner))
        self.assertEqual(resp.status_code, 200)
        html = resp.render().content.decode() if hasattr(resp, "render") else resp.content.decode()
        self.assertIn("People &amp; Roles", html)

    def test_non_owner_forbidden(self):
        from apps.accounts.views_owner_console_people import owner_console_people

        self.assertEqual(owner_console_people(self._req(self.member)).status_code, 403)

    def test_bulk_assign_many_roles_to_many_users_additive(self):
        from apps.accounts.views_owner_console_people import owner_console_people

        resp = owner_console_people(
            self._req(
                self.owner,
                method="post",
                data={"users": [self.u1.pk, self.u2.pk], "roles": [self.r1.pk, self.r2.pk]},
            )
        )
        self.assertEqual(resp.status_code, 302)
        # Members carry an auto-synced AccessRole for their scalar role (e.g.
        # "TEACHER"); the bulk grant is ADDITIVE on top, so assert our two roles
        # are present rather than asserting an exact/zero baseline.
        for u in (self.u1, self.u2):
            codes = set(u.roles.values_list("code", flat=True))
            self.assertTrue({"form_teacher", "exams_officer"}.issubset(codes))
        # additive: a second apply of just r1 keeps both
        owner_console_people(
            self._req(self.owner, method="post", data={"users": [self.u1.pk], "roles": [self.r1.pk]})
        )
        self.assertTrue(
            {"form_teacher", "exams_officer"}.issubset(
                set(self.u1.roles.values_list("code", flat=True))
            )
        )

    def test_bulk_assign_by_non_owner_refused(self):
        from apps.accounts.views_owner_console_people import owner_console_people

        resp = owner_console_people(
            self._req(self.member, method="post", data={"users": [self.u1.pk], "roles": [self.r1.pk]})
        )
        self.assertEqual(resp.status_code, 403)
        # the blocked POST must not have granted the target role
        self.assertNotIn("form_teacher", set(self.u1.roles.values_list("code", flat=True)))

    def test_empty_selection_reprompts_without_change(self):
        from apps.accounts.views_owner_console_people import owner_console_people

        resp = owner_console_people(self._req(self.owner, method="post", data={}))
        self.assertEqual(resp.status_code, 200)  # re-renders form with an error
        # the invalid submit must not have granted the target role
        self.assertNotIn("form_teacher", set(self.u1.roles.values_list("code", flat=True)))
