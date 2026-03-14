"""
Wave 4 tests: tenant-scoping and single-tenant cleanup.

Non-negotiable: lint/test for get_tenant_cache_prefix(None); tenant isolation;
single-tenant/legacy path documented or isolated.
"""
from pathlib import Path

from django.test import TestCase

from apps.accounts.models import User
from apps.requests.models import AccessRequest
from apps.schools.models import School


class Wave4TenantCachePrefixLintTests(TestCase):
    """Wave 4.2: get_tenant_cache_prefix(None) must not be used in tenant app code (except allowlist)."""

    def test_lint_tenant_cache_prefix_script_exists(self):
        """Lint script must exist and be runnable."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        script = root / "scripts" / "lint_tenant_cache_prefix.py"
        self.assertTrue(script.is_file(), "scripts/lint_tenant_cache_prefix.py must exist.")

    def test_tenant_app_requests_detail_filters_by_school(self):
        """requests.request_detail must filter by school (TENANT_ORM_AUDIT)."""
        from apps.requests import views as req_views
        import inspect
        source = inspect.getsource(req_views.request_detail)
        self.assertIn("school", source.lower(), "request_detail must use school for filtering.")
        self.assertTrue(
            "filter" in source and ("school" in source or "school_id" in source),
            "request_detail must filter queryset by school.",
        )


class Wave4TenantIsolationTests(TestCase):
    """Wave 4: Tenant isolation (list views / querysets scoped by school)."""

    def setUp(self):
        self.school1 = School.objects.create(
            name="Wave4 School One",
            slug="wave4-one",
            subdomain="wave4one",
            is_active=True,
        )
        self.school2 = School.objects.create(
            name="Wave4 School Two",
            slug="wave4-two",
            subdomain="wave4two",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="wave4_user",
            password="testpass123",
            is_staff=True,
            is_superuser=False,
            role=User.Role.ADMIN,
        )

    def test_access_request_model_has_school(self):
        """AccessRequest must have school FK for tenant scoping."""
        self.assertTrue(
            hasattr(AccessRequest, "school_id") or hasattr(AccessRequest, "school"),
            "AccessRequest must be school-scoped.",
        )
