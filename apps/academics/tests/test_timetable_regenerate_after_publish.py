"""Regression: regenerating a timetable after one is PUBLISHED must not crash
AND must not destroy the live published plan.

The generate view's cleanup used to delete every schedule for the term
(draft AND published). Migration 0066 rescopes uniqueness to the plan, so a
draft may coexist with the published timetable — regenerate now clears DRAFT
rows only; publish demotes rivals via ``Schedule.publish()``.
"""

from __future__ import annotations

import uuid

from django.db import transaction
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

    def _delete_drafts_for_term(self):
        # Mirrors views_timetable.timetable_generate draft-only cleanup.
        Schedule.objects.filter(
            academic_year=self.graph["year"],
            term=self.graph["term"],
            academic_year__school=self.school,
            status="DRAFT",
        ).delete()

    def test_regenerate_after_publish_preserves_published(self):
        gen = TimetableGenerator(self.graph["year"], self.graph["term"])
        first = gen.generate_schedule(created_by=self.admin)
        first.publish()
        self.assertEqual(first.status, "PUBLISHED")
        self.assertGreater(first.entries.count(), 0)

        # Regenerate clears drafts only — the live published plan stays.
        self._delete_drafts_for_term()
        second = gen.generate_schedule(created_by=self.admin)
        self.assertEqual(second.status, "DRAFT")
        self.assertGreater(second.entries.count(), 0)
        first.refresh_from_db()
        self.assertEqual(first.status, "PUBLISHED")
        self.assertTrue(Schedule.objects.filter(pk=first.pk).exists())
        self.assertNotEqual(first.pk, second.pk)

    def test_a_draft_may_now_coexist_with_the_published_plan(self):
        """The inverse of what this test used to assert — deliberately.

        It previously pinned the term-wide unique biting ACROSS schedules
        (a published entry blocking an identical draft entry) as CORRECT, and
        justified deleting the live timetable on every regenerate. That was the
        bug, not the contract: it also made the second plan for any term
        impossible, so a school could generate its timetable exactly once.

        Migration 0066 rescopes the uniques to the plan. A draft proposing the
        same teacher/room/slot as the published plan is a PROPOSAL, not a clash,
        and must be storable — that is what lets a school draft a replacement
        while the current timetable stays live.
        """
        gen = TimetableGenerator(self.graph["year"], self.graph["term"])
        published = gen.generate_schedule(created_by=self.admin)
        published.publish()
        sample = published.entries.first()
        self.assertIsNotNone(sample)

        draft = Schedule.objects.create(
            name=f"regen-draft-{self.uid}",
            academic_year=self.graph["year"],
            term=self.graph["term"],
            status="DRAFT",
            created_by=self.admin,
        )
        with transaction.atomic():
            ScheduleEntry.objects.create(
                schedule=draft,
                classroom=sample.classroom,
                subject=sample.subject,
                teacher=sample.teacher,
                room=sample.room,
                time_slot=sample.time_slot,
            )

        self.assertTrue(Schedule.objects.filter(pk=published.pk).exists())
        self.assertEqual(draft.entries.count(), 1)

    def test_publishing_a_replacement_demotes_the_previous_plan(self):
        """One live timetable per (term, shift) — the invariant term-scoping gave
        by accident, now enforced where it belongs."""
        gen = TimetableGenerator(self.graph["year"], self.graph["term"])
        first = gen.generate_schedule(created_by=self.admin)
        first.publish()

        replacement = Schedule.objects.create(
            name=f"regen-replacement-{self.uid}",
            academic_year=self.graph["year"],
            term=self.graph["term"],
            status="DRAFT",
            created_by=self.admin,
        )
        replacement.publish()

        first.refresh_from_db()
        self.assertEqual(first.status, "DRAFT", "the old plan must step down")
        self.assertEqual(
            Schedule.objects.filter(
                term=self.graph["term"], shift=replacement.shift, status="PUBLISHED"
            ).count(),
            1,
            "a term/shift must have exactly one live timetable",
        )
