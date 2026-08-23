"""Every tenant-scoped feedback table must be RLS-enabled, policied and FORCE'd.

``feedback/0008`` + ``0009`` enumerate only the eight models that carry a literal
``school`` FK. ``FeedbackComment``, ``FeedbackAttachment`` and
``FeedbackTriageEvent`` hold tenant data too — internal triage notes and every
attachment's storage path — but reach their school through a parent FK, so they
were in neither list.

``scripts/scan_rls_table_coverage.py`` skips any model without a ``school``
field, so its zero-finding baseline could never see this class of table. This
test is the app-side gate for it: it derives the tenant-scoped set from the
models themselves and checks it against what the migrations actually cover.

Scope note: a model counts as tenant-scoped here when it carries a ``school`` FK
OR a concrete FK to another *feedback* model that carries one. Cross-app parents
(e.g. ``portal.KBArticle``) are deliberately out of scope — this gate is about
feedback's own child tables, not about re-deciding another app's ownership.

RLS is PostgreSQL-only (``should_apply_rls``), and the suite runs on SQLite, so
this is a static/structural check. It does NOT prove the policies behave
correctly on a live Postgres connection.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from django.apps import apps as django_apps
from django.test import SimpleTestCase

MIGRATIONS_PACKAGE = "apps.feedback.migrations"


def _feedback_models():
    return list(django_apps.get_app_config("feedback").get_models())


def _has_school_field(model) -> bool:
    return any(getattr(f, "name", "") == "school" for f in model._meta.get_fields())


def tenant_scoped_feedback_tables() -> set[str]:
    """db_tables that hold per-school data, directly or through a feedback parent."""
    models = _feedback_models()
    direct = {m for m in models if _has_school_field(m)}
    tables = {m._meta.db_table for m in direct}
    for model in models:
        if model in direct:
            continue
        for field in model._meta.get_fields():
            if not (getattr(field, "many_to_one", False) and field.concrete):
                continue
            parent = field.remote_field.model
            if parent in direct:
                tables.add(model._meta.db_table)
                break
    return tables


def _migration_modules():
    package = importlib.import_module(MIGRATIONS_PACKAGE)
    for info in pkgutil.iter_modules(package.__path__):
        yield importlib.import_module(f"{MIGRATIONS_PACKAGE}.{info.name}")


def _rls_migration_sources() -> dict[str, str]:
    """Source text of every feedback migration that touches row level security."""
    sources = {}
    for module in _migration_modules():
        try:
            source = inspect.getsource(module)
        except OSError:  # pragma: no cover - compiled-only module
            continue
        if "ROW LEVEL SECURITY" in source or "CREATE POLICY" in source:
            sources[module.__name__] = source
    return sources


class FeedbackRlsCoverageTests(SimpleTestCase):
    def test_every_tenant_scoped_table_is_named_by_an_rls_migration(self):
        expected = tenant_scoped_feedback_tables()
        # Anti-vacuity: if the derivation returns nothing the assertions below
        # are trivially true, so pin the known child tables explicitly.
        self.assertTrue(expected, "tenant-scoped table derivation produced nothing")
        for table in (
            "feedback_feedbackcomment",
            "feedback_feedbackattachment",
            "feedback_feedbacktriageevent",
        ):
            self.assertIn(table, expected, "derivation missed a known child table")

        sources = _rls_migration_sources()
        self.assertTrue(sources, "no RLS migrations found in apps/feedback")
        blob = "\n".join(sources.values())
        uncovered = sorted(t for t in expected if t not in blob)
        self.assertEqual(
            uncovered,
            [],
            f"tenant-scoped feedback tables with no RLS migration: {uncovered}",
        )

    def test_fk_scoped_children_are_enabled_policied_and_forced(self):
        """Listing a table is not enough — ENABLE without FORCE exempts the owner."""
        children = (
            "feedback_feedbackcomment",
            "feedback_feedbackattachment",
            "feedback_feedbacktriageevent",
        )
        sources = _rls_migration_sources()
        for table in children:
            owning = [s for s in sources.values() if table in s]
            self.assertTrue(owning, f"{table} is named by no RLS migration")
            source = "\n".join(owning)
            self.assertIn(
                "ENABLE ROW LEVEL SECURITY", source, f"{table}: RLS never enabled"
            )
            self.assertIn("CREATE POLICY", source, f"{table}: no policy created")
            self.assertIn(
                "FORCE ROW LEVEL SECURITY",
                source,
                f"{table}: policy not FORCE'd, so the table owner (the role Django "
                "runs as in RLS mode) still bypasses it",
            )

    def test_child_policies_resolve_the_school_through_the_parent(self):
        """A child table has no school_id; its USING clause must join the parent."""
        sources = _rls_migration_sources()
        child_sources = "\n".join(
            s
            for s in sources.values()
            if "feedback_feedbackcomment" in s or "feedback_feedbackattachment" in s
        )
        self.assertIn("feedback_feedbacksubmission", child_sources)
        self.assertIn("app.current_school_id", child_sources)
        self.assertIn("app.rls_bypass", child_sources)
