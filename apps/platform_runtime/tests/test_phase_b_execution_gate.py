"""
End-to-end Phase 6 / Phase B DB gate: same ORM checks as scripts/verify_phase_b_execution.py
but against Django's migrated test database (CI), not the dev default sqlite from a subprocess.
"""

from __future__ import annotations

from django.test import TestCase

from apps.brand_experience.models import PlatformGlobalBranding
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.platform_runtime.tests.support.script_loading import load_repo_script


def _load_verify_phase_b_execution_module():
    return load_repo_script(
        "scripts/verify_phase_b_execution.py",
        "verify_phase_b_execution_gate",
    )


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
        # Row is persisted by get_or_create; no redundant bare site.save() (slim SiteSettings + batch 842+ optional maps).
        # verify_phase_b_execution.orm_phase_b_execution_errors requires pk=1 when a tenant settings row exists.
        PlatformGlobalBranding.objects.get_or_create(pk=1)

        errs = mod.orm_phase_b_execution_errors()
        self.assertEqual(errs, [], errs)
