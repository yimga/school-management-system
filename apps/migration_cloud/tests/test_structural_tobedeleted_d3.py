"""Audit D-3 — structural `tobedeleted` rows are held for review, not imported.

A OneRoster course/class marked ``status=tobedeleted`` must NOT land as an active
Subject/Classroom (the pre-D-3 bug) and must NOT hard-delete an existing tenant
row (those models have no is_active/status column and grades/enrollments FK into
them — a delete could orphan dependents). It is held for review, with its source
row (audit C-4).
"""
from __future__ import annotations

from django.test import TestCase


class StructuralTombstoneD3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.schools.models import School

        cls.school = School.objects.create(
            name="D3 School", slug="d3-tombstone-school", subdomain="d3-tombstone-school",
        )

    def _ctx(self):
        from apps.migration_cloud.landers.base import LanderContext

        return LanderContext(
            school=self.school, schema_name="public", bundle_id=0, artifact_id=0,
            dry_run=False,
        )

    def test_academics_holds_tobedeleted_course(self):
        from apps.academics.models import Subject
        from apps.migration_cloud.landers.academics_lander import AcademicsLander

        rows = [
            {"subject_name": "Mathematics", "subject_code": "MATH", "record_status": "active"},
            {"subject_name": "Latin", "subject_code": "LAT", "record_status": "tobedeleted"},
        ]
        result = AcademicsLander().land(canonical_rows=iter(rows), ctx=self._ctx())

        self.assertEqual(result.created, 1)
        self.assertEqual(result.quarantined, 1)
        self.assertTrue(
            Subject.objects.filter(school=self.school, name="Mathematics").exists()
        )
        self.assertFalse(
            Subject.objects.filter(school=self.school, name="Latin").exists()
        )
        # The held row carries its source row for operator review (C-4).
        self.assertTrue(
            any("Latin" in str(er.get("row")) for er in result.error_rows)
        )

    def test_academics_does_not_delete_existing_on_tombstone(self):
        from apps.academics.models import Subject
        from apps.migration_cloud.landers.academics_lander import AcademicsLander

        existing = Subject.objects.create(school=self.school, name="History")
        rows = [{"subject_name": "History", "subject_code": "HIST", "record_status": "tobedeleted"}]
        AcademicsLander().land(canonical_rows=iter(rows), ctx=self._ctx())
        # The existing subject is left intact (referential safety).
        self.assertTrue(Subject.objects.filter(pk=existing.pk).exists())

    def test_sections_holds_tobedeleted_class(self):
        from apps.academics.models import Classroom
        from apps.migration_cloud.landers.sections_lander import SectionsLander

        rows = [
            {"name": "Old Class 7A", "section_code": "OLD-7A", "record_status": "tobedeleted"},
        ]
        result = SectionsLander().land(canonical_rows=iter(rows), ctx=self._ctx())
        self.assertEqual(result.quarantined, 1)
        self.assertEqual(result.created, 0)
        self.assertFalse(
            Classroom.objects.filter(school=self.school, name="Old Class 7A").exists()
        )

    def test_active_structural_rows_unaffected(self):
        """A non-tombstone row still lands normally (no regression)."""
        from apps.academics.models import Subject
        from apps.migration_cloud.landers.academics_lander import AcademicsLander

        rows = [{"subject_name": "Physics", "subject_code": "PHY"}]  # no status key
        result = AcademicsLander().land(canonical_rows=iter(rows), ctx=self._ctx())
        self.assertEqual(result.created, 1)
        self.assertTrue(
            Subject.objects.filter(school=self.school, name="Physics").exists()
        )

    def test_source_deletion_classifier_matches_lander_hold_strings(self):
        """Must-fire coupling: the orchestrator quarantine classifier buckets the
        landers' ACTUAL hold strings as ``source_deletion``.

        This locks the producer↔classifier string coupling that is otherwise
        guarded only by code review — a future edit to either the lander message
        or ``_classify_quarantine_issue`` that breaks the match would silently
        drop held tobedeleted rows into the generic ``lander_error`` bucket
        instead of the operator's "held: source deleted" review surface. Feeding
        the lander's real emitted string (not a hand-copied literal) is what makes
        this a genuine coupling test.
        """
        from apps.migration_cloud.landers.academics_lander import AcademicsLander
        from apps.migration_cloud.landers.sections_lander import SectionsLander
        from apps.migration_cloud.orchestrator import _classify_quarantine_issue

        acad = AcademicsLander().land(
            canonical_rows=iter(
                [{"subject_name": "Latin", "subject_code": "LAT", "record_status": "tobedeleted"}]
            ),
            ctx=self._ctx(),
        )
        self.assertEqual(len(acad.errors), 1)
        self.assertEqual(_classify_quarantine_issue(acad.errors[0]), "source_deletion")

        sect = SectionsLander().land(
            canonical_rows=iter(
                [{"name": "Old 7A", "section_code": "OLD-7A", "record_status": "tobedeleted"}]
            ),
            ctx=self._ctx(),
        )
        self.assertEqual(len(sect.errors), 1)
        self.assertEqual(_classify_quarantine_issue(sect.errors[0]), "source_deletion")
