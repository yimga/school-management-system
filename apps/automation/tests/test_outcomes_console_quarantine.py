"""Outcomes console exposes MigrationRun ↔ quarantine traceability for staff."""

import uuid

from django.db.models import Count
from django.test import TestCase

from apps.automation.models import MigrationRun
from apps.automation.quarantine_services import add_to_quarantine
from apps.schools.models import School


class OutcomesConsoleQuarantineColumnTests(TestCase):
    def test_migration_run_queryset_annotation_matches_outcomes_console(self):
        """Same Count annotation as automation.views.outcomes_console (staff UI column)."""
        u = uuid.uuid4().hex[:8]
        school = School.objects.create(
            name="OC School",
            slug=f"oc-{u}",
            subdomain=f"oc-{u}",
            is_active=True,
        )
        run = MigrationRun.objects.create(
            school=school,
            migration_type="students",
            dry_run=True,
            status=MigrationRun.Status.SUCCESS,
            row_count=0,
        )
        add_to_quarantine(
            school=school,
            migration_run=run,
            domain="students",
            row_index=1,
            payload={"x": 1},
            issue_class="missing_required",
        )
        annotated = (
            MigrationRun.objects.filter(pk=run.pk)
            .annotate(quarantine_record_count=Count("quarantine_records"))
            .first()
        )
        self.assertIsNotNone(annotated)
        self.assertEqual(annotated.quarantine_record_count, 1)
