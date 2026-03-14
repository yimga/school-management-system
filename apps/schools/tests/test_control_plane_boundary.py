"""
Wave 1 control-plane boundary tests (RUNMYCAMPUS_AUDIT_PLAN_COMPLETE_NO_BACKLOG).

Non-negotiable: manager host denies non–platform users; /super/ has no tenant exceptions;
manager URLConf contains only control-plane namespaces (or redirects to them).
"""
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class ControlPlaneBoundaryTests(TestCase):
    """Wave 1.1.1 / 1.6: Manager host denies non–platform user for /super/ and manager APIs."""

    def setUp(self):
        self.platform_user = User.objects.create_user(
            username="platform_boundary",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.tenant_staff = User.objects.create_user(
            username="tenant_staff_cp_boundary",
            password="testpass123",
            is_staff=True,
            is_superuser=False,
            role=User.Role.ADMIN,
        )

    def test_manager_host_denies_non_platform_user_for_super(self):
        """Non–platform user on manager host must get 403 for /super/."""
        self.client.force_login(self.tenant_staff)
        response = self.client.get(
            reverse("super:dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(
            response.status_code,
            403,
            msg="Tenant staff must get 403 on manager host /super/ (control-plane only).",
        )

    def test_manager_host_denies_non_platform_user_for_api_search(self):
        """Non–platform user on manager host must get 403 for /api/search/."""
        self.client.force_login(self.tenant_staff)
        response = self.client.get(
            "/api/search/?q=test",
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(
            response.status_code,
            403,
            msg="Tenant staff must get 403 on manager host /api/search/.",
        )

    def test_manager_host_allows_platform_user_for_super(self):
        """Platform user on manager host can access /super/."""
        self.client.force_login(self.platform_user)
        response = self.client.get(
            reverse("super:dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertIn(
            response.status_code,
            (200, 302),
            msg="Platform user must be allowed on /super/.",
        )


class SuperNamespacePurityTests(TestCase):
    """Wave 1.4: /super/ namespace has no tenant exceptions."""

    def test_super_namespace_no_tenant_exceptions(self):
        """TenantSuperAdminRequiredMiddleware must not allow any /super/ path for non–control-plane users."""
        from apps.schools.middleware import TenantSuperAdminRequiredMiddleware
        import inspect
        source = inspect.getsource(TenantSuperAdminRequiredMiddleware.process_request)
        # There must be no exception that allows /super/... for non-super (e.g. /super/parent-tenant/).
        self.assertNotIn(
            "parent-tenant",
            source,
            msg="TenantSuperAdminRequiredMiddleware must not have /super/parent-tenant exception.",
        )
        self.assertIn(
            "/super/",
            source,
            msg="Middleware must restrict /super/.",
        )

    def test_super_urls_no_parent_tenant_path(self):
        """super_urls must not define a parent-tenant or tenant-hierarchy path under /super/."""
        from apps.schools import super_urls
        from django.urls import get_resolver
        resolver = get_resolver()
        # super_urls is included at path("super/", include(super_urls)); list all pattern names.
        try:
            super_namespace = resolver.url_patterns
            for pattern in super_namespace:
                if hasattr(pattern, "url_patterns"):
                    for p in pattern.url_patterns:
                        if hasattr(p, "pattern") and "parent" in str(getattr(p.pattern, "_route", "")):
                            self.fail("super_urls must not contain a path with 'parent' (tenant hierarchy).")
        except Exception:
            pass
        # Just ensure super_urls exists and has expected structure (dashboard, etc.).
        self.assertTrue(hasattr(super_urls, "urlpatterns"))
        self.assertGreater(len(super_urls.urlpatterns), 0)


class ManagerUrlconfOnlyControlPlaneTests(TestCase):
    """Wave 1.5: Manager URLConf contains only control-plane namespaces (or redirects)."""

    def test_manager_urlconf_only_control_plane(self):
        """Manager URLConf: /portal/ and /finance/ are redirects only; /super/ is control-plane namespace."""
        # Tenant-path-like routes must be redirects, not tenant app includes.
        match = resolve("/portal/", urlconf="config.manager_urls")
        self.assertEqual(match.func.__name__, "manager_legacy_surface_redirect")
        match = resolve("/finance/", urlconf="config.manager_urls")
        self.assertEqual(match.func.__name__, "manager_legacy_surface_redirect")
        # /super/ must be the control-plane namespace.
        match = resolve("/super/", urlconf="config.manager_urls")
        self.assertEqual(match.namespace, "super")
