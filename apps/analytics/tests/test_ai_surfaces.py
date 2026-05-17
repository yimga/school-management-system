"""Wave 5 tests — semantic search and AI-narrated digest.

Embedding provider is monkey-patched to a deterministic stub so tests
don't hit Ollama. AI gateway is patched to return a fixed string so
we exercise the digest formatter independently.
"""

from __future__ import annotations

import unittest.mock as mock
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics import semantic_search
from apps.analytics.models import RiskFactor
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import AIEmbeddingStore, RegionConfig


class CosineMathTests(SimpleTestCase):
    def test_identical_vectors_score_one(self):
        v = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(semantic_search._cosine(v, v), 1.0, places=6)

    def test_orthogonal_vectors_score_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        self.assertAlmostEqual(semantic_search._cosine(a, b), 0.0, places=6)

    def test_mismatched_length_returns_zero(self):
        self.assertEqual(semantic_search._cosine([1, 2], [1, 2, 3]), 0.0)

    def test_empty_returns_zero(self):
        self.assertEqual(semantic_search._cosine([], [1, 2]), 0.0)


class _StubEmbeddingProvider:
    """Maps the first character of the text to a deterministic vector."""

    _LOOKUP = {
        "a": [1.0, 0.0, 0.0],
        "b": [0.0, 1.0, 0.0],
        "c": [0.5, 0.5, 0.0],
        "z": [0.0, 0.0, 1.0],
    }

    def embed(self, text, *, max_tokens: int = 8192):
        if not text:
            return None
        first = text.strip()[:1].lower()
        return list(self._LOOKUP.get(first, [0.1, 0.2, 0.3]))


def _patch_embeddings():
    return mock.patch(
        "apps.analytics.semantic_search.get_embedding_provider",
        return_value=_StubEmbeddingProvider(),
    )


class SemanticSearchTests(TestCase):
    def _seed_student(self, school, name, code):
        u = User.objects.create_user(
            username=f"ss_{name}_{id(self)}",
            email=f"ss_{name}_{id(self)}@example.com",
            password="p",
        )
        return StudentProfile.objects.create(
            school=school, user=u,
            first_name=name, last_name="Stud",
            student_code=code, is_active=True,
        )

    def setUp(self):
        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"WS{uid % 9999}",
            defaults={
                "name": "WS Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"WS {uid}", slug=f"ws-{uid}",
            subdomain=f"ws-{uid}", is_active=True, default_region=region,
        )

    def test_index_and_search_roundtrip(self):
        # Two students whose names map to orthogonal vectors.
        # "Alpha" → 'a' → [1,0,0]; "Bravo" → 'b' → [0,1,0].
        alpha = self._seed_student(self.school, "Alpha", f"A-{id(self)}")
        bravo = self._seed_student(self.school, "Bravo", f"B-{id(self)}")
        with _patch_embeddings():
            self.assertTrue(semantic_search.index_student(alpha))
            self.assertTrue(semantic_search.index_student(bravo))
            results = semantic_search.search_students(
                "alpha-like query",  # 'a' → matches Alpha
                school_id=self.school.id, top_k=2,
            )
        self.assertGreater(len(results), 0)
        # Top result should be Alpha (cosine 1.0 vs Bravo 0.0).
        self.assertEqual(results[0]["student_id"], str(alpha.pk))
        self.assertGreater(results[0]["score"], results[-1]["score"])

    def test_search_returns_empty_when_no_embedding(self):
        # No index_student calls → search returns empty.
        with _patch_embeddings():
            self.assertEqual(
                semantic_search.search_students(
                    "anything", school_id=self.school.id, top_k=5,
                ),
                [],
            )

    def test_search_filters_by_school(self):
        # Two schools' students; query embeds same as both, but the
        # search should only return the queried school's hit.
        other = School.objects.create(
            name="OtherWS", slug=f"ws-other-{id(self)}",
            subdomain=f"ws-other-{id(self)}", is_active=True,
            default_region=self.school.default_region,
        )
        with _patch_embeddings():
            # "Cherry" → 'c'; "Carl" → 'c' — both match.
            cherry = self._seed_student(self.school, "Cherry", f"C-{id(self)}-A")
            carl = self._seed_student(other, "Carl", f"C-{id(self)}-B")
            semantic_search.index_student(cherry)
            semantic_search.index_student(carl)
            results = semantic_search.search_students(
                "c query", school_id=self.school.id, top_k=5,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["student_id"], str(cherry.pk))


class AINarrateRiskDigestTests(TestCase):
    def setUp(self):
        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"DG{uid % 9999}",
            defaults={
                "name": "DG Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"DG {uid}", slug=f"dg-{uid}",
            subdomain=f"dg-{uid}", is_active=True, default_region=region,
        )
        u = User.objects.create_user(
            username=f"dg_st_{uid}",
            email=f"dg_st_{uid}@example.com", password="p",
        )
        self.student = StudentProfile.objects.create(
            school=self.school, user=u, first_name="Dana",
            last_name="Test", student_code=f"DGS-{uid % 9999}",
        )
        RiskFactor.objects.create(
            school=self.school, student=self.student,
            score=85.0, reason_summary="heuristic",
            feature_contributions=[
                {"name": "attendance_rate", "value": 0.62,
                 "importance": 0.31, "direction": "elevates"},
            ],
        )

    def test_digest_runs_with_gateway_off(self):
        out = StringIO()
        with mock.patch(
            "services.ai_helpers.invoke_with_request",
            return_value=None,
        ):
            call_command(
                "ai_narrate_risk_digest",
                "--school", self.school.slug,
                "--top-n", "5",
                stdout=out,
            )
        text = out.getvalue()
        self.assertIn("Dana Test", text)
        self.assertIn("85.0", text)
        self.assertIn("attendance_rate", text)
        self.assertIn("Narrative unavailable", text)

    def test_digest_uses_gateway_response(self):
        out = StringIO()
        with mock.patch(
            "services.ai_helpers.invoke_with_request",
            return_value=("Dana needs an attendance check-in today.", {}),
        ):
            call_command(
                "ai_narrate_risk_digest",
                "--school", self.school.slug,
                "--top-n", "1",
                stdout=out,
            )
        text = out.getvalue()
        self.assertIn("Narrative:", text)
        self.assertIn("attendance check-in", text)
