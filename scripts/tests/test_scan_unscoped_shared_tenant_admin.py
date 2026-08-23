"""Coverage for ``scan_unscoped_shared_tenant_admin``.

The gate needs Django (it reads the live admin registry, because
``TenantAdminSite.register`` synthesises the final admin class at registration
time and no AST scan of an app's ``admin.py`` can see it). These tests therefore
boot Django once and then exercise the classifier against the real tree.

The live-tree assertion doubles as calibration: if the tree is clean and the
gate reports findings anyway, the classifier is wrong, not the tree.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "scan_unscoped_shared_tenant_admin",
        SCRIPTS_DIR / "scan_unscoped_shared_tenant_admin.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScanUnscopedSharedTenantAdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(REPO_ROOT)
        sys.path.insert(0, str(REPO_ROOT))
        cls.mod = _load_module()
        cls.mod._bootstrap_django()

    def test_the_live_tree_is_clean(self):
        result, error = self.mod._classify()
        self.assertIsNone(error, error)
        findings, _stats = result
        self.assertEqual(
            findings,
            [],
            "every SHARED model on the tenant admin must be classified in one "
            "of the five TENANT_ADMIN_* maps in config/admin.py",
        )

    def test_it_actually_looked_at_something(self):
        # A classifier that silently matched nothing would also report zero
        # findings. Assert it walked a realistic registry.
        result, error = self.mod._classify()
        self.assertIsNone(error, error)
        _findings, stats = result
        self.assertGreater(stats["registrations"], 100, stats)
        self.assertGreater(
            stats["shared_no_school"],
            10,
            "the gate is meaningless if it never sees a SHARED model without a "
            "school column",
        )

    def test_the_tenancy_lists_parse(self):
        from config.admin import _tenancy_app_lists

        shared, tenant = _tenancy_app_lists()
        self.assertGreater(len(shared), 20)
        self.assertGreater(len(tenant), 5)

    def test_an_unclassified_shared_model_is_reported(self):
        """Register one for real, with its classification withheld.

        Popping an entry out of a map AFTER startup proves nothing: the maps are
        read by ``TenantAdminSite.register`` when admin autodiscovery runs, and
        the resolved admin class is fixed from then on. The gate deliberately
        keys on that RESOLVED class -- what actually happens -- not on what a map
        currently says, so a post-hoc mutation is correctly ignored by it.

        So do the real thing: unregister a model, withhold its classification,
        register it again, and confirm both that it lands on the fail-closed
        mixin and that the gate names it.
        """
        from unittest import mock

        from django.contrib.auth.models import Group

        from config import admin as admin_mod

        label = "auth.Group"
        original_admin = admin_mod.tenant_admin_site._registry[Group]
        withheld = frozenset(admin_mod.TENANT_ADMIN_GLOBAL_CATALOGS) - {label}
        self.assertNotEqual(
            withheld,
            admin_mod.TENANT_ADMIN_GLOBAL_CATALOGS,
            "fixture drifted: auth.Group is no longer a declared global catalog",
        )

        try:
            admin_mod.tenant_admin_site.unregister(Group)
            with mock.patch.object(
                admin_mod, "TENANT_ADMIN_GLOBAL_CATALOGS", withheld
            ):
                admin_mod.tenant_admin_site.register(Group, type(original_admin))
                resolved = type(admin_mod.tenant_admin_site._registry[Group])
                self.assertTrue(
                    any(
                        b.__name__ == "_TenantUnclassifiedFailClosedMixin"
                        for b in resolved.__mro__
                    ),
                    "an unclassified SHARED model must land on the fail-closed "
                    "mixin, so it renders empty rather than cross-tenant",
                )
                result, error = self.mod._classify()
                self.assertIsNone(error, error)
                findings, _ = result
                self.assertIn(
                    label,
                    {f["model"] for f in findings},
                    "and the gate must name it, so somebody classifies it",
                )
        finally:
            try:
                admin_mod.tenant_admin_site.unregister(Group)
            except Exception:  # noqa: BLE001 — restore must not mask the real failure
                pass
            admin_mod.tenant_admin_site.register(Group, type(original_admin))

        # Clean again afterwards: the mutation was the cause, and this test left
        # nothing behind for the next one.
        result, _ = self.mod._classify()
        self.assertEqual(result[0], [])

    def test_main_exits_zero_on_a_clean_tree(self):
        self.assertEqual(self.mod.main([]), 0)

    def test_json_mode_exits_zero_too(self):
        self.assertEqual(self.mod.main(["--json"]), 0)

    def test_operator_only_models_are_not_on_the_tenant_site(self):
        from config.admin import TENANT_ADMIN_OPERATOR_ONLY, tenant_admin_site

        registered = {
            f"{m._meta.app_label}.{m.__name__}" for m in tenant_admin_site._registry
        }
        self.assertEqual(TENANT_ADMIN_OPERATOR_ONLY & registered, set())

    def test_operator_only_models_kept_a_platform_home(self):
        # Skipping them on the tenant site must not delete the platform's own
        # access -- four of them were registered ONLY on the tenant site, so a
        # bare skip would have turned a leak into an outage.
        from config.admin import TENANT_ADMIN_OPERATOR_ONLY, platform_admin_site

        registered = {
            f"{m._meta.app_label}.{m.__name__}" for m in platform_admin_site._registry
        }
        missing = TENANT_ADMIN_OPERATOR_ONLY - registered
        self.assertEqual(missing, set(), f"lost their only admin surface: {missing}")

    def test_every_platform_admin_model_has_a_bridge(self):
        # apps/schools/tests/test_platform_admin_bridge_completeness.py enforces
        # this too; asserted here as well because re-homing a model onto the
        # platform admin is what this gate's fix DOES, and a missing bridge is
        # the failure mode that discovers.
        from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES
        from config.admin import platform_admin_site

        bridged = {str(v["admin_url"]) for v in PLATFORM_ADMIN_BRIDGES.values()}
        needed = {
            f"admin:{m._meta.app_label}_{m._meta.model_name}_changelist"
            for m in platform_admin_site._registry
        }
        self.assertEqual(sorted(needed - bridged), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
