from django.test import TestCase

from apps.metadata.models import (
    DynamicFieldDefinition,
    DynamicFieldValue,
    EntityCatalogEntry,
    FieldCatalogEntry,
    MetadataDependency,
)
from apps.metadata.services import (
    export_entity_catalog_bundle,
    get_downstream_dependencies,
    get_dynamic_field_map,
    get_dynamic_field_value,
    set_dynamic_field_value,
)
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


class LineageAndCatalogExportTests(TestCase):
    """Tests for lineage-first rule and catalog bundle export (Workstream I)."""

    def setUp(self):
        self.entity = EntityCatalogEntry.objects.create(
            code="student",
            name="Student",
            description="Student profile",
            owning_app="people",
            model_label="people.StudentProfile",
            is_core=True,
        )
        self.field = FieldCatalogEntry.objects.create(
            entity=self.entity,
            field_name="admission_number",
            label="Admission number",
            data_type="string",
            is_custom=False,
            defined_in_app="people",
            source="seed_entity_catalog",
        )
        self.dep = MetadataDependency.objects.create(
            consumer_type="dashboard",
            consumer_code="principal_home",
            field=self.field,
        )

    def test_get_downstream_dependencies_by_entity_code(self):
        deps = get_downstream_dependencies(entity_code="student")
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["consumer_type"], "dashboard")
        self.assertEqual(deps[0]["consumer_code"], "principal_home")
        self.assertEqual(deps[0]["entity_code"], "student")
        self.assertEqual(deps[0]["field_name"], "admission_number")

    def test_get_downstream_dependencies_by_field_id(self):
        deps = get_downstream_dependencies(field_id=self.field.id)
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["consumer_code"], "principal_home")

    def test_get_downstream_dependencies_empty_when_no_match(self):
        self.assertEqual(get_downstream_dependencies(entity_code="nonexistent"), [])
        self.assertEqual(get_downstream_dependencies(field_id=99999), [])

    def test_export_entity_catalog_bundle_includes_entities_and_fields(self):
        bundle = export_entity_catalog_bundle(entity_codes=["student"])
        self.assertEqual(bundle["version"], "1")
        self.assertEqual(len(bundle["entities"]), 1)
        ent = bundle["entities"][0]
        self.assertEqual(ent["code"], "student")
        self.assertEqual(ent["name"], "Student")
        self.assertIn("fields", ent)
        fields = ent["fields"]
        self.assertTrue(any(f["field_name"] == "admission_number" for f in fields))

    def test_export_entity_catalog_bundle_can_include_dependencies(self):
        bundle = export_entity_catalog_bundle(
            entity_codes=["student"],
            include_dependencies=True,
        )
        ent = bundle["entities"][0]
        self.assertIn("dependencies", ent)
        self.assertTrue(
            any(
                d["consumer_code"] == "principal_home" and d["field_name"] == "admission_number"
                for d in ent["dependencies"]
            )
        )
