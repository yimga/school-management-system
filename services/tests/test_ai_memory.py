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


class RagRetrievalEvalTests(TestCase):
    """
    Lightweight RAG leakage / isolation checks for CI (no live embedding provider).

    ``AIMemoryService.search_similar`` must not surface another tenant's scoped rows
    when ``school_id`` is set; global rows (``school_id`` null) remain shared.
    """

    def test_tenant_retrieval_never_returns_other_school_scoped_rows(self):
        school_a = uuid4()
        school_b = uuid4()
        # Tenant B holds a chunk that matches the query vector better than A's own.
        AIEmbeddingStore.objects.create(
            school_id=school_b,
            conversation_id="secret-b-payroll",
            scope="help",
            text_hash="b-only",
            embedding=[1.0, 0.0, 0.0],
            metadata={"source": "tenant_b"},
        )
        AIEmbeddingStore.objects.create(
            school_id=school_a,
            conversation_id="tenant-a-doc",
            scope="help",
            text_hash="a-only",
            embedding=[0.5, 0.5, 0.0],
            metadata={"source": "tenant_a"},
        )
        AIEmbeddingStore.objects.create(
            school_id=None,
            conversation_id="global-help",
            scope="help",
            text_hash="global",
            embedding=[0.99, 0.01, 0.0],
            metadata={"source": "platform"},
        )

        results = AIMemoryService.search_similar(
            str(school_a), "help", [1.0, 0.0, 0.0], limit=10
        )
        ids = {row["conversation_id"] for row in results}

        self.assertNotIn("secret-b-payroll", ids)
        self.assertIn("tenant-a-doc", ids)
        self.assertIn("global-help", ids)

    def test_retrieval_without_school_id_is_unscoped_use_with_care(self):
        """Operator / no-tenant contexts pass ``school_id=None``; queryset is not school-filtered."""
        s1 = uuid4()
        s2 = uuid4()
        AIEmbeddingStore.objects.create(
            school_id=s1,
            conversation_id="only-s1",
            scope="config",
            text_hash="h1",
            embedding=[1.0, 0.0],
            metadata={},
        )
        AIEmbeddingStore.objects.create(
            school_id=s2,
            conversation_id="only-s2",
            scope="config",
            text_hash="h2",
            embedding=[1.0, 0.0],
            metadata={},
        )
        results = AIMemoryService.search_similar(None, "config", [1.0, 0.0], limit=10)
        ids = {row["conversation_id"] for row in results}
        self.assertEqual(ids, {"only-s1", "only-s2"})
