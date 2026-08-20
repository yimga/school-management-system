"""M33 — a purchase order must be DERIVED from class configuration, not typed in.

Each test here is the kind that would have failed before the feature existed: they
assert the arithmetic that connects a timetable to an order, not merely that rows can
be created.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.people.models import Enrollment, StudentProfile
from apps.schoolops.models import (
    InventoryItem,
    PurchaseOrder,
    SupplyRequirement,
    Vendor,
    VendorProduct,
)
from apps.schoolops.procurement_services import (
    generate_purchase_orders_from_class_config,
    tenant_gmv,
)
from apps.schools.models import School


class ProcurementFromClassConfigTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Procurement Test School",
            slug="procurement-test",
            subdomain="procurement-test",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.dept, name="General", code="GEN-PROC"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 4B",
            code="F4B",
        )
        self.chemistry = Subject.objects.create(
            school=self.school, name="Chemistry", category=Subject.Category.GENERAL
        )
        self.assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.chemistry,
            coefficient=1,
        )
        self.vendor = Vendor.objects.create(
            school=self.school, name="LabCo", is_certified=True, currency="USD"
        )
        self.goggles = VendorProduct.objects.create(
            school=self.school,
            vendor=self.vendor,
            sku="GOG-1",
            name="Safety goggles",
            unit_price=Decimal("5.00"),
        )

    def _enrol(self, count):
        for i in range(count):
            student = StudentProfile.objects.create(
                school=self.school,
                first_name=f"S{i}",
                last_name="Test",
                student_code=f"PROC-{i}",
                academic_year=self.year,
                classroom=self.classroom,
                specialty=self.specialty,
                is_active=True,
            )
            Enrollment.objects.create(
                school=self.school,
                student=student,
                academic_year=self.year,
                classroom=self.classroom,
                entry_date=self.year.start_date,
            )

    def test_quantity_is_derived_from_enrolment_not_guessed(self):
        """One goggle per student × 7 enrolled students = 7 goggles."""
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(7)

        orders = generate_purchase_orders_from_class_config(self.school)

        self.assertEqual(len(orders), 1)
        line = orders[0].lines.get()
        self.assertEqual(line.quantity, 7)
        self.assertEqual(line.line_total, Decimal("35.00"))
        self.assertEqual(orders[0].subtotal, Decimal("35.00"))
        self.assertEqual(orders[0].source, PurchaseOrder.Source.CLASS_CONFIG)
        self.assertEqual(orders[0].status, PurchaseOrder.Status.DRAFT)

    def test_line_records_which_class_drove_it(self):
        """An operator must be able to see WHY a quantity was proposed."""
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(3)

        orders = generate_purchase_orders_from_class_config(self.school)

        line = orders[0].lines.get()
        self.assertEqual(line.subject_assignment_id, self.assignment.pk)

    def test_stock_on_hand_is_netted_off(self):
        """Holding 4 of the 10 needed must order 6, not 10."""
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(10)
        InventoryItem.objects.create(
            school=self.school, name="Safety goggles", quantity=4
        )

        orders = generate_purchase_orders_from_class_config(self.school)

        self.assertEqual(orders[0].lines.get().quantity, 6)

    def test_fully_stocked_generates_nothing(self):
        """No order at all is the correct answer when stock already covers demand."""
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(5)
        InventoryItem.objects.create(
            school=self.school, name="Safety goggles", quantity=50
        )

        self.assertEqual(generate_purchase_orders_from_class_config(self.school), [])

    def test_no_enrolment_means_no_order(self):
        """A configured requirement with an empty class must not invent demand."""
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self.assertEqual(generate_purchase_orders_from_class_config(self.school), [])

    def test_orders_are_grouped_one_per_vendor(self):
        """Two products from one vendor belong on ONE order."""
        beakers = VendorProduct.objects.create(
            school=self.school,
            vendor=self.vendor,
            sku="BEAK-1",
            name="Beaker",
            unit_price=Decimal("2.50"),
        )
        other_vendor = Vendor.objects.create(
            school=self.school, name="BookCo", currency="USD"
        )
        books = VendorProduct.objects.create(
            school=self.school,
            vendor=other_vendor,
            sku="BK-1",
            name="Workbook",
            unit_price=Decimal("10.00"),
        )
        for product in (self.goggles, beakers, books):
            SupplyRequirement.objects.create(
                school=self.school,
                subject=self.chemistry,
                product=product,
                quantity_per_student=Decimal("1.00"),
            )
        self._enrol(2)

        orders = generate_purchase_orders_from_class_config(self.school)

        self.assertEqual(len(orders), 2)
        by_vendor = {o.vendor.name: o for o in orders}
        self.assertEqual(by_vendor["LabCo"].lines.count(), 2)
        self.assertEqual(by_vendor["BookCo"].lines.count(), 1)

    def test_gmv_excludes_drafts(self):
        """GMV that counted proposals would flatter the platform, not describe it."""
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(4)
        orders = generate_purchase_orders_from_class_config(self.school)

        self.assertEqual(tenant_gmv(self.school), Decimal("0.00"))

        orders[0].status = PurchaseOrder.Status.SUBMITTED
        orders[0].save(update_fields=["status"])
        self.assertEqual(tenant_gmv(self.school), orders[0].total)

    def test_another_school_is_never_touched(self):
        """Generation for school A must not read or write school B's rows."""
        other = School.objects.create(
            name="Other School",
            slug="procurement-other",
            subdomain="procurement-other",
            is_active=True,
        )
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.chemistry,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(3)

        generate_purchase_orders_from_class_config(self.school)

        self.assertEqual(PurchaseOrder.objects.filter(school=other).count(), 0)
        self.assertEqual(tenant_gmv(other), Decimal("0.00"))
        self.assertEqual(
            generate_purchase_orders_from_class_config(other), []
        )
