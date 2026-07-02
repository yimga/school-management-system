"""SSO tenant binding — multi-binding schema + JIT membership (first direct tests).

Locks the 9.8 SSO wave (2026-07-02). Before it: ``UserTenantBinding.user``
was a OneToOneField (one user → one tenant, contradicting SchoolMembership's
first-class multi-school support), the control-plane OIDC/SAML flows wrote
the binding but NO membership (a fresh SSO user authenticated with zero
tenant access), the operator reassign view was keyed on ``user_id`` alone,
and the model had zero direct test coverage anywhere.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from apps.accounts.models_sso import UserTenantBinding
from apps.api.oidc_rp import _bind_tenant_for_user
from apps.portal.views_tenant_binding import tenant_binding_reassign
from apps.schools.models import School, SchoolMembership


class MultiBindingSchemaTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school_a = School.objects.create(name="Binding School A", slug="bind-a", subdomain="bind-a")
        self.school_b = School.objects.create(name="Binding School B", slug="bind-b", subdomain="bind-b")
        self.user = User.objects.create_user(username="bind_user", password="Test1234!")

    def test_user_can_bind_to_two_schools(self):
        UserTenantBinding.objects.create(
            user=self.user, school=self.school_a, source="oidc", is_primary=True
        )
        UserTenantBinding.objects.create(
            user=self.user, school=self.school_b, source="manual", is_primary=False
        )
        self.assertEqual(self.user.tenant_bindings.count(), 2)

    def test_duplicate_user_school_rejected(self):
        UserTenantBinding.objects.create(
            user=self.user, school=self.school_a, source="oidc", is_primary=True
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserTenantBinding.objects.create(
                user=self.user, school=self.school_a, source="saml", is_primary=False
            )

    def test_two_primaries_rejected(self):
        UserTenantBinding.objects.create(
            user=self.user, school=self.school_a, source="oidc", is_primary=True
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserTenantBinding.objects.create(
                user=self.user, school=self.school_b, source="oidc", is_primary=True
            )


class SsoBindFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Binding School C", slug="bind-c", subdomain="bind-c")
        self.user = User.objects.create_user(
            username="bind_teacher", password="Test1234!"
        )

    def _teacher_profile(self):
        from apps.people.models import TeacherProfile

        return TeacherProfile.objects.create(user=self.user, school=self.school)

    def test_bind_creates_binding_and_jit_membership(self):
        self._teacher_profile()
        _bind_tenant_for_user(
            self.user, source="oidc", provider="azure", subject="sub-1", issuer="iss-1"
        )
        binding = UserTenantBinding.objects.get(user=self.user, school=self.school)
        self.assertTrue(binding.is_primary)
        # The forked-stacks hole: binding without membership = access-less
        # login. JIT membership must now exist, mirroring the user's role.
        membership = SchoolMembership.objects.get(user=self.user, school=self.school)
        self.assertEqual(membership.role, self.user.role)
        self.assertTrue(membership.is_primary)

    def test_relogin_refreshes_claims_no_duplicate(self):
        self._teacher_profile()
        _bind_tenant_for_user(
            self.user, source="oidc", provider="azure", subject="sub-1", issuer="iss-1"
        )
        _bind_tenant_for_user(
            self.user, source="oidc", provider="azure", subject="sub-2", issuer="iss-1"
        )
        bindings = UserTenantBinding.objects.filter(user=self.user)
        self.assertEqual(bindings.count(), 1)
        self.assertEqual(bindings.first().subject, "sub-2")
        self.assertEqual(
            SchoolMembership.objects.filter(user=self.user, school=self.school).count(), 1
        )

    def test_jit_membership_never_downgrades_existing(self):
        self._teacher_profile()
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True  # role-string-allow: test fixture asserting JIT never downgrades an existing membership
        )
        _bind_tenant_for_user(
            self.user, source="saml", provider="okta", subject="sub-9", issuer="iss-9"
        )
        membership = SchoolMembership.objects.get(user=self.user, school=self.school)
        self.assertEqual(membership.role, "ADMIN")  # role-string-allow: assertion mirror of the fixture above

    def test_no_school_resolvable_writes_nothing(self):
        _bind_tenant_for_user(
            self.user, source="oidc", provider="azure", subject="sub-1", issuer="iss-1"
        )
        self.assertFalse(UserTenantBinding.objects.filter(user=self.user).exists())


class ReassignViewMultiBindingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school_a = School.objects.create(name="Binding School D", slug="bind-d", subdomain="bind-d")
        self.school_b = School.objects.create(name="Binding School E", slug="bind-e", subdomain="bind-e")
        self.user = User.objects.create_user(username="bind_target", password="Test1234!")
        self.staff = User.objects.create_user(
            username="bind_operator", password="Test1234!", is_staff=True
        )
        UserTenantBinding.objects.create(
            user=self.user, school=self.school_a, source="oidc",
            provider="azure", subject="sub-keep", is_primary=True,
        )

    def _reassign(self, school):
        request = RequestFactory().post(
            "/portal/super/sso/bindings/reassign/",
            {"user": str(self.user.pk), "school": str(school.pk), "format": "json"},
        )
        request.user = self.staff
        request._dont_enforce_csrf_checks = True
        return tenant_binding_reassign(request)

    def test_reassign_adds_second_binding_and_moves_primary(self):
        response = self._reassign(self.school_b)
        self.assertEqual(response.status_code, 200)
        old = UserTenantBinding.objects.get(user=self.user, school=self.school_a)
        new = UserTenantBinding.objects.get(user=self.user, school=self.school_b)
        # Multi-binding: the original binding survives (audit trail intact,
        # provider/subject preserved), only primacy moves.
        self.assertFalse(old.is_primary)
        self.assertEqual(old.subject, "sub-keep")
        self.assertTrue(new.is_primary)
        self.assertEqual(new.source, "manual")
        self.assertEqual(UserTenantBinding.objects.filter(user=self.user).count(), 2)

    def test_reassign_to_same_school_idempotent(self):
        response = self._reassign(self.school_a)
        self.assertEqual(response.status_code, 200)
        row = UserTenantBinding.objects.get(user=self.user, school=self.school_a)
        self.assertTrue(row.is_primary)
        self.assertEqual(row.source, "manual")
        self.assertEqual(UserTenantBinding.objects.filter(user=self.user).count(), 1)
