"""An RLS policy on a NULLABLE school FK must carry the ``school_id IS NULL`` arm.

``policies/0009_rls_policy_default_deny.py`` applied ONE clause to all six tables::

    current_setting('app.rls_bypass', true) = 'on'
    OR (current_setting('app.current_school_id', true) IS NOT NULL
        AND school_id::text = current_setting('app.current_school_id', true))

Three of those six are hybrid platform-or-tenant: ``policies_policyrule``
("Null => platform-wide rule applied to every tenant"), ``policies_policybundle``
("Null = platform/country-level bundle") and ``policies_policydecisionlog``
(``school`` is ``null=True, SET_NULL``). For a row with ``school_id`` NULL,
``NULL::text = '42'`` evaluates to NULL, so USING is false and the row is INVISIBLE.

In RLS mode (``USE_DJANGO_TENANTS=0`` on PostgreSQL) that hides the three baseline
allow-rules migration 0010 seeds with ``school=None`` -- and ``pdp._applicable_rules``
is built entirely around ``Q(school__isnull=True) | Q(school=school)``, so every
``pdp_enforce`` surface would fall through to implicit_deny. Every
``decide(school=None)`` log INSERT would additionally violate the WITH CHECK (42501).

The peers already knew the shape: ``siteconfig/0129`` defines a separate ``USING_FT``
for its one hybrid table and ``metadata/0012`` leads with ``school_id IS NULL OR ...``.

This test is source-level on purpose. ``should_apply_rls`` is False on SQLite (and
under django-tenants), so the local suite can never execute these policies -- the
invariant that CAN be checked everywhere is that the clause shape matches the
model's own nullability, derived from the live model registry rather than a list.
"""

from __future__ import annotations

import importlib
import pkgutil

from django.apps import apps as django_apps
from django.test import SimpleTestCase

NULL_ARM = "school_id IS NULL"


def _tables_by_nullability() -> tuple[set[str], set[str]]:
    """(nullable, strict) db_table names for policies models carrying a school FK."""
    nullable, strict = set(), set()
    for model in django_apps.get_app_config("policies").get_models():
        try:
            field = model._meta.get_field("school")
        except Exception:  # noqa: BLE001 - model simply has no school FK
            continue
        if not getattr(field, "is_relation", False):
            continue
        (nullable if field.null else strict).add(model._meta.db_table)
    return nullable, strict


def _winning_clauses() -> dict[str, str]:
    """table -> USING clause from the LAST policies migration that creates its policy.

    Two module shapes are understood: an explicit ``POLICY_CLAUSES`` mapping (used
    when a migration applies different clauses to different tables), and the older
    ``TABLES`` + ``USING_CLAUSE`` pair that applies one clause to every table it names.
    Migrations that only ENABLE row security (no CREATE POLICY) expose neither.
    """
    package = importlib.import_module("apps.policies.migrations")
    clauses: dict[str, str] = {}
    for _finder, name, _ispkg in sorted(
        pkgutil.iter_modules(package.__path__), key=lambda m: m[1]
    ):
        module = importlib.import_module(f"apps.policies.migrations.{name}")
        explicit = getattr(module, "POLICY_CLAUSES", None)
        if isinstance(explicit, dict):
            clauses.update(explicit)
            continue
        tables = getattr(module, "TABLES", None)
        using = getattr(module, "USING_CLAUSE", None)
        if tables and isinstance(using, str):
            for table in tables:
                clauses[table] = using
    return clauses


class RlsClauseMatchesSchoolNullabilityTests(SimpleTestCase):
    def setUp(self) -> None:
        self.nullable, self.strict = _tables_by_nullability()
        self.clauses = _winning_clauses()
        # Non-vacuity: if the discovery helpers ever stop finding anything, every
        # assertion below would pass over an empty set.
        self.assertTrue(self.nullable, "no nullable-school policies table discovered")
        self.assertTrue(self.strict, "no strict-school policies table discovered")
        self.assertTrue(self.clauses, "no RLS policy clause discovered in migrations")

    def test_every_school_scoped_table_has_a_policy(self) -> None:
        missing = sorted((self.nullable | self.strict) - set(self.clauses))
        self.assertEqual(
            missing,
            [],
            f"policies tables with a school FK and no RLS policy: {missing}",
        )

    def test_nullable_school_tables_carry_the_null_arm(self) -> None:
        for table in sorted(self.nullable):
            with self.subTest(table=table):
                self.assertIn(
                    NULL_ARM,
                    self.clauses[table],
                    f"{table}.school is nullable, so its platform-scope rows are "
                    f"invisible under this clause: {self.clauses[table]}",
                )

    def test_strict_school_tables_do_not_get_the_null_arm(self) -> None:
        for table in sorted(self.strict):
            with self.subTest(table=table):
                self.assertNotIn(
                    NULL_ARM,
                    self.clauses[table],
                    f"{table}.school is NOT NULL -- the escape arm would only widen "
                    f"the policy for rows that cannot exist",
                )

    def test_every_clause_still_honours_bypass_and_tenant_match(self) -> None:
        """The NULL arm is an addition, never a replacement."""
        for table, clause in sorted(self.clauses.items()):
            with self.subTest(table=table):
                self.assertIn("app.rls_bypass", clause)
                self.assertIn(
                    "school_id::text = current_setting('app.current_school_id', true)",
                    clause,
                )
