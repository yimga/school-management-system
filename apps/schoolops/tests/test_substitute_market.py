"""Substitute market lock + candidate wiring tests (metric 12)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.academics.models import Department
from apps.people.models import TeacherProfile
from apps.schoolops.substitute_handover import find_substitute_candidates
from apps.schoolops.substitute_market import (
    ShiftAlreadyBooked,
    acquire_shift_slot_lock,
    claim_shift,
    open_shift,
)
from apps.schools.models import School

User = get_user_model()


class SubstituteMarketTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Substitute Market School",
            slug="substitute-market-school",
            subdomain="substitute-market-school",
            is_active=True,
        )
        self.absent = User.objects.create_user(
            username="absent_teacher",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.sub_a = User.objects.create_user(
            username="sub_teacher_a",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.sub_b = User.objects.create_user(
            username="sub_teacher_b",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        dept = Department.objects.create(school=self.school, name="STEM", code="STEM")
        TeacherProfile.objects.create(
            school=self.school,
            user=self.absent,
            department=dept,
            is_active=True,
            phone="+237600000001",
        )
        TeacherProfile.objects.create(
            school=self.school,
            user=self.sub_a,
            department=dept,
            is_active=True,
            phone="+237600000002",
            custom_attributes={"substitute_priority": 5},
        )
        TeacherProfile.objects.create(
            school=self.school,
            user=self.sub_b,
            department=dept,
            is_active=True,
            phone="+237600000003",
            custom_attributes={"substitute_priority": 1},
        )
        self.work_date = date(2026, 6, 26)

    def test_slot_lock_is_exclusive(self):
        self.assertTrue(
            acquire_shift_slot_lock(
                school_id=self.school.pk,
                work_date=self.work_date,
                period_label="Period 1",
            )
        )
        self.assertFalse(
            acquire_shift_slot_lock(
                school_id=self.school.pk,
                work_date=self.work_date,
                period_label="Period 1",
            )
        )

    def test_open_shift_raises_when_slot_locked(self):
        open_shift(
            school=self.school,
            absent_teacher_id=self.absent.pk,
            work_date=self.work_date,
            publish_fn=lambda _payload: None,
        )
        with self.assertRaises(ShiftAlreadyBooked):
            open_shift(
                school=self.school,
                absent_teacher_id=self.absent.pk,
                work_date=self.work_date,
                publish_fn=lambda _payload: None,
            )

    def test_open_shift_publishes_with_candidate_count(self):
        published = []

        shift = open_shift(
            school=self.school,
            absent_teacher_id=self.absent.pk,
            work_date=self.work_date,
            publish_fn=published.append,
        )
        self.assertEqual(shift.status, "open")
        self.assertEqual(len(published), 1)
        self.assertGreaterEqual(published[0].get("candidate_count", 0), 1)

    def test_find_substitute_candidates_ranks_by_priority(self):
        ranked = find_substitute_candidates(
            school=self.school,
            absent_teacher_user_id=self.absent.pk,
            work_date=self.work_date,
        )
        ids = [c.teacher_id for c in ranked]
        self.assertIn(str(self.sub_a.pk), ids)
        self.assertIn(str(self.sub_b.pk), ids)
        self.assertEqual(ids[0], str(self.sub_a.pk))

    def test_claim_shift_persists_substitute_cover(self):
        shift = open_shift(
            school=self.school,
            absent_teacher_id=self.absent.pk,
            work_date=self.work_date,
            period_label="Period 2",
            publish_fn=lambda _payload: None,
        )
        cover_id = claim_shift(
            school=self.school,
            shift_id=shift.shift_id,
            substitute_teacher_id=self.sub_a.pk,
            publish_fn=lambda _payload: None,
        )
        self.assertGreater(cover_id, 0)
        from apps.schoolops.models import SubstituteCover

        cover = SubstituteCover.objects.get(pk=cover_id)
        self.assertEqual(cover.covering_teacher_id, self.sub_a.pk)
