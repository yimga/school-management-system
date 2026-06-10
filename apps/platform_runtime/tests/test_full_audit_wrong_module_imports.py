"""Full cross-WF audit (2026-06-10) — wrong-module imports corrected.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

A repo-wide AST resolution of every ``from apps.* import`` symbol surfaced four
wrong-module imports that pointed at a class living in a different module (or a
renamed class). Each sat in code that either swallowed the resulting error
(silent-wrong result, the WF4 pattern) or would crash when reached:

  * studio_os/services.py        ProcessRun           -> orchestration.OrchestrationRun (x2, swallowed)
  * siteconfig/admin_index_surface.py MigrationCloudBundle -> migration_cloud.MigrationBundle (swallowed)
  * schools/marketing_views.py   siteconfig.models.RegionalPitch -> siteconfig.models_global_experience (swallowed)
  * accounts/migration_importers.py billing.models.ComplianceProfile -> finance.models.ComplianceProfile (hard)

This test pins the corrected targets (the right class is importable + the field
lookups each call site uses are valid) and asserts the dead names are gone.
"""

from __future__ import annotations

import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class FullAuditWrongModuleImportTests(unittest.TestCase):

    def test_corrected_targets_resolve(self) -> None:
        from apps.orchestration.models import OrchestrationRun
        from apps.migration_cloud.models import MigrationBundle
        from apps.siteconfig.models_global_experience import RegionalPitch
        from apps.finance.models import ComplianceProfile

        # Field lookups used at each call site must be valid (.query renders SQL).
        self.assertTrue(
            str(OrchestrationRun.objects.filter(status__iexact="failed").query)
        )
        self.assertTrue(str(MigrationBundle.objects.all().query))
        self.assertTrue(
            str(RegionalPitch.objects.filter(country_code="US", is_active=True).query)
        )
        self.assertTrue(
            str(ComplianceProfile.objects.filter(is_active=True).query)
        )

    def test_dead_names_removed_from_call_sites(self) -> None:
        checks = {
            "apps/studio_os/services.py": ["import ProcessRun", "ProcessRun.objects"],
            "apps/siteconfig/admin_index_surface.py": ["MigrationCloudBundle"],
            "apps/schools/marketing_views.py": [
                "from apps.siteconfig.models import RegionalPitch"
            ],
            "apps/accounts/migration_importers.py": [
                "from apps.billing.models import ComplianceProfile"
            ],
        }
        for rel, deads in checks.items():
            src = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            for dead in deads:
                self.assertNotIn(dead, src, f"{rel} still references `{dead}`")


if __name__ == "__main__":
    unittest.main()
