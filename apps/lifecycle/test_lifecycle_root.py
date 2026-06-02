"""Lifecycle spine — service-layer + signal smoke tests."""

from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School

from .models import SchoolLifecycleStage
from .services import (
    actor_hash,
    current_stage,
    record_stage,
    stage_counts,
    timeline_for,
)


class ActorHashTests(TestCase):
    def test_returns_12_hex_chars(self):
        h = actor_hash("42")
        self.assertEqual(len(h), 12)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_empty_string_for_none(self):
        self.assertEqual(actor_hash(None), "")

    def test_stable_for_same_input(self):
        self.assertEqual(actor_hash(42), actor_hash(42))


class RecordStageTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", slug="test-school")

    def test_rejects_unknown_stage(self):
        with self.assertRaises(ValueError):
            record_stage(self.school, "NOT_A_REAL_STAGE")

    def test_sanitizes_sensitive_keys_from_payload(self):
        row = record_stage(
            self.school,
            SchoolLifecycleStage.Stage.OPERATING,
            payload={"role": "admin", "password": "p", "api_key": "k"},
        )
        self.assertIn("role", row.payload)
        self.assertNotIn("password", row.payload)
        self.assertNotIn("api_key", row.payload)

    def test_caps_note_at_200_chars(self):
        row = record_stage(
            self.school,
            SchoolLifecycleStage.Stage.OPERATING,
            note="x" * 500,
        )
        self.assertEqual(len(row.note), 200)

    def test_refuses_past_terminal_stage(self):
        record_stage(self.school, SchoolLifecycleStage.Stage.OFFBOARDING_PURGED)
        new_row = record_stage(self.school, SchoolLifecycleStage.Stage.OPERATING)
        self.assertEqual(new_row.stage, SchoolLifecycleStage.Stage.OFFBOARDING_PURGED)


class CurrentStageTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School 2", slug="test-school-2")

    def test_returns_none_when_empty(self):
        # post_save signal will have written rows. Wipe to assert empty path.
        SchoolLifecycleStage.objects.filter(school=self.school).delete()
        self.assertIsNone(current_stage(self.school))

    def test_returns_latest(self):
        SchoolLifecycleStage.objects.filter(school=self.school).delete()
        record_stage(self.school, SchoolLifecycleStage.Stage.REQUESTED)
        record_stage(self.school, SchoolLifecycleStage.Stage.OPERATING)
        self.assertEqual(current_stage(self.school), SchoolLifecycleStage.Stage.OPERATING)


class TimelineForTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School 3", slug="test-school-3")

    def test_returns_queryset_for_school(self):
        rows = list(timeline_for(self.school, limit=10))
        self.assertTrue(all(r.school_id == self.school.id for r in rows))


class StageCountsTests(TestCase):
    def test_counts_by_stage(self):
        school = School.objects.create(name="Test School 4", slug="test-school-4")
        SchoolLifecycleStage.objects.filter(school=school).delete()
        record_stage(school, SchoolLifecycleStage.Stage.REQUESTED)
        record_stage(school, SchoolLifecycleStage.Stage.REQUESTED)
        record_stage(school, SchoolLifecycleStage.Stage.OPERATING)
        counts = stage_counts(timeline_for(school))
        self.assertEqual(counts.get(SchoolLifecycleStage.Stage.REQUESTED), 2)
        self.assertEqual(counts.get(SchoolLifecycleStage.Stage.OPERATING), 1)


class SchoolPostSaveSignalTests(TestCase):
    def test_creates_requested_and_provisioned_rows(self):
        school = School.objects.create(name="Signal School", slug="signal-school")
        rows = list(timeline_for(school))
        stages = {r.stage for r in rows}
        self.assertIn(SchoolLifecycleStage.Stage.REQUESTED, stages)
        self.assertIn(SchoolLifecycleStage.Stage.PROVISIONED, stages)
