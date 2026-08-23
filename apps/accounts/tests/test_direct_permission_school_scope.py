"""A direct permission grant must not travel to another tenant.

``User.has_feature_permission(code, school=...)`` school-scopes the AccessRole
branch and the TemporaryRoleGrant branch, but short-circuited FIRST on
``self.feature_permissions.filter(code=code).exists()`` with the ``school``
argument ignored. ``feature_permissions`` is written from tenant surfaces -- the
RBAC console's ``user_permissions`` branch does ``.set()`` over
``Permission.objects.all()`` -- and this is the resolver behind
``user_has_permission`` -> ``require_permission`` -> ``permission_access``, so
EVERY surface gated on a granular code was affected.

Concretely: School A's admin grants ``finance.manage`` to U on the RBAC console.
U is also a PARENT at School B. ``require_permission("finance.manage")`` on School
B's tenant host then passed for U.

Not theoretical -- ``apps/sync_engine/pairing_service.py`` records this exact call
MEASURED returning True for a user whose only membership was in a different
school, which is why the pairing path stopped consulting it; the resolver itself
was never fixed.

Uses RequestFactory and calls the view directly, matching
test_access_role_school_scope.py: the tenant MFA middleware otherwise redirects a
privileged view to /mfa/setup/ and the assertion becomes vacuous.
"""

from __future__ import annotations

import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import FeaturePermissionScope, Permission, User
from apps.accounts.views import rbac_dashboard
from apps.schools.models import School, SchoolMembership


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="off")
class DirectPermissionGrantIsSchoolScopedTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        tag = uuid.uuid4().hex[:8]
        self.school_a = School.objects.create(
            name="Direct A",
            slug=f"dra-{tag}",
            subdomain=f"dra-{tag}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Direct B",
            slug=f"drb-{tag}",
            subdomain=f"drb-{tag}",
            is_active=True,
        )
        # A code no seeded global template grants, so a signal-attached role
        # cannot make the "held at B" assertion pass for the wrong reason.
        self.code = f"scopedgrant.{tag}"
        self.perm = Permission.objects.create(
            code=self.code, name="Scoped grant probe"
        )
        self.other_code = f"othergrant.{tag}"
        self.other_perm = Permission.objects.create(
            code=self.other_code, name="Other grant probe"
        )

        self.admin = User.objects.create_user(
            username=f"rbacadmin-{tag}",
            email=f"rbacadmin-{tag}@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_superuser=True,
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school_a, role="ADMIN", is_school_owner=True
        )
        # The multi-school account: staff at A, parent at B.
        self.target = User.objects.create_user(
            username=f"dualmember-{tag}",
            email=f"dualmember-{tag}@example.com",
            password="pass12345678",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.create(
            user=self.target, school=self.school_a, role="ADMIN"
        )
        SchoolMembership.objects.create(
            user=self.target, school=self.school_b, role="PARENT"
        )

    def _grant_via_console(self, codes, school):
        perms = Permission.objects.filter(code__in=codes)
        request = self.factory.post(
            "/authentication/rbac/",
            {
                "form_type": "user_permissions",
                "user_permission-user": str(self.target.pk),
                "user_permission-permissions": [str(p.pk) for p in perms],
            },
        )
        request.user = self.admin
        request.school = school
        request.session = {}
        request._messages = FallbackStorage(request)
        return rbac_dashboard(request)

    def test_the_console_actually_grants_at_its_own_school(self) -> None:
        """Guard: without this, every "not held at B" assertion below would also
        pass against a view that 403'd, a form that rejected the POST, or a
        fixture whose permission pk never reached the writer."""
        response = self._grant_via_console([self.code], self.school_a)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.target.feature_permissions.filter(code=self.code).exists()
        )
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_a)
        )

    def test_a_grant_issued_at_one_school_is_not_held_at_another(self) -> None:
        self._grant_via_console([self.code], self.school_a)
        self.assertFalse(
            self.target.has_feature_permission(self.code, school=self.school_b)
        )

    def test_the_resolver_behind_require_permission_agrees(self) -> None:
        """``user_has_permission`` is what ``@require_permission`` calls.

        ``allow_admin=False`` isolates the code check: the target holds an ADMIN
        membership at School A, and the additive admin leg would otherwise let
        the assertion pass without the grant being consulted at all.
        """
        from apps.accounts.decorators import user_has_permission

        self._grant_via_console([self.code], self.school_a)
        self.assertTrue(
            user_has_permission(
                self.target, self.school_a, (self.code,), allow_admin=False
            )
        )
        self.assertFalse(
            user_has_permission(
                self.target, self.school_b, (self.code,), allow_admin=False
            )
        )

    def test_a_legacy_unscoped_grant_still_applies_everywhere(self) -> None:
        """Rows written before scoping existed keep the meaning they were given.

        Nothing in this codebase recorded which school a direct grant was for, so
        narrowing every existing row would silently revoke access the platform had
        already handed out.
        """
        self.target.feature_permissions.add(self.perm)
        self.assertFalse(
            FeaturePermissionScope.objects.filter(user=self.target).exists()
        )
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_a)
        )
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_b)
        )

    def test_school_none_keeps_the_unscoped_answer(self) -> None:
        self._grant_via_console([self.code], self.school_a)
        self.assertTrue(self.target.has_feature_permission(self.code))

    def test_the_console_revokes_only_what_it_issued(self) -> None:
        self._grant_via_console([self.code, self.other_code], self.school_a)
        self._grant_via_console([self.code], self.school_a)
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_a)
        )
        self.assertFalse(
            self.target.has_feature_permission(self.other_code, school=self.school_a)
        )
        self.assertFalse(
            self.target.feature_permissions.filter(code=self.other_code).exists()
        )

    def test_two_schools_can_hold_the_same_code_independently(self) -> None:
        self._grant_via_console([self.code], self.school_a)
        self._grant_via_console([self.code], self.school_b)
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_a)
        )
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_b)
        )
        # And revoking at B must not revoke at A.
        self._grant_via_console([], self.school_b)
        self.assertTrue(
            self.target.has_feature_permission(self.code, school=self.school_a)
        )
        self.assertFalse(
            self.target.has_feature_permission(self.code, school=self.school_b)
        )
