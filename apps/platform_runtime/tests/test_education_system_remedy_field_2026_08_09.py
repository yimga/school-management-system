"""The tenant 'direct remedy' repair control for the *Education system* registry
field must read and write ``School.primary_sector`` (the education-system TYPE /
sector code — PUBLIC/PRIVATE/IB/... validated against EducationSystemTypeRegistry),
NOT ``School.sub_system`` (the language sub-system FR/EN/INT).

Before the fix the control read + wrote ``sub_system``: picking a curriculum/sector
code from the registry-backed dropdown wrote it into the language sub-system field
(whose choices are FR/EN/INT), corrupting it, while the Setup/Launch alignment row
— which validates against EducationSystemTypeRegistry — could never line up. These
tests fail on the old wrong-field wiring and pass once read/write target
``primary_sector``.
"""

from django.test import TestCase

from apps.platform_runtime.tenant_direct_remedies import (
    apply_direct_remedy,
    current_remedy_value,
)
from apps.registries.models import EducationSystemTypeRegistry
from apps.schools.models import School


class EducationSystemRemedyFieldTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Remedy Sector", slug="remedy-sector")
        EducationSystemTypeRegistry.objects.update_or_create(
            code="PRIVATE",
            defaults={"name": "Private / independent", "is_active": True},
        )

    def test_apply_writes_primary_sector_and_leaves_language_subsystem_intact(self):
        # A distinct, valid language sub-system that must survive the repair.
        self.school.sub_system = "FR"
        self.school.primary_sector = ""
        self.school.save(update_fields=["sub_system", "primary_sector"])

        apply_direct_remedy(
            self.school, field_key="education_system", value="PRIVATE", actor=None
        )
        self.school.refresh_from_db()

        # The chosen education-system TYPE lands on the sector field...
        self.assertEqual(self.school.primary_sector, "PRIVATE")
        # ...and the language sub-system is NOT clobbered with a curriculum code.
        self.assertEqual(self.school.sub_system, "FR")

    def test_current_value_reads_primary_sector(self):
        self.school.sub_system = "EN"
        self.school.primary_sector = "PRIVATE"
        self.school.save(update_fields=["sub_system", "primary_sector"])
        # The pre-filled control value reflects the sector, never the language.
        self.assertEqual(
            current_remedy_value(self.school, "education_system"), "PRIVATE"
        )
