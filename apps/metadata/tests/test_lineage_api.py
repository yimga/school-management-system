"""
Tests for §3.3 unified lineage API (usage_registry + package lineage + blast radius).
"""

from django.test import TestCase

from apps.metadata.lineage_api import get_unified_lineage
from apps.metadata.models import (
    EntityCatalogEntry,
    FieldCatalogEntry,
    MetadataDependency,
)


class LineageAPITests(TestCase):
    """Unified lineage get_unified_lineage() contract and aggregation."""

    def setUp(self):
        self.entity = EntityCatalogEntry.objects.create(
            code="student",
            name="Student",
            owning_app="people",
            is_core=True,
        )
        self.field = FieldCatalogEntry.objects.create(
            entity=self.entity,
            field_name="admission_number",
            label="Admission number",
            data_type="string",
            defined_in_app="people",
            source="seed_entity_catalog",
        )
        MetadataDependency.objects.create(
            consumer_type="dashboard",
            consumer_code="principal_home",
            field=self.field,
        )
        MetadataDependency.objects.create(
            consumer_type="template",
            consumer_code="template:student-card",
            field=self.field,
        )

    def test_entity_lineage_returns_downstream_and_blast_radius(self):
        payload = get_unified_lineage(object_type="entity", code="student")
        self.assertEqual(payload["object"]["type"], "entity")
        self.assertEqual(payload["object"]["entity_code"], "student")
        self.assertIn("downstream", payload)
        self.assertIn("blast_radius", payload)
        self.assertIsNotNone(payload["blast_radius"])
        self.assertEqual(payload["blast_radius"]["consumer_count"], 2)
        self.assertEqual(
            payload["downstream_summary"]["consumer_count"],
            2,
        )
        codes = [d["consumer_code"] for d in payload["downstream"]]
        self.assertIn("principal_home", codes)
        self.assertIn("template:student-card", codes)

    def test_field_lineage_returns_downstream_and_blast_radius(self):
        payload = get_unified_lineage(
            object_type="field",
            entity_code="student",
            field_name="admission_number",
        )
        self.assertEqual(payload["object"]["type"], "field")
        self.assertEqual(payload["object"]["entity_code"], "student")
        self.assertEqual(payload["object"]["field_name"], "admission_number")
        self.assertIsNotNone(payload["blast_radius"])
        self.assertEqual(payload["blast_radius"]["consumer_count"], 2)

    def test_entity_lineage_with_entity_code_param(self):
        payload = get_unified_lineage(object_type="entity", entity_code="student")
        self.assertEqual(payload["object"]["entity_code"], "student")
        self.assertGreaterEqual(len(payload["downstream"]), 1)

    def test_unknown_entity_returns_empty_downstream(self):
        payload = get_unified_lineage(object_type="entity", code="nonexistent")
        self.assertEqual(payload["object"].get("entity_code"), "nonexistent")
        self.assertEqual(payload["downstream"], [])
        self.assertIsNotNone(payload["blast_radius"])
        self.assertEqual(payload["blast_radius"]["consumer_count"], 0)

    def test_package_lineage_returns_packages_list(self):
        payload = get_unified_lineage(object_type="package", package_id="any-package")
        self.assertEqual(payload["object"]["type"], "package")
        self.assertEqual(payload["object"]["package_id"], "any-package")
        self.assertIsInstance(payload["packages"], list)

    def test_consumer_lineage_returns_consumers_summary(self):
        payload = get_unified_lineage(
            object_type="consumer",
            consumer_type="dashboard",
            consumer_code="principal_home",
        )
        self.assertEqual(payload["object"]["type"], "consumer")
        self.assertIn("downstream_summary", payload)
        self.assertIn("consumers", payload["downstream_summary"])
        # principal_home consumes student.admission_number
        consumers = payload["downstream_summary"]["consumers"]
        self.assertTrue(
            any(c.get("consumer_code") == "principal_home" for c in consumers),
            consumers,
        )

    def test_empty_object_type_returns_empty_result(self):
        payload = get_unified_lineage(object_type="entity", code="")
        self.assertEqual(payload["object"], {})
        self.assertEqual(payload["downstream"], [])
