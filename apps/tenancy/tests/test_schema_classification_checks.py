from django.test import SimpleTestCase, override_settings

from apps.tenancy.checks import tenancy_strategy_checks


class SchemaClassificationChecksTests(SimpleTestCase):
    @override_settings(
        USE_DJANGO_TENANTS=True,
        SHARED_APPS=["apps.accounts", "apps.portal"],
        TENANT_APPS=["apps.student360", "apps.communication"],
        MIDDLEWARE=["django_tenants.middleware.main.TenantMainMiddleware"],
        DATABASES={"default": {"ENGINE": "django_tenants.postgresql_backend"}},
        INSTALLED_APPS=["apps.accounts", "apps.portal", "apps.student360", "apps.communication"],
    )
    def test_tenant_only_apps_in_shared_apps_raise_error(self):
        errors = tenancy_strategy_checks(None)
        self.assertTrue(any(error.id == "tenancy.E005" for error in errors))

    @override_settings(
        USE_DJANGO_TENANTS=True,
        SHARED_APPS=["apps.accounts"],
        TENANT_APPS=["apps.communication"],
        MIDDLEWARE=["django_tenants.middleware.main.TenantMainMiddleware"],
        DATABASES={"default": {"ENGINE": "django_tenants.postgresql_backend"}},
        INSTALLED_APPS=["apps.accounts", "apps.communication"],
    )
    def test_missing_tenant_only_apps_raise_error(self):
        errors = tenancy_strategy_checks(None)
        self.assertTrue(any(error.id == "tenancy.E006" for error in errors))
