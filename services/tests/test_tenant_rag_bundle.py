from __future__ import annotations

import copy
import hashlib
from datetime import timedelta
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.siteconfig.models import AIEmbeddingStore
from services.ai_memory import AIMemoryService
from services.tenant_rag_bundle import (
    BUNDLE_SCHEMA,
    TenantRAGBundleError,
    export_tenant_rag_bundle,
    import_tenant_rag_bundle,
    sign_bundle_body,
)


@override_settings(TENANT_RAG_BUNDLE_SIGNING_KEY="test-rag-signing-key", DEBUG=False)
class TenantRAGBundleTests(TestCase):
    def setUp(self):
        self.school_id = uuid4()
        self.other_school_id = uuid4()
        self.now = timezone.now().replace(microsecond=0)

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _record(
        self,
        *,
        document_id: str,
        text: str,
        status: str = "active",
        updated_at=None,
    ):
        return {
            "conversation_id": document_id,
            "scope": "policy",
            "document_id": document_id,
            "text_hash": self._hash(text),
            "embedding_model": "ollama:nomic-embed-text",
            "embedding_dimensions": 2 if status == "active" else None,
            "embedding": [1.0, 0.0] if status == "active" else [],
            "lifecycle_status": status,
            "retention_until": None,
            "source_updated_at": (
                updated_at or self.now
            ).isoformat().replace("+00:00", "Z"),
            "metadata": {"source": "test"},
        }

    def _bundle(self, records):
        return sign_bundle_body(
            {
                "schema": BUNDLE_SCHEMA,
                "bundle_id": str(uuid4()),
                "tenant_id": str(self.school_id),
                "generated_at": self.now.isoformat().replace("+00:00", "Z"),
                "record_count": len(records),
                "scopes": ["policy"],
                "embedding_contract": {
                    "models": ["ollama:nomic-embed-text"],
                    "dimensions": [2],
                },
                "records": records,
            }
        )

    def test_export_is_tenant_scoped_and_preserves_contract_fields(self):
        AIEmbeddingStore.objects.create(
            school_id=self.school_id,
            conversation_id="policy:1",
            document_id="policy:1",
            scope="policy",
            text_hash=self._hash("tenant"),
            embedding_model="ollama:nomic-embed-text",
            embedding_dimensions=2,
            embedding=[1.0, 0.0],
            source_updated_at=self.now,
            metadata={"visibility": "tenant"},
        )
        AIEmbeddingStore.objects.create(
            school_id=self.other_school_id,
            conversation_id="policy:secret",
            document_id="policy:secret",
            scope="policy",
            text_hash=self._hash("other"),
            embedding=[0.0, 1.0],
            source_updated_at=self.now,
        )

        bundle = export_tenant_rag_bundle(str(self.school_id))

        self.assertEqual(bundle["record_count"], 1)
        self.assertEqual(bundle["tenant_id"], str(self.school_id))
        self.assertEqual(bundle["records"][0]["document_id"], "policy:1")
        self.assertEqual(
            bundle["embedding_contract"]["models"],
            ["ollama:nomic-embed-text"],
        )
        self.assertEqual(bundle["integrity"]["algorithm"], "HMAC-SHA256")

    def test_tampered_bundle_is_rejected_before_database_write(self):
        bundle = self._bundle([self._record(document_id="policy:1", text="one")])
        bundle["records"][0]["metadata"]["tampered"] = True

        with self.assertRaisesRegex(TenantRAGBundleError, "checksum mismatch"):
            import_tenant_rag_bundle(
                bundle,
                expected_school_id=str(self.school_id),
            )

        self.assertFalse(AIEmbeddingStore.objects.exists())

    def test_cross_tenant_import_is_rejected(self):
        bundle = self._bundle([self._record(document_id="policy:1", text="one")])

        with self.assertRaisesRegex(TenantRAGBundleError, "tenant binding"):
            import_tenant_rag_bundle(
                bundle,
                expected_school_id=str(self.other_school_id),
            )

    def test_import_is_idempotent(self):
        bundle = self._bundle([self._record(document_id="policy:1", text="one")])

        first = import_tenant_rag_bundle(
            bundle,
            expected_school_id=str(self.school_id),
        )
        second = import_tenant_rag_bundle(
            bundle,
            expected_school_id=str(self.school_id),
        )

        self.assertEqual(first.created, 1)
        self.assertEqual(second.updated, 1)
        self.assertEqual(AIEmbeddingStore.objects.count(), 1)

    def test_newer_tombstone_suppresses_document_and_blocks_stale_replay(self):
        active_time = self.now
        tombstone_time = self.now + timedelta(minutes=5)
        active = self._record(
            document_id="handbook",
            text="chunk-one",
            updated_at=active_time,
        )
        second_chunk = self._record(
            document_id="handbook",
            text="chunk-two",
            updated_at=active_time,
        )
        import_tenant_rag_bundle(
            self._bundle([active, second_chunk]),
            expected_school_id=str(self.school_id),
        )
        tombstone = self._record(
            document_id="handbook",
            text="deleted-handbook",
            status="tombstone",
            updated_at=tombstone_time,
        )

        summary = import_tenant_rag_bundle(
            self._bundle([tombstone]),
            expected_school_id=str(self.school_id),
        )
        stale_summary = import_tenant_rag_bundle(
            self._bundle([copy.deepcopy(active)]),
            expected_school_id=str(self.school_id),
        )

        self.assertEqual(summary.tombstoned, 3)
        self.assertEqual(stale_summary.skipped, 1)
        self.assertFalse(
            AIEmbeddingStore.objects.filter(
                school_id=self.school_id,
                document_id="handbook",
                lifecycle_status="active",
            ).exists()
        )
        self.assertEqual(
            AIMemoryService.search_similar(
                str(self.school_id), "policy", [1.0, 0.0], limit=10
            ),
            [],
        )

    def test_expired_retention_value_round_trips(self):
        retention = self.now + timedelta(days=30)
        record = self._record(document_id="policy:retained", text="retained")
        record["retention_until"] = retention.isoformat().replace("+00:00", "Z")
        import_tenant_rag_bundle(
            self._bundle([record]),
            expected_school_id=str(self.school_id),
        )

        exported = export_tenant_rag_bundle(str(self.school_id))

        self.assertEqual(
            exported["records"][0]["retention_until"],
            retention.isoformat().replace("+00:00", "Z"),
        )
