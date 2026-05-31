"""Academic structure breadcrumb extension (Phase 3C)."""

from datetime import date

from django.test import TestCase

from apps.academics.academic_structure import AcademicStructureNode
from apps.academics.models import AcademicYear
from apps.schools.models import School
from apps.siteconfig.terminology_service import (
    academic_structure_breadcrumb,
    matrix_institution_vocabulary_with_structure,
)


class TerminologyStructureBreadcrumbTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Breadcrumb School",
            slug="breadcrumb-school",
            subdomain="breadcrumb-school",
            country_code="CM",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        AcademicStructureNode.objects.create(
            school=self.school,
            node_type=AcademicStructureNode.NodeType.CYCLE,
            local_label="Primaire",
            sort_order=0,
            structural_metadata={"pack_school_type": "primaire"},
        )

    def test_academic_structure_breadcrumb_lists_nodes(self):
        trail = academic_structure_breadcrumb(self.school)
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["label"], "Primaire")
        self.assertEqual(trail[0]["node_type"], "cycle")

    def test_matrix_vocabulary_includes_breadcrumb(self):
        vocab = matrix_institution_vocabulary_with_structure("CM", self.school)
        self.assertTrue(vocab.get("country_code"))
        self.assertIn("academic_structure_breadcrumb", vocab)
        self.assertEqual(len(vocab["academic_structure_breadcrumb"]), 1)
