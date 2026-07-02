"""T15: conflict detection now covers every domain, not just students.

``upsert_with_conflict_detection`` is the shared helper the domain landers call
in place of a bare ``update_or_create``, so finance / guardians / staff /
grades / attendance (and future domains) get the same ``MigrationConflict``
operator-review surface students already had. Before this, a re-apply silently
overwrote a tenant's existing invoice amount / grade / guardian record with no
review row.

These tests exercise the generic helper directly, using ``MigrationBundle`` as
a convenient stand-in canonical model — the helper is model-agnostic (it
introspects ``_meta`` and compares field values), so this runs in the default
schema without a full tenant apply.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase

from apps.migration_cloud.landers._helpers import upsert_with_conflict_detection
from apps.migration_cloud.models import (
    BundleStatus,
    ConflictResolution,
    IntakeMethod,
    MigrationBundle,
    MigrationConflict,
)


class UpsertConflictDetectionTests(TestCase):
    def setUp(self):
        self.bundle = MigrationBundle.objects.create(
            label="orig-label",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="conflict-helper-test",
            status=BundleStatus.MAPPED,
        )
        self.ctx = SimpleNamespace(bundle_id=self.bundle.pk)

    def test_new_row_creates_and_logs_no_conflict(self):
        obj, created, preserved = upsert_with_conflict_detection(
            ctx=self.ctx,
            domain="students",
            model=MigrationBundle,
            lookup={"idempotency_key": "brand-new-key"},
            defaults={
                "label": "fresh",
                "intake_method": IntakeMethod.FILE_UPLOAD,
                "status": BundleStatus.PENDING,
            },
            legacy_id="x",
        )
        self.assertTrue(created)
        self.assertFalse(preserved)
        self.assertEqual(
            MigrationConflict.objects.filter(bundle=self.bundle).count(), 0
        )
        obj.delete()

    def test_changed_existing_value_logs_conflict_and_overwrites(self):
        obj, created, preserved = upsert_with_conflict_detection(
            ctx=self.ctx,
            domain="finance",
            model=MigrationBundle,
            lookup={"pk": self.bundle.pk},
            defaults={"label": "changed-label"},
            legacy_id="inv-1",
        )
        self.assertFalse(created)
        self.assertFalse(preserved)  # no prior PRESERVE resolution

        conflicts = MigrationConflict.objects.filter(bundle=self.bundle)
        self.assertEqual(conflicts.count(), 1)
        conflict = conflicts.first()
        self.assertIn("label", conflict.changed_fields)
        self.assertEqual(conflict.existing_values.get("label"), "orig-label")
        self.assertEqual(conflict.incoming_values.get("label"), "changed-label")

        # Default resolution is OVERWRITE, so the update WAS applied.
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.label, "changed-label")

    def test_preserve_resolution_skips_the_update(self):
        canonical_model = (
            f"{MigrationBundle.__module__}.{MigrationBundle.__name__}"
        )
        MigrationConflict.objects.create(
            bundle=self.bundle,
            domain="finance",
            canonical_model=canonical_model,
            canonical_pk=str(self.bundle.pk),
            legacy_id="inv-1",
            existing_values={"label": "orig-label"},
            incoming_values={"label": "changed-label"},
            changed_fields=["label"],
            resolution=ConflictResolution.PRESERVE,
        )
        obj, created, preserved = upsert_with_conflict_detection(
            ctx=self.ctx,
            domain="finance",
            model=MigrationBundle,
            lookup={"pk": self.bundle.pk},
            defaults={"label": "should-not-apply"},
            legacy_id="inv-1",
        )
        self.assertTrue(preserved)
        self.assertFalse(created)
        # PRESERVE means the tenant's existing value is untouched.
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.label, "orig-label")
