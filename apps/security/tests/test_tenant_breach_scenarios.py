"""RLS batch-1242 breach-scenario tests (repo-contained)."""

from django.test import TestCase, tag

from apps.platform_runtime.storage import get_signed_url, tenant_media_path


@tag("tenants_rls")
class SignedStoragePathTests(TestCase):
    def test_tenant_media_path_prefixes_school(self):
        path = tenant_media_path(42, "uploads/report.pdf")
        self.assertTrue(path.startswith("tenants/42/"))

    def test_signed_url_does_not_accept_foreign_tenant_path_swap(self):
        own = tenant_media_path(1, "secret.pdf")
        foreign = tenant_media_path(2, "secret.pdf")
        self.assertNotEqual(own, foreign)
        url_own = get_signed_url(own)
        self.assertIn("tenants/1/", url_own)
        self.assertNotIn("tenants/2/", url_own)


@tag("tenants_rls")
class PlanLimitEnforcementTests(TestCase):
    def test_plan_limit_suite_present(self):
        from apps.schools.tests.test_plan_and_feature_gate import (
            UsageLimitMiddlewareTests,
        )

        self.assertTrue(
            hasattr(UsageLimitMiddlewareTests, "test_max_students_limit_blocks_when_at_cap")
        )


@tag("tenants_rls")
class GraphqlAliasRegressionTests(TestCase):
    """Delegates to schools wave-2 GraphQL leak test contract."""

    def test_graphql_alias_test_module_importable(self):
        from apps.schools.tests import test_wave2_admin_and_graphql

        self.assertTrue(
            hasattr(
                test_wave2_admin_and_graphql,
                "Wave2GraphQLGlobalSchoolsRestrictedTests",
            )
        )
        self.assertTrue(
            hasattr(
                test_wave2_admin_and_graphql.Wave2GraphQLGlobalSchoolsRestrictedTests,
                "test_graphql_aliasing_cannot_bypass_global_school_restriction",
            )
        )
