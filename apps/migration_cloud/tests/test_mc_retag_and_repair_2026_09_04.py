"""mc_retag_and_repair routes retag + repair through the same guardrails as the UI."""
from __future__ import annotations

import uuid
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.migration_cloud.models import BundleStatus, MigrationBundle
from apps.schools.models import School

_REPAIR = "apps.migration_cloud.management.commands.mc_retag_and_repair.repair_bundle"
_READINESS = "apps.migration_cloud.management.commands.mc_retag_and_repair.repair_readiness"


class McRetagAndRepairCommandTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Retag {uid}",
            slug=f"retag-{uid}",
            subdomain=f"rt{uid}",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            status=BundleStatus.APPLIED,
            idempotency_key=f"mc-retag-{uuid.uuid4().hex[:16]}",
        )

    def _run(self, *args):
        out = StringIO()
        call_command("mc_retag_and_repair", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_dry_run_is_read_only(self):
        with (
            mock.patch(_REPAIR) as repair,
            mock.patch(
                "apps.migration_cloud.pipeline.refresh_bundle_inference",
            ) as refresh,
        ):
            body = self._run("--bundle-id", str(self.bundle.pk), "--dry-run")
        self.assertIn("Read-only", body)
        repair.assert_not_called()
        refresh.assert_not_called()

    def test_apply_refreshes_inference_and_repairs_when_repairable(self):
        with (
            mock.patch(
                "apps.migration_cloud.catalog_preflight.apply_catalog_recommendations",
                return_value=0,
            ) as apply_catalog,
            mock.patch(
                "apps.migration_cloud.pipeline.refresh_bundle_inference",
                return_value={"per_artifact": {}},
            ) as refresh,
            mock.patch(_READINESS, return_value=mock.Mock(repairable=True, reason="", blockers=[])),
            mock.patch(
                _REPAIR,
                return_value=mock.Mock(
                    ok=True,
                    ran=True,
                    message="ok",
                    created=10,
                    updated=5,
                    quarantined=0,
                    before_status=BundleStatus.APPLIED,
                    after_status=BundleStatus.APPLIED,
                    blockers=[],
                ),
            ) as repair,
        ):
            body = self._run("--bundle-id", str(self.bundle.pk), "--apply", "--sync")
        apply_catalog.assert_called_once()
        refresh.assert_called_once()
        repair.assert_called_once_with(bundle_id=self.bundle.pk, off_http=False)
        self.assertIn("Applied:", body)

    def test_force_reapply_on_clean_applied_bundle(self):
        with (
            mock.patch(
                "apps.migration_cloud.catalog_preflight.apply_catalog_recommendations",
                return_value=1,
            ),
            mock.patch(
                "apps.migration_cloud.pipeline.refresh_bundle_inference",
                return_value={"per_artifact": {"dir.xlsx": {"domain": "staff"}}},
            ),
            mock.patch(
                _READINESS,
                return_value=mock.Mock(
                    repairable=False,
                    reason="applied cleanly",
                    blockers=["status:APPLIED"],
                ),
            ),
            mock.patch(_REPAIR) as repair,
            mock.patch(
                "apps.migration_cloud.management.commands.mc_retag_and_repair.Command._force_reapply",
                return_value=mock.Mock(
                    ok=True,
                    ran=True,
                    message="reimported",
                    created=40,
                    updated=11,
                    quarantined=0,
                    before_status=BundleStatus.APPLIED,
                    after_status=BundleStatus.APPLIED,
                    blockers=[],
                ),
            ) as force_reapply,
        ):
            body = self._run(
                "--bundle-id",
                str(self.bundle.pk),
                "--apply",
                "--force-reapply",
                "--sync",
            )
        repair.assert_not_called()
        force_reapply.assert_called_once()
        self.assertIn("Applied:", body)

    def test_school_mismatch_refuses(self):
        other = School.objects.create(
            name="Other",
            slug=f"other-{uuid.uuid4().hex[:8]}",
            subdomain=f"oth{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        with self.assertRaises(CommandError):
            self._run(
                "--bundle-id",
                str(self.bundle.pk),
                "--school",
                other.slug,
                "--dry-run",
            )
