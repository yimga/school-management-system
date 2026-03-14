from django.test import TestCase

from apps.metadata.models import (
    DynamicFieldDefinition,
    DynamicFieldValue,
    EntityCatalogEntry,
    ENTITY_CATALOG_LIFECYCLE_DEPRECATED,
    ENTITY_CATALOG_LIFECYCLE_DRAFT,
    FieldCatalogEntry,
    MetadataDependency,
)
from apps.metadata.services import (
    build_metadata_blast_radius,
    export_entity_catalog_bundle,
    get_package_lineage_registry,
    get_downstream_dependencies,
    get_dynamic_field_map,
    get_dynamic_field_value,
    set_dynamic_field_value,
    summarize_dependency_consumers,
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

    def test_export_entity_catalog_bundle_active_only_excludes_draft_deprecated(self):
        """Default active_only=True exposes only active lifecycle entries."""
        EntityCatalogEntry.objects.create(
            code="draft_entity",
            name="Draft Entity",
            lifecycle_state=ENTITY_CATALOG_LIFECYCLE_DRAFT,
        )
        EntityCatalogEntry.objects.create(
            code="deprecated_entity",
            name="Deprecated Entity",
            lifecycle_state=ENTITY_CATALOG_LIFECYCLE_DEPRECATED,
        )
        bundle = export_entity_catalog_bundle()
        codes = [e["code"] for e in bundle["entities"]]
        self.assertIn("student", codes)
        self.assertNotIn("draft_entity", codes)
        self.assertNotIn("deprecated_entity", codes)

    def test_export_entity_catalog_bundle_active_only_false_includes_all(self):
        """active_only=False includes draft and deprecated entries."""
        EntityCatalogEntry.objects.create(
            code="draft_entity",
            name="Draft Entity",
            lifecycle_state=ENTITY_CATALOG_LIFECYCLE_DRAFT,
        )
        bundle = export_entity_catalog_bundle(active_only=False)
        codes = [e["code"] for e in bundle["entities"]]
        self.assertIn("student", codes)
        self.assertIn("draft_entity", codes)

    def test_summarize_dependency_consumers_groups_by_consumer(self):
        MetadataDependency.objects.create(
            consumer_type="api",
            consumer_code="api:student-record",
            field=self.field,
        )

        rows = summarize_dependency_consumers()

        self.assertTrue(any(row["consumer_code"] == "principal_home" for row in rows))
        api_row = next(row for row in rows if row["consumer_code"] == "api:student-record")
        self.assertEqual(api_row["entity_codes"], ["student"])
        self.assertEqual(api_row["field_names"], ["admission_number"])

    def test_build_metadata_blast_radius_counts_consumers(self):
        MetadataDependency.objects.create(
            consumer_type="template",
            consumer_code="template:student-card",
            field=self.field,
        )

        blast_radius = build_metadata_blast_radius(entity_codes=["student"])

        self.assertEqual(blast_radius["consumer_count"], 2)
        self.assertEqual(blast_radius["consumer_type_counts"]["dashboard"], 1)
        self.assertEqual(blast_radius["consumer_type_counts"]["template"], 1)

    def test_get_package_lineage_registry_includes_rollback_events(self):
        from apps.packages.engine import apply_package, rollback
        from apps.packages.models import InstalledPackage

        result = apply_package(
            tenant_id=None,
            package_id="metadata-lineage-pack",
            version="1.0",
            payload_sections={
                "dashboard": {
                    "dashboards": [
                        {
                            "code": "principal-home",
                            "entity_code": "student",
                            "field_names": ["admission_number"],
                        }
                    ]
                }
            },
            actor_id=None,
        )
        rollback(InstalledPackage.objects.get(pk=result["installed_id"]), actor_id=None)

        rows = get_package_lineage_registry(package_id="metadata-lineage-pack")

        self.assertEqual(rows[0]["package_id"], "metadata-lineage-pack")
        self.assertEqual(rows[0]["rollback_event_count"], 1)
        self.assertGreaterEqual(rows[0]["blast_radius"]["consumer_count"], 1)
