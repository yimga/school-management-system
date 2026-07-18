"""SCRATCH fails-first proof for M12 (delete after use).

HEAD-compatible: uses ONLY `find_substitute_candidates` (unchanged signature),
so it imports and runs against both HEAD source and the fixed source. Asserts
the in-department (qualified) sub ranks first even though the out-of-department
sub has far higher priority. Against HEAD this FAILS because the prod matcher
never threads the absent teacher's department.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.academics.models import Department
from apps.people.models import TeacherProfile
from apps.schoolops.substitute_handover import find_substitute_candidates
from apps.schools.models import School

User = get_user_model()


class M12FailsFirstScratch(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="M12 Scratch School",
            slug="m12-scratch-school",
            subdomain="m12-scratch-school",
            is_active=True,
        )
        math = Department.objects.create(school=self.school, name="Math", code="MATH")
        science = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        self.absent = User.objects.create_user(
            username="m12s_absent", password="p", role=User.Role.TEACHER
        )
        self.qualified = User.objects.create_user(
            username="m12s_qualified", password="p", role=User.Role.TEACHER
        )
        self.unqualified = User.objects.create_user(
            username="m12s_unqualified", password="p", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(
            school=self.school, user=self.absent, department=math,
            is_active=True, phone="+237600000010",
        )
        TeacherProfile.objects.create(
            school=self.school, user=self.qualified, department=math,
            is_active=True, phone="+237600000011",
            custom_attributes={"substitute_priority": 0},
        )
        TeacherProfile.objects.create(
            school=self.school, user=self.unqualified, department=science,
            is_active=True, phone="+237600000012",
            custom_attributes={"substitute_priority": 99},
        )

    def test_qualified_sub_ranks_first(self):
        ranked = find_substitute_candidates(
            school=self.school,
            absent_teacher_user_id=self.absent.pk,
            work_date=date(2026, 6, 26),
        )
        self.assertEqual(ranked[0].teacher_id, str(self.qualified.pk))
