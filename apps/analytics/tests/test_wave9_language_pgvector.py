"""Wave 9 tests — multi-language digest + pgvector gating."""

from __future__ import annotations

import unittest.mock as mock
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics import semantic_search
from apps.analytics.management.commands import ai_narrate_risk_digest as digest_mod
from apps.analytics.models import RiskFactor
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class LanguageResolutionTests(SimpleTestCase):
    def test_known_label(self):
        self.assertEqual(digest_mod._language_label("fr"), "French")
        self.assertEqual(digest_mod._language_label("sw"), "Swahili")

    def test_unknown_falls_back_to_uppercased_code(self):
        self.assertEqual(digest_mod._language_label("zz"), "ZZ")
        self.assertEqual(digest_mod._language_label(""), "English")


class LanguageResolutionFromSchoolTests(TestCase):
    def _school(self, *, region_lang):
        region, _ = RegionConfig.objects.get_or_create(
            code=f"L9{abs(hash(region_lang))}",
            defaults={
                "name": "L9 Region",
                "default_language": region_lang,
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        # Override the language even if existing.
        region.default_language = region_lang
        region.save()
        return School.objects.create(
            name=f"L9 {region_lang}",
            slug=f"l9-{region_lang.lower()}-{abs(hash(region_lang)) % 9999}",
            subdomain=f"l9-{region_lang.lower()}-{abs(hash(region_lang)) % 9999}",
            is_active=True,
            default_region=region,
        )

    def test_resolves_from_region(self):
        sc = self._school(region_lang="fr")
        self.assertEqual(digest_mod._resolve_language_code(sc), "fr")

    def test_strips_locale_suffix(self):
        sc = self._school(region_lang="fr-CM")
        self.assertEqual(digest_mod._resolve_language_code(sc), "fr")

    @override_settings(LANGUAGE_CODE="es")
    def test_falls_back_to_settings(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="L9NL",
            defaults={
                "name": "NL Region",
                "default_language": "",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        region.default_language = ""
        region.save()
        sc = School.objects.create(
            name="NL", slug=f"nl-{id(self)}",
            subdomain=f"nl-{id(self)}",
            is_active=True, default_region=region,
        )
        self.assertEqual(digest_mod._resolve_language_code(sc), "es")


class DigestPromptIncludesLanguageTests(TestCase):
    def test_prompt_carries_language_label(self):
        region, _ = RegionConfig.objects.get_or_create(
            code=f"L9P{id(self) % 9999}",
            defaults={
                "name": "L9P Region",
                "default_language": "fr",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        region.default_language = "fr"
        region.save()
        school = School.objects.create(
            name=f"L9P {id(self)}",
            slug=f"l9p-{id(self)}",
            subdomain=f"l9p-{id(self)}",
            is_active=True, default_region=region,
        )
        u = User.objects.create_user(
            username=f"l9p_st_{id(self)}",
            email="x@example.com", password="p",
        )
        student = StudentProfile.objects.create(
            school=school, user=u, first_name="N",
            last_name="O", student_code=f"L9P-{id(self)}",
        )
        RiskFactor.objects.create(
            school=school, student=student, score=82.0,
            reason_summary="t",
        )
        captured = {}

        def _capture(*, task_type, prompt, school, metadata=None, **kw):
            captured["prompt"] = prompt
            captured["metadata"] = metadata
            return ("OK", {})

        with mock.patch(
            "services.ai_helpers.invoke_with_request",
            side_effect=_capture,
        ):
            call_command(
                "ai_narrate_risk_digest",
                "--school", school.slug,
                "--top-n", "1",
                stdout=StringIO(),
            )
        self.assertIn("French", captured.get("prompt", ""))
        self.assertEqual(
            (captured.get("metadata") or {}).get("language"), "fr",
        )


class PgvectorGatingTests(SimpleTestCase):
    @override_settings(PGVECTOR_ENABLED=False)
    def test_gate_off_by_default(self):
        self.assertFalse(semantic_search._pgvector_enabled())

    @override_settings(PGVECTOR_ENABLED=True)
    def test_gate_on_only_when_postgres(self):
        # Test DB is sqlite in this env; gate should still return False.
        self.assertFalse(semantic_search._pgvector_enabled())


class PgvectorMigrationCommandTests(TestCase):
    def test_refuses_when_not_postgres(self):
        from django.core.management import CommandError
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "migrate_embeddings_to_pgvector",
                "--dimensions", "384",
                stdout=StringIO(),
            )
        self.assertIn("pgvector requires PostgreSQL", str(ctx.exception))


class PgvectorSearchBranchTests(TestCase):
    """When pgvector is enabled, search calls the pgvector path."""

    def test_pgvector_path_called(self):
        with mock.patch(
            "apps.analytics.semantic_search._pgvector_enabled",
            return_value=True,
        ), mock.patch(
            "apps.analytics.semantic_search._pgvector_search",
            return_value=[{"student_id": "999", "score": 0.99, "summary": "via pgv"}],
        ) as pgv_mock, mock.patch(
            "apps.analytics.semantic_search.get_embedding_provider"
        ) as ep_mock:
            ep_mock.return_value.embed.return_value = [0.1, 0.2, 0.3]
            results = semantic_search.search_students(
                "test", school_id="abc", top_k=5,
            )
        self.assertEqual(pgv_mock.call_count, 1)
        self.assertEqual(results[0]["score"], 0.99)

    def test_pgvector_failure_falls_back_to_json(self):
        with mock.patch(
            "apps.analytics.semantic_search._pgvector_enabled",
            return_value=True,
        ), mock.patch(
            "apps.analytics.semantic_search._pgvector_search",
            side_effect=RuntimeError("vector ext missing"),
        ), mock.patch(
            "apps.analytics.semantic_search.get_embedding_provider"
        ) as ep_mock:
            ep_mock.return_value.embed.return_value = [0.1, 0.2, 0.3]
            # No JSON rows seeded → empty fallback. No crash.
            self.assertEqual(
                semantic_search.search_students(
                    "test", school_id="abc", top_k=5,
                ),
                [],
            )
