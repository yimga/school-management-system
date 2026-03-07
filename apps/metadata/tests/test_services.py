from django.test import TestCase

from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import get_dynamic_field_map, get_dynamic_field_value, set_dynamic_field_value
from apps.people.models import StudentProfile
from apps.schools.models import School


class MetadataServicesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Metadata School",
            slug="metadata-school",
            subdomain="metadata-school",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Meta",
            last_name="Student",
            student_code="META-001",
            custom_attributes={"gpa": 3.2, "allergy": "none"},
        )

    def test_dynamic_value_prefers_metadata_over_legacy_custom_attributes(self):
        set_dynamic_field_value(self.student, "gpa", 3.9, data_type="number")

        self.assertEqual(get_dynamic_field_value(self.student, "gpa"), 3.9)
        payload = get_dynamic_field_map(self.student)
        self.assertEqual(payload["gpa"], 3.9)
        self.assertEqual(payload["allergy"], "none")

    def test_set_dynamic_field_value_creates_definition_and_can_sync_legacy_copy(self):
        set_dynamic_field_value(
            self.student,
            "transportation_zone",
            "north-campus",
            sync_legacy=True,
        )
        self.student.save(update_fields=["custom_attributes"])
        self.student.refresh_from_db()

        self.assertTrue(
            DynamicFieldDefinition.objects.filter(
                school=self.school,
                entity_type="people.studentprofile",
                field_key="transportation_zone",
            ).exists()
        )
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                school=self.school,
                entity_type="people.studentprofile",
                entity_id=str(self.student.pk),
                field_key="transportation_zone",
            ).exists()
        )
        self.assertEqual(self.student.custom_attributes["transportation_zone"], "north-campus")
