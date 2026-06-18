"""Persona onboarding + safeguarding + HR wizard domain writer tests (batch 4)."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.payroll.models import EmploymentContract, PayrollEmployee
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.wizard_resolvers import (
    write_hr_absence,
    write_hr_contract,
    write_parent_children,
    write_parent_profile,
    write_safeguarding_anchor,
    write_safeguarding_categories,
    write_staff_profile,
    write_staff_schedule,
)


class SafeguardingWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="GB", defaults={"name": "United Kingdom"})
        self.school = School.objects.create(
            name="Safeguard School",
            slug="safeguard-school",
            subdomain="safeguard-school",
            country_code="GB",
            is_active=True,
        )

    def test_categories_and_anchor_persisted(self):
        write_safeguarding_categories(
            school=self.school,
            wizard_key="dynamic_safeguarding_incident_medical",
            step_key="incident_categorization",
            payload={"value": ["physical_abuse", "self_harm"]},
            actor_user_id=1,
        )
        write_safeguarding_anchor(
            school=self.school,
            wizard_key="dynamic_safeguarding_incident_medical",
            step_key="immutable_audit_anchor",
            payload={"value": "append_only_db"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        sg = (self.school.settings or {}).get("safeguarding", {})
        self.assertEqual(sg.get("enabled_categories"), ["physical_abuse", "self_harm"])
        self.assertEqual(sg.get("audit_anchor"), "append_only_db")


class ParentOnboardingWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Parent School",
            slug="parent-school",
            subdomain="parent-school",
            country_code="CM",
            is_active=True,
        )
        User = get_user_model()
        self.parent = User.objects.create_user(
            username="parent1",
            password="x",
            role=User.Role.PARENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            admission_number="ADM-1001",
            first_name="Child",
            last_name="One",
        )

    def test_profile_updates_user_and_links_channel(self):
        link = StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            preferred_contact=StudentGuardian.PreferredContact.EMAIL,
        )
        write_parent_profile(
            school=self.school,
            wizard_key="parent_onboarding",
            step_key="profile_basics",
            payload={
                "full_name": "Jane Parent",
                "preferred_language": "fr",
                "preferred_communication_channel": "whatsapp",
            },
            actor_user_id=self.parent.pk,
        )
        self.parent.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual(self.parent.first_name, "Jane")
        self.assertEqual(self.parent.last_name, "Parent")
        self.assertEqual(self.parent.preferred_language, "fr")
        self.assertEqual(link.preferred_contact, StudentGuardian.PreferredContact.WHATSAPP)

    def test_children_links_by_admission_number(self):
        write_parent_children(
            school=self.school,
            wizard_key="parent_onboarding",
            step_key="linked_children",
            payload={"value": ["ADM-1001"]},
            actor_user_id=self.parent.pk,
        )
        self.assertTrue(
            StudentGuardian.objects.filter(
                guardian_user=self.parent,
                student=self.student,
            ).exists()
        )


class StaffOnboardingWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Staff School",
            slug="staff-school",
            subdomain="staff-school",
            country_code="CM",
            is_active=True,
        )
        User = get_user_model()
        self.teacher = User.objects.create_user(
            username="teacher1",
            password="x",
            role=User.Role.TEACHER,
        )

    def test_staff_profile_and_schedule(self):
        write_staff_profile(
            school=self.school,
            wizard_key="staff_onboarding",
            step_key="profile_basics",
            payload={"full_name": "Sam Staff", "employee_id": "EMP-42"},
            actor_user_id=self.teacher.pk,
        )
        write_staff_schedule(
            school=self.school,
            wizard_key="staff_onboarding",
            step_key="schedule_preferences",
            payload={"standard_hours_per_week": 35, "preferred_break_minutes": 45},
            actor_user_id=self.teacher.pk,
        )
        self.teacher.refresh_from_db()
        profile = TeacherProfile.objects.get(user=self.teacher)
        employee = PayrollEmployee.objects.get(user=self.teacher)
        contract = EmploymentContract.objects.get(employee=employee, is_active=True)
        self.assertEqual(self.teacher.first_name, "Sam")
        self.assertEqual(profile.staff_id, "EMP-42")
        self.assertEqual(profile.school_id, self.school.pk)
        self.assertEqual(employee.employee_code, "EMP-42")
        self.assertEqual(contract.hours_per_week, Decimal("35"))


class HRPolicyWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="HR School",
            slug="hr-school",
            subdomain="hr-school",
            country_code="CM",
            is_active=True,
        )

    def test_labor_and_absence_policy(self):
        write_hr_contract(
            school=self.school,
            wizard_key="human_capital_shift_substitute_market",
            step_key="labor_contract_profile",
            payload={
                "max_weekly_hours": 40,
                "overtime_threshold_hours": 38,
                "overtime_multiplier": "1.5",
            },
            actor_user_id=1,
        )
        write_hr_absence(
            school=self.school,
            wizard_key="human_capital_shift_substitute_market",
            step_key="absence_logic_toggles",
            payload={
                "emergency_absence_cutoff_time": "08:00",
                "auto_broadcast_to_subs": True,
            },
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        hr = (self.school.settings or {}).get("hr", {})
        self.assertEqual(hr["labor_contract"]["max_weekly_hours"], 40)
        self.assertTrue(hr["absence"]["auto_broadcast_to_subs"])
