from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, resolve, reverse

from apps.accounts.models import User
from apps.accounts.decorators import permission_required
from apps.accounts.permissions import can_access_module
from apps.schools.models import School, SchoolMembership
from apps.academics.models_tenant_runtime import ReportCardStyleAssignment
from apps.global_registries.models import HolidayCalendar
from apps.siteconfig import models as _siteconfig_models
from config.admin import platform_admin_site, tenant_admin_site

_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")
from config.schema import schema


class ControlPlaneBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superadmin = User.objects.create_user(
            username="cp_superadmin",
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=False,
        )
        self.tenant_admin = User.objects.create_user(
            username="tenant_admin_boundary",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=False,
        )

    def test_superadmin_role_includes_default_module_access(self):
        # SUPERADMIN is part of module role defaults in permissions.py.
        self.assertTrue(can_access_module(self.superadmin, "finance", action="read"))
        self.assertTrue(can_access_module(self.superadmin, "portal", action="write"))

    def test_global_school_registry_is_control_plane_only(self):
        query = "query { schoolCount schools { slug } }"

        manager_request = self.factory.post(
            "/graphql/", data={"query": query}, content_type="application/json"
        )
        manager_request.user = self.superadmin
        manager_request.public_host_kind = "manager"
        manager_result = schema.execute(query, context_value=manager_request)
        self.assertIn("schoolCount", manager_result.data)
        self.assertIn("schools", manager_result.data)

        tenant_request = self.factory.post(
            "/graphql/", data={"query": query}, content_type="application/json"
        )
        tenant_request.user = self.tenant_admin
        tenant_request.public_host_kind = "tenant"
        tenant_result = schema.execute(query, context_value=tenant_request)
        self.assertIsNone(tenant_result.data["schoolCount"])
        self.assertEqual(tenant_result.data["schools"], [])


class AdminRegistryBoundaryTests(SimpleTestCase):
    """Assert platform and tenant admin have separate registries and correct model assignment."""

    def test_platform_and_tenant_registries_are_separate(self):
        self.assertIsNot(platform_admin_site._registry, tenant_admin_site._registry)

    def test_user_model_registered_on_both_admin_sites(self):
        """Operators edit Users on manager /admin/ (platform) and school /admin/ (tenant)."""
        self.assertIn(User, tenant_admin_site._registry)
        self.assertIn(User, platform_admin_site._registry)

    def test_platform_only_model_in_platform_admin_not_in_tenant_admin(self):
        self.assertIn(School, platform_admin_site._registry)
        self.assertNotIn(School, tenant_admin_site._registry)

    def test_tenant_runtime_models_do_not_leak_into_platform_admin(self):
        self.assertIn(ReportCardStyleAssignment, tenant_admin_site._registry)
        self.assertIn(HolidayCalendar, tenant_admin_site._registry)
        self.assertNotIn(ReportCardStyleAssignment, platform_admin_site._registry)
        self.assertNotIn(HolidayCalendar, platform_admin_site._registry)

    def test_site_settings_tenant_admin_only_platform_uses_super(self):
        """Tenant site-settings row CRUD on tenant /admin/ only; manager uses super:site_settings_*."""
        self.assertIn(_TenantSettingsModel, tenant_admin_site._registry)
        self.assertNotIn(_TenantSettingsModel, platform_admin_site._registry)

    def test_metadata_dynamic_field_models_on_tenant_admin_site(self):
        """Batch 14 Phase 5: canonical DynamicField* CRUD is on tenant metadata admin."""
        from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue

        self.assertIn(DynamicFieldDefinition, tenant_admin_site._registry)
        self.assertIn(DynamicFieldValue, tenant_admin_site._registry)


class TenantAdminAccessBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Admin School",
            slug="tenant-admin-school",
            subdomain="tenant-admin-school",
            is_active=True,
        )

    def _request_for(self, user, *, host_kind="tenant", school=None):
        request = self.factory.get("/admin/")
        request.user = user
        request.public_host_kind = host_kind
        request.school = school if school is not None else self.school
        return request

    def test_tenant_role_admin_without_django_staff_can_open_tenant_admin(self):
        user = User.objects.create_user(
            username="tenant_role_admin",
            password="testpass123",
            role=User.Role.ADMIN,
            is_staff=False,
            is_superuser=False,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

        self.assertTrue(tenant_admin_site.has_permission(self._request_for(user)))

    def test_tenant_school_owner_without_django_staff_can_open_tenant_admin(self):
        user = User.objects.create_user(
            username="tenant_owner_admin",
            password="testpass123",
            role=User.Role.TEACHER,
            is_staff=False,
            is_superuser=False,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.TEACHER,
            is_school_owner=True,
        )

        self.assertTrue(tenant_admin_site.has_permission(self._request_for(user)))

    def test_tenant_admin_site_does_not_open_on_manager_host(self):
        user = User.objects.create_user(
            username="tenant_admin_on_manager",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.ADMIN,
        )

        self.assertFalse(
            tenant_admin_site.has_permission(
                self._request_for(user, host_kind="manager")
            )
        )

    def test_resolved_school_prevents_tenant_admin_from_being_classified_as_platform(self):
        user = User.objects.create_user(
            username="tenant_admin_without_host_kind",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.ADMIN,
        )
        request = self._request_for(user)
        request.public_host_kind = None

        self.assertTrue(tenant_admin_site.has_permission(request))

    def test_tenant_admin_denies_suspended_owner_and_non_admin_member(self):
        owner = User.objects.create_user(
            username="suspended_tenant_owner",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        teacher = User.objects.create_user(
            username="tenant_teacher_staff",
            password="testpass123",
            role=User.Role.TEACHER,
            is_staff=True,
        )
        from django.utils import timezone

        SchoolMembership.objects.create(
            user=owner,
            school=self.school,
            role=User.Role.ADMIN,
            is_school_owner=True,
            suspended_at=timezone.now(),
        )
        SchoolMembership.objects.create(
            user=teacher,
            school=self.school,
            role=User.Role.TEACHER,
        )

        self.assertFalse(tenant_admin_site.has_permission(self._request_for(owner)))
        self.assertFalse(tenant_admin_site.has_permission(self._request_for(teacher)))

    def test_tenant_admin_site_uses_tenant_login_form_and_template(self):
        from django.contrib.auth.forms import AuthenticationForm

        self.assertIs(tenant_admin_site.login_form, AuthenticationForm)
        self.assertEqual(tenant_admin_site.login_template, "auth/tenant_admin_login.html")
        self.assertEqual(platform_admin_site.login_template, "auth/admin_login.html")

    @override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="example.com")
    def test_root_admin_dispatch_fails_closed_for_unresolved_tenant_host(self):
        from config.urls import admin_host_dispatch

        request = self.factory.get("/admin/", HTTP_HOST="missing.example.com")
        request.public_host_kind = None
        request.user = self.tenant_admin = User.objects.create_user(
            username="unresolved_tenant_admin",
            password="testpass123",
            role=User.Role.ADMIN,
        )

        response = admin_host_dispatch(request)

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"resolved tenant", response.content)


class TenantConfigurationPermissionDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Config School",
            slug="tenant-config-school",
            subdomain="tenant-config-school",
            is_active=True,
        )

    def _request_for(self, user):
        request = self.factory.get("/siteconfig/reports/builder/")
        request.user = user
        request.school = self.school
        request.public_host_kind = "tenant"
        return request

    def test_admin_like_scalar_role_can_enter_tenant_settings_without_explicit_feature_grant(self):
        user = User.objects.create_user(
            username="tenant_config_scalar_admin",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.ADMIN,
        )

        @permission_required("settings.manage", raise_exception=True)
        def protected_view(request):
            return HttpResponse("ok")

        response = protected_view(self._request_for(user))
        self.assertEqual(response.status_code, 200)

    def test_school_owner_can_enter_tenant_settings_without_explicit_feature_grant(self):
        user = User.objects.create_user(
            username="tenant_config_owner",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.TEACHER,
            is_school_owner=True,
        )

        @permission_required("settings.manage", raise_exception=True)
        def protected_view(request):
            return HttpResponse("ok")

        response = protected_view(self._request_for(user))
        self.assertEqual(response.status_code, 200)

    def test_non_admin_member_still_cannot_enter_tenant_settings(self):
        user = User.objects.create_user(
            username="tenant_config_teacher",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=user,
            school=self.school,
            role=User.Role.TEACHER,
        )

        @permission_required("settings.manage", raise_exception=True)
        def protected_view(request):
            return HttpResponse("ok")

        response = protected_view(self._request_for(user))
        self.assertEqual(response.status_code, 403)


class AdminPlaneUrlConfTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_urlconf_uses_platform_admin_site_without_tenant_namespaces(self):
        match = resolve("/admin/")
        self.assertIs(match.func.admin_site, platform_admin_site)
        with self.assertRaises(NoReverseMatch):
            reverse("portal:parent_dashboard")
        self.assertTrue(reverse("kb:kb_home").startswith("/kb/"))

    @override_settings(ROOT_URLCONF="config.tenant_urls")
    def test_tenant_urlconf_uses_tenant_admin_site_with_tenant_namespaces(self):
        match = resolve("/admin/")
        self.assertIs(match.func.admin_site, tenant_admin_site)
        self.assertTrue(reverse("portal:parent_dashboard").startswith("/portal/"))
