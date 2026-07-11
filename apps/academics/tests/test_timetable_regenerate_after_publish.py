"""Regression: regenerating a timetable after one is PUBLISHED must not crash.

The generate view's "fresh slate" cleanup used to delete only status="DRAFT"
schedules. But the term-wide ScheduleEntry unique constraints
(uniq_schedentry_{teacher,room}_slot_termwide) key on (term, teacher/room,
time_slot) with condition is_cancelled=False and are STATUS-AGNOSTIC — so a
surviving PUBLISHED schedule's entries collided with the regenerated ones,
raising IntegrityError: a 500 that permanently blocked regenerating a term's
timetable in-product. The cleanup now clears schedules of every status.
"""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.scheduling import Schedule, ScheduleEntry, TimetableGenerator
from apps.academics.tests.test_timetable_publish_flow import _TimetableGraphMixin
from apps.accounts.models import User
from apps.schools.models import School


class RegenerateAfterPublishTests(_TimetableGraphMixin, TestCase):
    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Regen School {self.uid}",
            slug=f"regen-{self.uid}",
            subdomain=f"regen-{self.uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"regen_admin_{self.uid}",
            password="Test1234",
            role=User.Role.ADMIN,
        )
        self.graph = self.build_graph(self.school, self.uid)

    def _delete_all_for_term(self):
        # Mirrors the FIXED views_timetable.timetable_generate "fresh slate" cleanup.
        Schedule.objects.filter(
            academic_year=self.graph["year"],
            term=self.graph["term"],
            academic_year__school=self.school,
        ).delete()

    def test_regenerate_after_publish_succeeds(self):
        gen = TimetableGenerator(self.graph["year"], self.graph["term"])
        first = gen.generate_schedule(created_by=self.admin)
        first.publish()
        self.assertEqual(first.status, "PUBLISHED")
        self.assertGreater(first.entries.count(), 0)

        # Regenerate: clear ALL schedules for the term (the fix), then generate
        # again — the previously-published entries no longer exist to collide on
        # the status-agnostic term-wide unique constraints.
        self._delete_all_for_term()
        second = gen.generate_schedule(created_by=self.admin)
        self.assertEqual(second.status, "DRAFT")
        self.assertGreater(second.entries.count(), 0)
        # The published schedule was replaced, not left dangling.
        self.assertFalse(Schedule.objects.filter(pk=first.pk).exists())

    def test_draft_only_cleanup_leaves_published_entry_colliding(self):
        """Documents the bug the fix closes: the term-wide unique constraint bites
        ACROSS schedules regardless of status, so a published entry blocks an
        identical draft entry — which is exactly what a DRAFT-only cleanup left."""
        gen = TimetableGenerator(self.graph["year"], self.graph["term"])
        published = gen.generate_schedule(created_by=self.admin)
        published.publish()
        sample = published.entries.first()
        self.assertIsNotNone(sample)

        # OLD cleanup: DRAFT only — the published schedule + its entries survive.
        Schedule.objects.filter(
            academic_year=self.graph["year"],
            term=self.graph["term"],
            academic_year__school=self.school,
            status="DRAFT",
        ).delete()
        draft = Schedule.objects.create(
            name=f"regen-draft-{self.uid}",
            academic_year=self.graph["year"],
            term=self.graph["term"],
            status="DRAFT",
            created_by=self.admin,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ScheduleEntry.objects.create(
                    schedule=draft,
                    classroom=sample.classroom,
                    subject=sample.subject,
                    teacher=sample.teacher,
                    room=sample.room,
                    time_slot=sample.time_slot,
                )
