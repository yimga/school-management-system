from decimal import Decimal
from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.people.models import StudentProfile, StudentGuardian
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import ReferralReward
from apps.platform_runtime.helpers import get_platform_site_settings_record


class ReferralRewardTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        spec = Specialty.objects.create(name="General", code="GEN", department=dept)
        classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=self.year,
            department=dept,
        )
        self.student = StudentProfile.objects.create(
            first_name="Learner",
            last_name="One",
            student_code="STD200",
            academic_year=self.year,
            classroom=classroom,
            specialty=spec,
        )
        self.parent = User.objects.create_user(username="parent2", password="pass")
        self.parent.role = User.Role.PARENT
        self.parent.save(update_fields=["role"])
        self.guardian = StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
        )

    def test_referral_reward_defaults_and_mark_paid(self):
        site = get_platform_site_settings_record(create=True)
        site.referral_bonus_amount = Decimal("150.00")
        site.save(update_fields=["referral_bonus_amount"])

        reward = ReferralReward.objects.create(
            student=self.student,
            guardian=self.guardian,
            amount=site.referral_bonus_amount,
            description="Referral reward",
            awarded_by=self.parent,
        )

        self.assertEqual(reward.status, ReferralReward.Status.PENDING)
        self.assertEqual(str(reward), f"{self.student} referral reward ({reward.amount})")
        reward.mark_paid()
        self.assertEqual(reward.status, ReferralReward.Status.PAID)
