from uuid import uuid4

from django.test import TestCase

from apps.siteconfig.models import AIEmbeddingStore
from services.ai_memory import AIMemoryService


class AIMemoryServiceTests(TestCase):
    def test_search_similar_includes_global_rows_for_tenant_queries(self):
        school_id = uuid4()
        AIEmbeddingStore.objects.create(
            school_id=school_id,
            conversation_id="tenant-row",
            scope="help",
            text_hash="tenant-row",
            embedding=[1.0, 0.0],
            metadata={"source": "tenant"},
        )
        AIEmbeddingStore.objects.create(
            school_id=None,
            conversation_id="global-row",
            scope="help",
            text_hash="global-row",
            embedding=[0.9, 0.1],
            metadata={"source": "global"},
        )

        results = AIMemoryService.search_similar(str(school_id), "help", [1.0, 0.0], limit=5)

        self.assertEqual({row["conversation_id"] for row in results}, {"tenant-row", "global-row"})

    def test_search_similar_respects_role_and_staff_visibility(self):
        school_id = uuid4()
        AIEmbeddingStore.objects.create(
            school_id=None,
            conversation_id="staff-config",
            scope="config",
            text_hash="staff-config",
            embedding=[1.0, 0.0],
            metadata={"staff_only": True, "visibility": "staff"},
        )
        AIEmbeddingStore.objects.create(
            school_id=None,
            conversation_id="finance-playbook",
            scope="config",
            text_hash="finance-playbook",
            embedding=[0.9, 0.1],
            metadata={"allowed_roles": ["finance"]},
        )
        AIEmbeddingStore.objects.create(
            school_id=None,
            conversation_id="general-help",
            scope="config",
            text_hash="general-help",
            embedding=[0.8, 0.2],
            metadata={"visibility": "authenticated"},
        )

        finance_results = AIMemoryService.search_similar(
            str(school_id),
            "config",
            [1.0, 0.0],
            limit=5,
            actor_roles=["finance"],
        )
        self.assertEqual(
            {row["conversation_id"] for row in finance_results},
            {"finance-playbook", "general-help"},
        )

        staff_results = AIMemoryService.search_similar(
            str(school_id),
            "config",
            [1.0, 0.0],
            limit=5,
            actor_roles=["admin"],
            actor_is_staff=True,
        )
        self.assertEqual(
            {row["conversation_id"] for row in staff_results},
            {"staff-config", "general-help"},
        )

    def test_policy_scope_prefers_tenant_row_over_global_at_equal_embedding(self):
        school_id = uuid4()
        # Same embedding vector → equal cosine; tenant-specific policy should rank first.
        AIEmbeddingStore.objects.create(
            school_id=None,
            conversation_id="global-policy",
            scope="policy",
            text_hash="global-policy",
            embedding=[1.0, 0.0],
            metadata={"source": "PolicyBundle", "visibility": "tenant"},
        )
        AIEmbeddingStore.objects.create(
            school_id=school_id,
            conversation_id="tenant-policy",
            scope="policy",
            text_hash="tenant-policy",
            embedding=[1.0, 0.0],
            metadata={"source": "PolicyBundle", "visibility": "tenant"},
        )
        results = AIMemoryService.search_similar(
            str(school_id), "policy", [1.0, 0.0], limit=5
        )
        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0]["conversation_id"], "tenant-policy")
