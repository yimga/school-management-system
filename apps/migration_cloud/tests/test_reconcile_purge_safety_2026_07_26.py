"""Reconciliation purge-safety: scope indirect-school models + never seal on a
missing per-domain visible-count.

Two gaps let the APPLIED -> RECONCILED close-out (which PURGES the encrypted source
blobs) fire without real proof the rows landed:

  1. verification._school_scoped_count fell through to ``.all()`` for any model
     whose school link isn't literally ``school`` / ``student`` (e.g.
     HostelRoom.hostel -> Hostel.school). In the shared-schema path ``.all()``
     counts EVERY school's rows, so drift could never fire. Now scoped by the
     model's indirect school path.
  2. verify_landed_counts swallows a per-domain count error (the domain is simply
     absent from the result). reconcile then saw ``visible=None`` and skipped the
     drift check -> sealed + purged with no proof. Now a verifiable domain that
     reported creates but has no visible-count blocks the seal.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.migration_cloud import reconciliation
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.reconciliation import reconcile_bundle
from apps.migration_cloud.verification import _school_scoped_count
from apps.schoolops.models import Hostel, HostelRoom
from apps.schools.models import School


class HostelScopedCountTests(TestCase):
    def test_hostel_rooms_scoped_by_school_not_all(self):
        a = School.objects.create(
            name="Sch A", slug="hostel-a", subdomain="hostel-a", is_active=True, country_code="CM"
        )
        b = School.objects.create(
            name="Sch B", slug="hostel-b", subdomain="hostel-b", is_active=True, country_code="CM"
        )
        ha = Hostel.objects.create(school=a, name="A-Hostel")
        hb = Hostel.objects.create(school=b, name="B-Hostel")
        HostelRoom.objects.create(hostel=ha, name="A1")
        HostelRoom.objects.create(hostel=ha, name="A2")
        HostelRoom.objects.create(hostel=hb, name="B1")
        # School A sees only its 2 rooms — NOT all 3 (the old .all() overcount).
        self.assertEqual(_school_scoped_count(HostelRoom, a), 2)
        self.assertEqual(_school_scoped_count(HostelRoom, b), 1)


class ReconcileMissingVisibleCountTests(TestCase):
    def _applied_bundle(self, key):
        school = School.objects.create(
            name=f"Recon {key}", slug=f"recon-{key}", subdomain=f"recon-{key}",
            is_active=True, country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="recon", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"recon-{key}", status=BundleStatus.APPLIED, school=school,
            mapping_summary={"apply_totals": {"created": 5, "updated": 0, "quarantined": 0}},
            discovery_summary={"per_artifact_domain": {"roster.csv": {"domain": "students"}}},
        )
        MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="roster.csv", filename="roster.csv",
            sha256="0" * 64, detected_format="csv", row_count=5,
        )
        return bundle

    def test_missing_visible_count_for_verifiable_domain_blocks_seal(self):
        b = self._applied_bundle("missing")
        with (
            mock.patch.object(
                reconciliation, "_domain_run_stats",
                return_value={"students": {"created": 5, "updated": 0, "errors": 0}},
            ),
            mock.patch.object(reconciliation, "_safe_verify_visible", return_value={}),
        ):
            report = reconcile_bundle(bundle_id=b.pk)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.APPLIED)  # NOT sealed / purged
        self.assertTrue(
            any("could not be completed" in str(n).lower() for n in report.notes),
            msg=f"expected a missing-visible-count block note, got {report.notes!r}",
        )

    def test_verified_domain_seals(self):
        b = self._applied_bundle("ok")
        with (
            mock.patch.object(
                reconciliation, "_domain_run_stats",
                return_value={"students": {"created": 5, "updated": 0, "errors": 0}},
            ),
            mock.patch.object(reconciliation, "_safe_verify_visible", return_value={"students": 5}),
        ):
            reconcile_bundle(bundle_id=b.pk)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.RECONCILED)  # visible == created -> seals
