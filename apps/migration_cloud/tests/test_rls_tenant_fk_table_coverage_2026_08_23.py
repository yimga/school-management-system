"""Every migration_cloud table scoped by a School FK must be RLS-enumerated.

``scripts/scan_rls_table_coverage.py`` decides what is tenant-scoped with
``if "school" not in field_names: continue`` — a FIELD-NAME test. migration_cloud
scopes eight models by a FK NAMED ``tenant`` (or ``tenant_scope``) instead, so
the scanner never looks at them, reports 0 findings, and its zero-baseline gate
passes forever no matter how many such tables are added. The scanner also only
sees models registered by ``django.setup()``, which silently excludes
``GuardianConsentToken`` (its module is imported lazily by the views).

That matters in exactly one mode and it is the mode the scanner exists for:
``USE_DJANGO_TENANTS=0`` + PostgreSQL, the sovereign edge box, where RLS *is*
the isolation. Encrypted Companion bundle blobs, MAA agreements, webhook HMAC
secrets, guardian consent tokens and tenant-scoped API tokens had no row-level
isolation there at all.

This is the app-side gate: it detects tenant scoping by the FK's TARGET MODEL,
not by the field's name, so a new ``tenant``-scoped table cannot join the
uncovered set unnoticed. Fixing the central scanner (and regenerating its
baseline) is a scripts/ change and is reported separately.
"""

from __future__ import annotations

import ast
from pathlib import Path

from django.apps import apps as django_apps
from django.test import SimpleTestCase

import apps.migration_cloud.models_guardian_consent  # noqa: F401 — registers GuardianConsentToken
from apps.schools.models import School

APPS_ROOT = Path(__file__).resolve().parents[2]
_TABLE_ASSIGN_NAMES = frozenset({"TABLE", "TABLES", "_TABLE", "_TABLES"})


def _string_literals(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    found: set[str] = set()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for el in node.elts:
            found |= _string_literals(el)
    return found


def _enumerated_tables() -> set[str]:
    """Table names named by any app's ``*rls*`` migration — same union rule the
    central scanner uses (a table's RLS need not be declared by its own app)."""
    found: set[str] = set()
    for mig in sorted(APPS_ROOT.glob("*/migrations/*.py")):
        if "rls" not in mig.name:
            continue
        try:
            tree = ast.parse(mig.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                names = {t.id for t in node.targets if isinstance(t, ast.Name)}
                if names & _TABLE_ASSIGN_NAMES:
                    found |= {
                        s for s in _string_literals(node.value)
                        if "_" in s and s.islower() and " " not in s
                    }
    return found


def _school_scoped_tables() -> dict[str, str]:
    """``{db_table: "Model.field"}`` for every migration_cloud model carrying a
    ForeignKey whose TARGET is ``schools.School``, whatever the field is named."""
    scoped: dict[str, str] = {}
    for model in django_apps.get_app_config("migration_cloud").get_models():
        for f in model._meta.get_fields():
            if getattr(f, "many_to_one", False) and getattr(f, "related_model", None) is School:
                scoped[model._meta.db_table] = f"{model.__name__}.{f.name}"
                break
    return scoped


class MigrationCloudRlsTableCoverageTests(SimpleTestCase):
    def test_the_detector_itself_finds_the_tables_we_know_are_enumerated(self):
        # Prove the parser before believing its zero: a broken _enumerated_tables
        # would return an empty set and make the coverage test below fail for the
        # wrong reason (or, inverted, pass on nothing).
        enumerated = _enumerated_tables()
        self.assertIn("migration_cloud_migrationbundle", enumerated)
        self.assertIn("migration_cloud_migrationsourceconnection", enumerated)

    def test_the_detector_itself_sees_the_tenant_named_fks(self):
        scoped = _school_scoped_tables()
        # These are scoped by a FK named `tenant` / `tenant_scope`, which is
        # precisely what a field-name test misses.
        self.assertEqual(
            scoped.get("migration_cloud_companionciphertextblob"),
            "CompanionCiphertextBlob.tenant",
        )
        self.assertEqual(
            scoped.get("migration_cloud_migrationcloudapitoken"),
            "MigrationCloudAPIToken.tenant_scope",
        )
        self.assertIn("migration_cloud_guardianconsenttoken", scoped)

    def test_every_school_scoped_table_is_named_in_an_rls_migration(self):
        enumerated = _enumerated_tables()
        scoped = _school_scoped_tables()
        uncovered = sorted(t for t in scoped if t not in enumerated)
        self.assertEqual(
            uncovered, [],
            "tenant-scoped migration_cloud tables with no RLS enable/policy: "
            + ", ".join(f"{t} ({scoped[t]})" for t in uncovered),
        )
