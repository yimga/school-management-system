"""The structural seal must pass on the real tree AND catch regressions.

Sealing the seal: if the verifier can't detect a removed/misordered migrate
call, it's not a guard. These tests lock both directions.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[3]
    / "scripts"
    / "verify_provisioning_migrates_tenant_schema.py"
)
_spec = importlib.util.spec_from_file_location("verify_prov_migrate_seal", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


GOOD = """
def _do_provision_tracked(school, school_id, **kwargs):
    tenant_client = _ensure_tenant_client(school)
    if tenant_client is not None:
        _run_tenant_migrations(tenant_client)
    with _optional_tenant_context(tenant_client):
        AcademicYear.objects.get_or_create(school=school)
"""

MISSING = """
def _do_provision_tracked(school, school_id, **kwargs):
    tenant_client = _ensure_tenant_client(school)
    with _optional_tenant_context(tenant_client):
        AcademicYear.objects.get_or_create(school=school)
"""

AFTER = """
def _do_provision_tracked(school, school_id, **kwargs):
    tenant_client = _ensure_tenant_client(school)
    with _optional_tenant_context(tenant_client):
        AcademicYear.objects.get_or_create(school=school)
    _run_tenant_migrations(tenant_client)
"""


class ProvisioningMigrateSealTests(unittest.TestCase):
    def test_real_tree_passes(self):
        self.assertEqual(_mod.main(), 0, "the shipped tasks.py must pass the seal")

    def test_good_source_passes(self):
        code, _ = _mod.check_source(GOOD)
        self.assertEqual(code, 0)

    def test_missing_migrate_is_caught(self):
        code, msg = _mod.check_source(MISSING)
        self.assertEqual(code, 1)
        self.assertIn("never calls", msg)

    def test_migrate_after_seed_is_caught(self):
        code, msg = _mod.check_source(AFTER)
        self.assertEqual(code, 1)
        self.assertIn("AFTER", msg)


if __name__ == "__main__":
    unittest.main()
