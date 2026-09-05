"""Prove the RLS migration did what it says, on the substrate where it acts.

``people/0079`` is a no-op on SQLite and under schema-per-tenant, which means the
suite the repo normally runs cannot tell anyone whether it works. A migration
that silently does nothing and a migration that works look identical from a green
SQLite run, so these assertions ask PostgreSQL's own catalogs instead of trusting
that the RunPython body was reached.

FORCE gets its own assertion because it is the half that is easy to omit and
impossible to notice: PostgreSQL exempts a table's OWNER from its own policies,
Django connects as the owner, and so an ENABLEd but un-FORCEd table has a policy
that is decorative on the only connection the application ever uses. The repo has
been here before -- 198 tables carried policies that did not bind.
"""

from unittest import skipUnless

from django.db import connection
from django.test import TestCase

from apps.schools.rls import should_apply_rls

TABLE = "people_provisioningrequest"
POLICY = "people_rls_provisioningrequest"


@skipUnless(
    should_apply_rls(connection),
    "row-level security does not apply here (SQLite, or schema-per-tenant where "
    "isolation comes from the schema instead)",
)
class TheQueueTableIsActuallyBoundTests(TestCase):
    def test_the_table_exists_at_all(self):
        """Guard the guard: a typo'd table name would make every query below empty."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_class WHERE relname = %s", [TABLE]
            )
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_row_level_security_is_enabled_and_forced(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = %s",
                [TABLE],
            )
            enabled, forced = cursor.fetchone()
        self.assertTrue(enabled, "RLS is not enabled on %s" % TABLE)
        self.assertTrue(
            forced,
            "RLS is enabled but not FORCEd: Django connects as the table owner, "
            "and PostgreSQL exempts the owner from its own policies, so this "
            "policy would not bind on the only connection that matters",
        )

    def test_the_policy_is_present_and_covers_every_command(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT policyname, cmd, qual, with_check FROM pg_policies "
                "WHERE tablename = %s",
                [TABLE],
            )
            rows = cursor.fetchall()
        names = [r[0] for r in rows]
        self.assertIn(POLICY, names, "policy missing; found %r" % (names,))
        policy = next(r for r in rows if r[0] == POLICY)
        self.assertEqual(policy[1], "ALL", "policy must cover every command")
        self.assertIsNotNone(policy[3], "a policy with no WITH CHECK allows writes")
        for clause in (policy[2], policy[3]):
            self.assertIn("app.current_school_id", clause)
