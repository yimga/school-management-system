"""
End-to-end Phase 6 / Phase B DB gate: same ORM checks as scripts/verify_phase_b_execution.py
but against Django's migrated test database (CI), not the dev default sqlite from a subprocess.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import TestCase

from apps.brand_experience.models import PlatformGlobalBranding
from apps.platform_runtime.helpers import get_platform_site_settings_record


def _load_verify_phase_b_execution_module():
    root = Path(__file__).resolve().parent.parent.parent.parent
    path = root / "scripts" / "verify_phase_b_execution.py"
    spec = importlib.util.spec_from_file_location("verify_phase_b_execution_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PhaseBExecutionGateTests(TestCase):
    """Phase 6 E2E: migrated schema + consistency when a tenant site-settings row exists."""

    def test_migration_artifacts_present(self):
        mod = _load_verify_phase_b_execution_module()
        errs = mod.migration_artifact_errors()
        self.assertEqual(errs, [], errs)

    def test_orm_schema_and_snapshot_rows_when_site_exists(self):
        mod = _load_verify_phase_b_execution_module()
        self.assertEqual(mod.orm_phase_b_execution_errors(), [])

        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.save()
        # verify_phase_b_execution.orm_phase_b_execution_errors requires pk=1 when a tenant settings row exists.
        PlatformGlobalBranding.objects.get_or_create(pk=1)

        errs = mod.orm_phase_b_execution_errors()
        self.assertEqual(errs, [], errs)
