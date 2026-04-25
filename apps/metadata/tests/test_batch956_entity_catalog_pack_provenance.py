"""SOT §11.4 batch 956 — PATH §6.3 III.7: EntityCatalogEntry pack provenance (read-only lineage + admin list)."""

from django.test import TestCase

from apps.metadata.lineage_api import get_unified_lineage
from apps.metadata.models import EntityCatalogEntry, FieldCatalogEntry


class Batch956EntityCatalogPackProvenanceTests(TestCase):
    def test_entity_catalog_entry_has_pack_fields(self):
        e = EntityCatalogEntry.objects.create(
            code="batch956_entity",
            name="Batch 956",
            source_pack_id="pack_slug",
            source_pack_version="3.0.0",
        )
        e.refresh_from_db()
        self.assertEqual(e.source_pack_id, "pack_slug")
        self.assertEqual(e.source_pack_version, "3.0.0")

    def test_lineage_entity_includes_empty_pack_when_catalog_blank(self):
        EntityCatalogEntry.objects.create(
            code="blank_pack_entity",
            name="No pack",
        )
        payload = get_unified_lineage(object_type="entity", code="blank_pack_entity")
        self.assertEqual(payload["object"]["source_pack_id"], "")
        self.assertEqual(payload["object"]["source_pack_version"], "")

    def test_lineage_field_includes_entity_pack_provenance(self):
        ent = EntityCatalogEntry.objects.create(
            code="ent_with_pack",
            name="With pack",
            source_pack_id="my_pack",
            source_pack_version="1.0.0",
        )
        FieldCatalogEntry.objects.create(
            entity=ent,
            field_name="f1",
            data_type="string",
        )
        payload = get_unified_lineage(
            object_type="field",
            entity_code="ent_with_pack",
            field_name="f1",
        )
        self.assertEqual(payload["object"]["source_pack_id"], "my_pack")
        self.assertEqual(payload["object"]["source_pack_version"], "1.0.0")
