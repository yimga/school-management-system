from django.test import SimpleTestCase

from apps.portal.kb_embeddings import cosine_similarity, embedding_source_text
from apps.portal.models_kb import KBArticle


class KbEmbeddingMathTests(SimpleTestCase):
    def test_cosine_identical_vectors_score_one(self):
        vec = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(vec, vec), 1.0)

    def test_cosine_orthogonal_vectors_score_zero(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_embedding_source_text_joins_fields(self):
        class Stub:
            title = "Fees"
            summary = "How to pay"
            tags = "billing"

        text = embedding_source_text(Stub())
        self.assertIn("Fees", text)
        self.assertIn("billing", text)

    def test_kb_article_model_exposes_vector_embedding_field(self):
        field = KBArticle._meta.get_field("vector_embedding")
        self.assertEqual(field.get_internal_type(), "JSONField")
