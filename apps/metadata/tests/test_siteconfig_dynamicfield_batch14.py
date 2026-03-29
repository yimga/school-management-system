"""Batch 14: metadata DynamicField* runtime (post–Phase 5b legacy table retire)."""

from django.test import TestCase

from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import get_dynamic_field_map
from apps.metadata.siteconfig_dynamicfield_sync import run_full_sync
from apps.people.models import StudentProfile
from apps.schools.models import School


class SiteconfigDynamicFieldSyncRetirementTests(TestCase):
    def test_run_full_sync_is_noop_with_retirement_warning(self):
        stats = run_full_sync(dry_run=False)
        self.assertEqual(stats.definition_rows_seen, 0)
        self.assertEqual(stats.value_rows_seen, 0)
        self.assertEqual(stats.definitions_upserted, 0)
        self.assertEqual(stats.values_upserted, 0)
        self.assertTrue(any("0168" in w for w in stats.warnings))


class MetadataDynamicFieldMapTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="MD School",
            slug="md-school",
            subdomain="md-school",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="M",
            last_name="D",
            student_code="MD-1",
        )

    def test_get_dynamic_field_map_reads_metadata_only(self):
        DynamicFieldDefinition.objects.create(
            entity_type="people.studentprofile",
            field_key="nick",
            label="Nick",
            data_type="string",
            school=self.school,
            is_active=True,
            required=False,
        )
        DynamicFieldValue.objects.create(
            school=self.school,
            entity_type="people.studentprofile",
            entity_id=str(self.student.pk),
            field_key="nick",
            value_json={"v": "meta-only"},
        )
        payload = get_dynamic_field_map(self.student)
        self.assertEqual(payload.get("nick"), "meta-only")

    def test_metadata_wins_on_duplicate_key_resolution_order(self):
        DynamicFieldDefinition.objects.create(
            entity_type="people.studentprofile",
            field_key="dup",
            label="D",
            data_type="string",
            school=self.school,
            is_active=True,
            required=False,
        )
        DynamicFieldValue.objects.create(
            school=self.school,
            entity_type="people.studentprofile",
            entity_id=str(self.student.pk),
            field_key="dup",
            value_json={"v": "winner"},
        )
        payload = get_dynamic_field_map(self.student)
        self.assertEqual(payload.get("dup"), "winner")
