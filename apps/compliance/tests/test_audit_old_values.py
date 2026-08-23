"""AuditLog UPDATE rows must record the PRE-change state in ``old_values``.

``get_model_changes`` used to re-SELECT the row from inside the ``post_save``
receiver — i.e. after the UPDATE had already been written — so ``old_values``
was a serialisation of the NEW state and ``changed_fields`` was always empty.
The trail said "Invoice #500 was updated" but could never say what it was
before, for every ``audit_enabled`` model. These tests pin the pre_save stash.
"""

from datetime import date

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.compliance.models_audit import AuditLog
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class AuditOldValuesTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="audit-oldvals-school",
            subdomain="audit-oldvals-school",
            name="Audit Old Values School",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
        )
        # AuditLog is append-only (platform_runtime.append_only), so the
        # CREATE row cannot be deleted -- watermark it instead and only look at
        # rows written after setUp.
        last = AuditLog.objects.order_by("-id").first()
        self.since_id = last.id if last else 0

    def _update_row(self):
        rows = AuditLog.objects.filter(
            id__gt=self.since_id,
            model_name="AcademicYear",
            object_id=str(self.year.pk),
            action=AuditLog.Action.UPDATE,
        )
        # Reached-the-code guard: if the post_save receiver never ran (audit
        # disabled, signal not wired, model name changed) there is nothing to
        # assert on and every assertion below would pass vacuously.
        self.assertEqual(
            rows.count(), 1, "expected exactly one AuditLog UPDATE row for the save"
        )
        return rows.get()

    def test_update_records_previous_value_not_the_new_one(self):
        self.year.name = "2026/2027"
        self.year.save()

        row = self._update_row()
        self.assertIsNotNone(row.old_values, "UPDATE row must carry old_values")
        self.assertEqual(row.old_values["name"], "2025/2026")
        self.assertEqual(row.new_values["name"], "2026/2027")
        self.assertNotEqual(
            row.old_values["name"],
            row.new_values["name"],
            "old_values must be the PRE-change state, not a re-read of the new row",
        )

    def test_update_reports_changed_fields(self):
        self.year.is_active = True
        self.year.save()

        row = self._update_row()
        self.assertTrue(row.changed_fields, "changed_fields must not be empty")
        self.assertIn("is_active", row.changed_fields)
        # get_changes() is the UI accessor and reads changed_fields; it went
        # silently empty for every UPDATE while old_values == new_values.
        changes = row.get_changes()
        self.assertIn("is_active", changes)
        self.assertEqual(changes["is_active"], (False, True))

    def test_update_fields_save_does_not_report_unpersisted_fields(self):
        """``save(update_fields=[...])`` must not report a field it never wrote.

        The old post_save re-read compared the DB row against the in-memory
        instance, so a field changed in memory but excluded from update_fields
        showed up in changed_fields even though no UPDATE touched it.
        """
        self.year.is_active = True
        self.year.name = "NEVER-PERSISTED"
        self.year.save(update_fields=["is_active"])

        row = self._update_row()
        self.assertIn("is_active", row.changed_fields or [])
        self.assertNotIn(
            "name",
            row.changed_fields or [],
            "name was not in update_fields, so no UPDATE wrote it",
        )

    def test_create_still_has_no_old_values(self):
        AcademicYear.objects.create(
            school=self.school,
            name="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 7, 31),
        )
        row = AuditLog.objects.get(
            id__gt=self.since_id,
            model_name="AcademicYear",
            action=AuditLog.Action.CREATE,
        )
        self.assertIsNone(row.old_values)
        self.assertEqual(row.new_values["name"], "2027/2028")
