from django.test import SimpleTestCase

from apps.siteconfig.db_router import TenantDatabaseRouter


class TenantDatabaseRouterTests(SimpleTestCase):
    def test_allow_migrate_defers_to_downstream_routers(self):
        router = TenantDatabaseRouter()

        self.assertIsNone(router.allow_migrate("default", "communication", "outboundmessagequeue"))
        self.assertIsNone(router.allow_migrate("default", "siteconfig", "sitesettings"))
