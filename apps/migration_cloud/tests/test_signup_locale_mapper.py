"""Signup locale bridge + mapper integration (v4.02.28 E2E)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.migration_cloud.mapper import map_artifact
from apps.migration_cloud.profiler import _normalize_header
from apps.migration_cloud.signup_locale_bridge import (
    extra_synonyms_for_canonical,
    resolve_signup_locale_context,
)


class SignupLocaleBridgeTests(SimpleTestCase):
    databases = {"default"}

    def test_resolve_prefers_bundle_snapshot(self):
        bundle = SimpleNamespace(
            progress_snapshot={
                "signup_locale_context": {"country_code": "CN", "term_label": "学期"}
            },
            school=None,
        )
        ctx = resolve_signup_locale_context(bundle)
        self.assertEqual(ctx["country_code"], "CN")
        self.assertEqual(ctx["term_label"], "学期")

    def test_extra_synonyms_from_cn_terminology(self):
        bundle = SimpleNamespace(
            progress_snapshot={"signup_locale_context": {"country_code": "CN"}},
            school=None,
        )
        extras = extra_synonyms_for_canonical(
            bundle,
            canonical_field="term",
            domain="grades",
        )
        self.assertTrue(
            any("学期" in token or "semester" in token.lower() for token in extras)
        )

    def test_cjk_header_normalization_preserved(self):
        self.assertEqual(_normalize_header("年级"), "年级")

    def test_mapper_maps_cjk_grade_header(self):
        bundle = SimpleNamespace(
            progress_snapshot={"signup_locale_context": {"country_code": "CN"}},
            school=None,
        )
        artifact = SimpleNamespace(
            bundle=bundle,
            profile={
                "columns": [
                    {
                        "name": "年级",
                        "normalized": _normalize_header("年级"),
                        "inferred_type": "string",
                        "samples": ["10", "11"],
                    }
                ]
            },
        )
        mappings = map_artifact(artifact=artifact, domain="students")
        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0].canonical_field, "grade_level")
        self.assertEqual(mappings[0].method, "alias")
