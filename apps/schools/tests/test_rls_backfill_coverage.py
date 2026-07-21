"""Must-fire guard on RLS coverage for tenant-scoped tables.

This is the test the platform did not have. The pre-existing protections were both
structurally incapable of catching the real defect:

* ``scan_rls_force_coverage.py`` asks whether an APP has both RLS migration FILES.
  Every app did, so it reported zero gaps while 123 tables had no RLS at all.
* Each app's ``*_enable_rls_postgresql.py`` freezes a literal ``TABLES = [...]`` at
  authoring time. A model that gains a ``school`` FK afterwards is never added, and
  nothing notices.

So a new tenant-scoped model shipped with no row-level security and every gate
stayed green. Under single-schema deployment (``USE_DJANGO_TENANTS=False``) RLS
*is* the tenant isolation, so that is a cross-tenant read waiting to happen.

These tests re-derive the truth from the model registry and compare it against the
literal. Adding a model with a ``school`` FK without regenerating the migration
(``python scripts/generate_rls_backfill_tables.py --write``) turns them red.

They run on SQLite: they assert the migration's CONTENT, not its SQL execution.
The SQL itself is a no-op off PostgreSQL and under schema-per-tenant, so asserting
on execution would produce a test that passes by doing nothing -- the failure mode
this whole program exists to remove.
"""

from __future__ import annotations

import ast
import pathlib
import sys

from django.apps import apps as django_apps
from django.test import SimpleTestCase

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT
    / "apps"
    / "schools"
    / "migrations"
    / "0081_rls_backfill_unenumerated_tenant_tables.py"
)


def _add_scripts_to_path() -> None:
    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def _migration_tables() -> list[str]:
    tree = ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "TABLES":
                return [
                    el.value
                    for el in node.value.elts
                    if isinstance(el, ast.Constant) and isinstance(el.value, str)
                ]
    raise AssertionError("The RLS backfill migration has no TABLES literal.")


def _enumerated_anywhere() -> set[str]:
    """Table literals across every app's RLS migrations.

    Delegates to the scanner rather than reimplementing it. An earlier version of
    this test hand-rolled the collection and only read list/tuple/set literals,
    which missed four tables enabled by an inline
    ``cursor.execute("ALTER TABLE x ENABLE ROW LEVEL SECURITY")`` string. A test
    that disagrees with the gate it guards is worse than no test, so there is
    exactly one implementation and both callers use it.
    """
    _add_scripts_to_path()
    from scan_rls_table_coverage import _enumerated_tables

    return _enumerated_tables()


def _tenant_scoped_tables() -> set[str]:
    """Distinct db_tables carrying a ``school`` FK column.

    Delegates to the generator so the test and the thing that writes the list can
    never disagree. The generator derives from MIGRATION STATE rather than the
    runtime app registry, which matters: ``get_app_configs()`` only sees models
    that have been imported, and Django's test discovery imports modules ordinary
    startup does not. An earlier version of this test walked the registry and its
    result depended on import order -- ``apps/portal/models_forums.py`` is pulled
    in by ``views_forums.py``, so those two school-scoped tables appeared or
    vanished depending on what ran first.
    """
    _add_scripts_to_path()
    from generate_rls_backfill_tables import tenant_scoped_tables

    return set(tenant_scoped_tables())


class RlsBackfillCoverageTests(SimpleTestCase):
    def test_every_tenant_scoped_table_is_enumerated_somewhere(self):
        """The defect itself: a school-FK table with no RLS enablement anywhere."""
        uncovered = sorted(_tenant_scoped_tables() - _enumerated_anywhere())
        self.assertEqual(
            uncovered,
            [],
            "These tables have a school FK but no RLS enablement in any migration. "
            "Run: python scripts/generate_rls_backfill_tables.py --write",
        )

    def test_backfill_list_has_no_stale_entries(self):
        """A table that stopped being tenant-scoped must leave the list."""
        stale = sorted(set(_migration_tables()) - _tenant_scoped_tables())
        self.assertEqual(
            stale,
            [],
            "These tables are enumerated for RLS but no longer carry a school FK. "
            "Run: python scripts/generate_rls_backfill_tables.py --write",
        )

    def test_every_backfilled_table_really_has_a_school_id_column(self):
        """Guards the reverse-relation trap.

        ``_meta.get_fields()`` returns reverse accessors too, so a naive walk can
        list a model whose only ``school`` is a reverse relation. That table has no
        ``school_id`` column, and the policy's ``school_id::text = ...`` predicate
        would fail at CREATE POLICY time -- during a migration, on deploy.
        """
        by_table: dict[str, list[str]] = {}
        for cfg in django_apps.get_app_configs():
            if not cfg.name.startswith("apps."):
                continue
            for model in cfg.get_models():
                by_table.setdefault(model._meta.db_table, []).append(
                    f"{cfg.label}.{model.__name__}"
                )

        without_column = []
        for table in _migration_tables():
            models = by_table.get(table, [])
            self.assertTrue(models, f"{table} is enumerated but no model owns it.")
            has_column = False
            for dotted in models:
                app_label, name = dotted.split(".")
                model = django_apps.get_model(app_label, name)
                try:
                    field = model._meta.get_field("school")
                except Exception:  # noqa: BLE001 - absent field is the thing we check
                    continue
                if getattr(field, "column", None) == "school_id":
                    has_column = True
                    break
            if not has_column:
                without_column.append(table)

        self.assertEqual(
            without_column,
            [],
            "Enumerated for RLS but carrying no school_id column; CREATE POLICY "
            "would fail on deploy.",
        )

    def test_policy_predicate_is_default_deny(self):
        """Absent tenant context must deny, not fall through to every row."""
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("app.current_school_id", source)
        self.assertIn("app.rls_bypass", source)
        self.assertIn("FORCE ROW LEVEL SECURITY", source)
        # A NULL tenant setting must not match. The permissive shape this platform
        # shipped earlier ("NULL OR match") is what default-deny replaced.
        self.assertIn(
            "current_setting('app.current_school_id', true) IS NOT NULL", source
        )
