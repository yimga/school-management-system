"""Tuition PPP opt-in applies CountryMultiplier to fee invoice lines."""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.finance.models import ComplianceProfile, FeeItem, FeePlan, InvoiceLine
from apps.finance.services import create_fee_invoices
from apps.finance.tuition_pricing import localized_tuition_amount, tuition_ppp_enabled_for_school
from apps.people.models import StudentProfile
from apps.registries.models import CountryRegistry
from apps.siteconfig.country_multiplier_seed import seed_country_multipliers
from apps.schools.models import School


class TuitionPppTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="IN", defaults={"name": "India"})
        seed_country_multipliers(country_codes=["IN"])
        self.school = School.objects.create(
            name="PPP Tuition School",
            slug="ppp-tuition-school",
            subdomain="ppp-tuition-school",
            country_code="IN",
            is_active=True,
            settings={"finance_apply_ppp_to_tuition": True},
        )
        self.profile = ComplianceProfile.objects.create(
            name="IN Finance",
            country_code="IN",
            currency_code="INR",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        specialty = Specialty.objects.create(
            school=self.school, department=department, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=department,
            name="10A",
            code="10A",
        )
        self.plan = FeePlan.objects.create(
            school=self.school,
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            name="Annual tuition",
        )
        FeeItem.objects.create(
            plan=self.plan,
            name="Tuition",
            amount=Decimal("1000.00"),
            item_type=FeeItem.ItemType.TUITION,
        )
        FeeItem.objects.create(
            plan=self.plan,
            name="PTA levy",
            amount=Decimal("50.00"),
            item_type=FeeItem.ItemType.PTA,
        )
        StudentProfile.objects.create(
            school=self.school,
            first_name="Priya",
            last_name="Sharma",
            student_code="IN-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            is_active=True,
        )

    def test_opt_in_flag_reads_school_settings(self):
        self.assertTrue(tuition_ppp_enabled_for_school(self.school))
        self.school.settings = {}
        self.school.save(update_fields=["settings"])
        self.assertFalse(tuition_ppp_enabled_for_school(self.school))

    def test_localized_tuition_uses_multiplier(self):
        scaled = localized_tuition_amount(
            school=self.school,
            base_amount=Decimal("1000.00"),
            item_type=FeeItem.ItemType.TUITION,
        )
        self.assertEqual(scaled, Decimal("280.00"))

    def test_create_fee_invoices_applies_ppp_to_tuition_only(self):
        invoices = create_fee_invoices(plan=self.plan, profile=self.profile)
        self.assertEqual(len(invoices), 1)
        lines = list(InvoiceLine.objects.filter(invoice=invoices[0]).order_by("description"))
        tuition_line = next(l for l in lines if l.description == "Tuition")
        pta_line = next(l for l in lines if l.description == "PTA levy")
        self.assertEqual(tuition_line.amount, Decimal("280.00"))
        self.assertEqual(pta_line.amount, Decimal("50.00"))

    def test_without_opt_in_base_amount_preserved(self):
        self.school.settings = {}
        self.school.save(update_fields=["settings"])
        invoices = create_fee_invoices(plan=self.plan, profile=self.profile)
        tuition_line = InvoiceLine.objects.get(
            invoice=invoices[0], description="Tuition"
        )
        self.assertEqual(tuition_line.amount, Decimal("1000.00"))


class TuitionPppNigeriaSoakTests(TestCase):
    """Metric #6 — tuition PPP soak for NG (0.35×) alongside IN coverage."""

    def setUp(self):
        CountryRegistry.objects.get_or_create(code="NG", defaults={"name": "Nigeria"})
        seed_country_multipliers(country_codes=["NG"])
        self.school = School.objects.create(
            name="PPP NG School",
            slug="ppp-ng-school",
            subdomain="ppp-ng-school",
            country_code="NG",
            is_active=True,
            settings={"finance_apply_ppp_to_tuition": True},
        )
        self.profile = ComplianceProfile.objects.create(
            name="NG Finance",
            country_code="NG",
            currency_code="NGN",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        specialty = Specialty.objects.create(
            school=self.school, department=department, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=department,
            name="10A",
            code="10A",
        )
        self.plan = FeePlan.objects.create(
            school=self.school,
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            name="Annual tuition",
        )
        FeeItem.objects.create(
            plan=self.plan,
            name="Tuition",
            amount=Decimal("1000.00"),
            item_type=FeeItem.ItemType.TUITION,
        )
        FeeItem.objects.create(
            plan=self.plan,
            name="PTA levy",
            amount=Decimal("50.00"),
            item_type=FeeItem.ItemType.PTA,
        )
        StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Okafor",
            student_code="NG-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            is_active=True,
        )

    def test_nigeria_tuition_scales_at_point_three_five(self):
        invoices = create_fee_invoices(plan=self.plan, profile=self.profile)
        self.assertEqual(len(invoices), 1)
        lines = list(InvoiceLine.objects.filter(invoice=invoices[0]).order_by("description"))
        tuition_line = next(l for l in lines if l.description == "Tuition")
        pta_line = next(l for l in lines if l.description == "PTA levy")
        self.assertEqual(tuition_line.amount, Decimal("350.00"))
        self.assertEqual(pta_line.amount, Decimal("50.00"))
