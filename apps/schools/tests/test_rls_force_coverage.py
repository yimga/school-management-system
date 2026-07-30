"""Must-fire RLS FORCE coverage: no RLS-enabled + policied table may be left
un-FORCE'd.

Without FORCE ROW LEVEL SECURITY, the Postgres table owner (the role Django runs
as in CI, managed prod, and most local setups) bypasses every RLS policy -- so a
default-deny policy that is not FORCE'd binds "for everyone except the owner --
i.e. for nobody". This test walks pg_catalog and asserts every tenant table that
is RLS-enabled AND carries at least one policy is also FORCE'd. It fails loudly
the instant an app enables + policies a table without forcing it (the gap that
schools/0083_force_rls_late_enabled_tables closed for ~75 tables across 11 apps).

Requires PostgreSQL and USE_DJANGO_TENANTS=False. Tag: tenants_rls.
"""

import unittest

from django.db import connection
from django.test import TestCase, override_settings, tag


@tag("tenants_rls")
@unittest.skipIf(
    connection.vendor != "postgresql", "RLS FORCE coverage requires PostgreSQL"
)
@override_settings(USE_DJANGO_TENANTS=False)
class RlsForceCoverageTests(TestCase):
    def test_no_enabled_policied_table_is_unforced(self):
        """Every RLS-enabled table with a policy must also be FORCE'd, or the
        policy does not bind for the owner connection."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'r'
                  AND n.nspname = current_schema()
                  AND c.relrowsecurity = TRUE
                  AND c.relforcerowsecurity = FALSE
                  AND EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid)
                ORDER BY c.relname
                """
            )
            unforced = [row[0] for row in cursor.fetchall()]

        self.assertEqual(
            unforced,
            [],
            "RLS-enabled + policied tables are NOT FORCE'd, so their tenant "
            "policies do not bind for the owner connection (cross-tenant read "
            f"leak in RLS mode): {unforced}. Add a FORCE sweep (see "
            "schools/0083_force_rls_late_enabled_tables) or FORCE them in the "
            "app's own RLS migration.",
        )
