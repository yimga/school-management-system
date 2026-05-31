"""Tests for academic structure provisioning (global kernel Phase 3)."""

from datetime import date

from django.test import TestCase

from apps.academics.academic_structure import AcademicStructureNode
from apps.academics.models import AcademicYear, Classroom, Department
from apps.academics.structure_provisioning import provision_academic_structure_for_school
from apps.schools.models import School


class AcademicStructureProvisioningTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Structure Test School",
            slug="structure-test",
            subdomain="structure-test",
            country_code="CM",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )

    def test_provision_creates_cycle_nodes_idempotent(self):
        first = provision_academic_structure_for_school(
            self.school,
            school_type_codes=["primaire"],
            academic_year=self.year,
        )
        self.assertGreaterEqual(first["created_nodes"], 1)
        nodes_after_first = AcademicStructureNode.objects.filter(school=self.school).count()

        second = provision_academic_structure_for_school(
            self.school,
            school_type_codes=["primaire"],
            academic_year=self.year,
        )
        self.assertEqual(second["created_nodes"], 0)
        self.assertEqual(
            AcademicStructureNode.objects.filter(school=self.school).count(),
            nodes_after_first,
        )

    def test_secondary_sector_creates_classroom_leaf(self):
        provision_academic_structure_for_school(
            self.school,
            school_type_codes=["lycee-2nd-cycle"],
            academic_year=self.year,
        )
        self.assertTrue(
            Classroom.objects.filter(school=self.school, academic_year=self.year).exists()
        )
        self.assertTrue(
            AcademicStructureNode.objects.filter(
                school=self.school,
                node_type=AcademicStructureNode.NodeType.CLASSROOM_LEAF,
            ).exists()
        )
        self.assertTrue(
            Department.objects.filter(school=self.school).exists()
        )
