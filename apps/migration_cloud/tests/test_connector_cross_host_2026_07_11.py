"""Wave 2 — Migration Cloud connector cross-host reverse safety + RLS coverage.

Two failure classes this guards, both DB-free (fast SimpleTestCase):

1. Cross-host 500 — the connector wizard renders under three namespace chains
   (tenant ``migration_cloud_connector``, operator
   ``migration_cloud_super:migration_cloud_connector``, portal
   ``migration_cloud_portal:migration_cloud_connector``). A bare
   ``migration_cloud_connector:<name>`` reverse NoReverseMatch-es → 500 on the two
   nested mounts. ``_connector_namespace`` rebuilds the live prefix from
   ``resolver_match.namespaces`` so redirects and templates resolve on every mount.

2. RLS coverage drift — every school-scoped connector table must carry the tenant
   default-deny policy (migration 0037). If a future connector model adds a
   ``school`` FK but nobody extends 0037's TABLES, this test fails.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.conf import settings
from django.test import SimpleTestCase

from apps.migration_cloud.views_connectors import _connector_namespace


def _fake_request(namespaces):
    """Minimal request stand-in exposing ``resolver_match.namespaces``."""
    return SimpleNamespace(resolver_match=SimpleNamespace(namespaces=namespaces))


class ConnectorNamespaceResolutionTests(SimpleTestCase):
    def test_tenant_host_top_level_namespace(self):
        req = _fake_request(["migration_cloud_connector"])
        self.assertEqual(_connector_namespace(req), "migration_cloud_connector")

    def test_operator_nested_namespace(self):
        req = _fake_request(["migration_cloud_super", "migration_cloud_connector"])
        self.assertEqual(
            _connector_namespace(req),
            "migration_cloud_super:migration_cloud_connector",
        )

    def test_portal_nested_namespace(self):
        req = _fake_request(["migration_cloud_portal", "migration_cloud_connector"])
        self.assertEqual(
            _connector_namespace(req),
            "migration_cloud_portal:migration_cloud_connector",
        )

    def test_missing_resolver_match_falls_back_to_tenant_namespace(self):
        # No resolver_match yet (e.g. very early in the cycle) → safe default.
        self.assertEqual(
            _connector_namespace(SimpleNamespace(resolver_match=None)),
            "migration_cloud_connector",
        )

    def test_unrelated_namespace_chain_falls_back(self):
        # Chain that does not end in the connector namespace → do not guess; use
        # the tenant-host default so a reverse still targets a real namespace.
        req = _fake_request(["some_other_app"])
        self.assertEqual(_connector_namespace(req), "migration_cloud_connector")


def _load_rls_migration_tables():
    """Import 0037's module by path (name starts with a digit) and read TABLES."""
    mig_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "migration_cloud"
        / "migrations"
        / "0037_connector_tables_rls.py"
    )
    spec = importlib.util.spec_from_file_location("_mc_0037_rls", mig_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module.TABLES)


class ConnectorRlsCoverageTests(SimpleTestCase):
    def test_migration_0037_exists(self):
        self.assertTrue(
            (
                Path(settings.BASE_DIR)
                / "apps"
                / "migration_cloud"
                / "migrations"
                / "0037_connector_tables_rls.py"
            ).exists()
        )

    def test_every_school_scoped_connector_table_has_rls_policy(self):
        """Each connector model with a ``school`` FK must be in 0037's TABLES.

        Introspects ``models_connectors`` rather than hard-coding names, so a new
        school-scoped connector model that skips RLS trips this immediately.
        """
        covered = _load_rls_migration_tables()
        from apps.migration_cloud import models_connectors

        school_scoped = []
        for name in dir(models_connectors):
            obj = getattr(models_connectors, name)
            if not isinstance(obj, type):
                continue
            meta = getattr(obj, "_meta", None)
            if meta is None or meta.abstract or meta.proxy:
                continue
            if getattr(meta, "app_label", None) != "migration_cloud":
                continue
            field_names = {f.name for f in meta.get_fields()}
            if "school" in field_names:
                school_scoped.append(meta.db_table)

        self.assertTrue(school_scoped, "expected some school-scoped connector models")
        missing = sorted(t for t in school_scoped if t not in covered)
        self.assertEqual(
            missing,
            [],
            f"school-scoped connector tables missing from RLS migration 0037: {missing}",
        )

    def test_platform_wide_profile_table_is_not_rls_scoped(self):
        """``MigrationConnectorProfile`` is platform-wide (no school_id) and must
        NOT be under the school_id tenant policy."""
        covered = _load_rls_migration_tables()
        profile_table = django_apps.get_model(
            "migration_cloud", "MigrationConnectorProfile"
        )._meta.db_table
        self.assertNotIn(profile_table, covered)
