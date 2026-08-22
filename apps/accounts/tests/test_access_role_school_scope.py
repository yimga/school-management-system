"""AccessRole school FK — catalog isolation with global template inheritance."""

from __future__ import annotations

import uuid

from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import IntegrityError
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.access_roles import role_applies_to_school, roles_queryset_for_school
from apps.accounts.models import AccessRole, Permission, User
from apps.schools.models import School, SchoolMembership


class AccessRoleSchoolScopeTests(TestCase):
    def setUp(self) -> None:
        self.school_a = School.objects.create(
            name="Scope A",
            slug=f"sca-{uuid.uuid4().hex[:10]}",
            subdomain=f"sca-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Scope B",
            slug=f"scb-{uuid.uuid4().hex[:10]}",
            subdomain=f"scb-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.global_role = AccessRole.objects.create(
            code="global_template",
            name="Global template",
            school=None,
        )
        self.role_a = AccessRole.objects.create(
            code="local_only",
            name="School A local",
            school=self.school_a,
        )
        self.role_b = AccessRole.objects.create(
            code="local_only",
            name="School B local",
            school=self.school_b,
        )

    def test_roles_queryset_includes_global_and_tenant(self) -> None:
        qs = roles_queryset_for_school(self.school_a)
        codes = set(qs.values_list("code", flat=True))
        self.assertIn("global_template", codes)
        self.assertIn("local_only", codes)
        self.assertEqual(qs.filter(school=self.school_b).count(), 0)

    def test_role_applies_to_school(self) -> None:
        self.assertTrue(role_applies_to_school(self.global_role, self.school_a))
        self.assertTrue(role_applies_to_school(self.role_a, self.school_a))
        self.assertFalse(role_applies_to_school(self.role_a, self.school_b))

    def test_duplicate_code_per_school_allowed(self) -> None:
        self.assertEqual(
            AccessRole.objects.filter(code="local_only").count(),
            2,
        )

    def test_global_code_unique(self) -> None:
        with self.assertRaises(IntegrityError):
            AccessRole.objects.create(
                code="global_template",
                name="Duplicate global",
                school=None,
            )

    def test_has_feature_permission_respects_school_scoped_role(self) -> None:
        perm = Permission.objects.create(code="reports.view", name="View reports")
        self.role_a.permissions.add(perm)
        user = User.objects.create_user(
            username=f"scoped-{uuid.uuid4().hex[:6]}",
            email="scoped@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        user.roles.add(self.role_a)
        self.assertTrue(user.has_feature_permission("reports.view", school=self.school_a))
        self.assertFalse(user.has_feature_permission("reports.view", school=self.school_b))


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="off")
class GlobalRoleTemplateIsNotEditableFromATenantTests(TestCase):
    """A tenant admin must not be able to rewrite a PLATFORM-GLOBAL role template.

    ``roles_queryset_for_school`` includes the global templates (school IS NULL)
    on purpose -- they are assignable at every school, and every caller that
    populates a choice field wants exactly that. The RBAC dashboard's
    ``edit_role`` branch used the same queryset as its MUTATION target, and
    ``EditRoleForm.role_id`` is a bare ``IntegerField`` in a ``HiddenInput`` --
    a widget, not a control. So any tenant admin holding ``settings.manage``
    could POST a global template's pk and rewrite the permission set of a row
    every school on the platform inherits.

    Uses RequestFactory and calls the view directly, matching
    test_control_plane_boundaries.py: the tenant MFA middleware otherwise
    redirects a privileged view to /mfa/setup/ and the assertion becomes vacuous.
    """

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant One",
            slug=f"t1-{uuid.uuid4().hex[:10]}",
            subdomain=f"t1-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.kept = Permission.objects.create(
            code="reports.view", name="View reports"
        )
        self.injected = Permission.objects.create(
            code="finance.manage", name="Manage finance"
        )
        self.global_role = AccessRole.objects.create(
            code="platform_template", name="Platform template", school=None
        )
        self.global_role.permissions.add(self.kept)
        self.local_role = AccessRole.objects.create(
            code="local_role", name="Local role", school=self.school
        )
        self.admin = User.objects.create_user(
            username=f"ta-{uuid.uuid4().hex[:6]}",
            email="ta@example.com",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def _edit_role_post(self, role_id):
        request = self.factory.post(
            "/rbac/",
            {
                "form_type": "edit_role",
                "role_id": str(role_id),
                "description": "pwned",
                "permissions": [str(self.injected.pk)],
            },
        )
        request.user = self.admin
        request.school = self.school
        request.public_host_kind = "tenant"
        # The view uses django.contrib.messages; RequestFactory has no middleware.
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_posting_a_global_template_id_does_not_mutate_it(self) -> None:
        from apps.accounts.views import rbac_dashboard

        with self.assertRaises(Http404):
            rbac_dashboard(self._edit_role_post(self.global_role.pk))

        self.global_role.refresh_from_db()
        self.assertEqual(self.global_role.name, "Platform template")
        self.assertNotEqual(self.global_role.description, "pwned")
        codes = set(self.global_role.permissions.values_list("code", flat=True))
        self.assertEqual(codes, {"reports.view"})
        self.assertNotIn("finance.manage", codes)

    def test_the_tenants_own_role_is_still_editable(self) -> None:
        # The fix must not break the feature it guards.
        from apps.accounts.views import rbac_dashboard

        rbac_dashboard(self._edit_role_post(self.local_role.pk))

        self.local_role.refresh_from_db()
        self.assertEqual(self.local_role.description, "pwned")
        self.assertEqual(
            set(self.local_role.permissions.values_list("code", flat=True)),
            {"finance.manage"},
        )
