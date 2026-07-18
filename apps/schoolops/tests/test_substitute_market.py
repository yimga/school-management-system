"""Substitute market lock + candidate wiring tests (metric 12)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.academics.models import Department
from apps.people.models import TeacherProfile
from apps.schoolops.substitute_handover import (
    find_substitute_candidates,
    select_qualified_or_override,
)
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


class SubstituteQualificationFilterTests(TestCase):
    """Qualification must be a REAL filter through the PROD path (metric 12).

    Fails-first against HEAD: ``find_substitute_candidates`` never passed the
    absent teacher's department to the matcher, so ``required_department_id``
    stayed "" and the qualification tier was inert — a higher-priority
    OUT-OF-department substitute outranked an in-department one, and no
    ``qualified`` flag / ``select_qualified_or_override`` existed at all.
    """

    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Qualification School",
            slug="qualification-school",
            subdomain="qualification-school",
            is_active=True,
        )
        self.math = Department.objects.create(
            school=self.school, name="Math", code="MATH"
        )
        self.science = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        self.absent = User.objects.create_user(
            username="absent_math_teacher",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.qualified_sub = User.objects.create_user(
            username="qualified_math_sub",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.unqualified_sub = User.objects.create_user(
            username="unqualified_science_sub",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(
            school=self.school,
            user=self.absent,
            department=self.math,
            is_active=True,
            phone="+237600000010",
        )
        # In-department (qualified) but LOW priority.
        TeacherProfile.objects.create(
            school=self.school,
            user=self.qualified_sub,
            department=self.math,
            is_active=True,
            phone="+237600000011",
            custom_attributes={"substitute_priority": 0},
        )
        # Out-of-department (unqualified) but FAR HIGHER priority — under the
        # old code this teacher would rank first and be broadcast to.
        TeacherProfile.objects.create(
            school=self.school,
            user=self.unqualified_sub,
            department=self.science,
            is_active=True,
            phone="+237600000012",
            custom_attributes={"substitute_priority": 99},
        )
        self.work_date = date(2026, 6, 26)

    def test_prod_path_ranks_qualified_above_higher_priority_unqualified(self):
        ranked = find_substitute_candidates(
            school=self.school,
            absent_teacher_user_id=self.absent.pk,
            work_date=self.work_date,
        )
        by_id = {c.teacher_id: c for c in ranked}
        # The in-department sub is a HARD tier above the out-of-department one
        # despite the latter's far higher priority.
        self.assertEqual(ranked[0].teacher_id, str(self.qualified_sub.pk))
        self.assertTrue(by_id[str(self.qualified_sub.pk)].qualified)
        self.assertFalse(by_id[str(self.unqualified_sub.pk)].qualified)
        self.assertLess(
            ranked.index(by_id[str(self.qualified_sub.pk)]),
            ranked.index(by_id[str(self.unqualified_sub.pk)]),
        )

    def test_broadcast_targets_exclude_unqualified_when_qualified_exists(self):
        ranked = find_substitute_candidates(
            school=self.school,
            absent_teacher_user_id=self.absent.pk,
            work_date=self.work_date,
        )
        target_ids = {c.teacher_id for c in select_qualified_or_override(ranked)}
        self.assertIn(str(self.qualified_sub.pk), target_ids)
        self.assertNotIn(str(self.unqualified_sub.pk), target_ids)

    def test_override_tier_used_only_when_no_qualified_substitute(self):
        # Remove the only qualified sub → the override tier surfaces the
        # out-of-department teacher rather than stranding the school.
        TeacherProfile.objects.filter(user=self.qualified_sub).update(is_active=False)
        ranked = find_substitute_candidates(
            school=self.school,
            absent_teacher_user_id=self.absent.pk,
            work_date=self.work_date,
        )
        targets = select_qualified_or_override(ranked)
        target_ids = {c.teacher_id for c in targets}
        self.assertIn(str(self.unqualified_sub.pk), target_ids)
        self.assertTrue(all(not c.qualified for c in targets))
