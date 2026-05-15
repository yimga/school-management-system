"""Multilingual baseline-overlay smoke for ontology.all_synonyms().

Verifies the seeded en/fr/es/ar/pt plus the platform's baseline overlay
(de/it/zh/hi/ja/ko/vi/id/ru/tr/sw/ha/yo/am/tw/pid/ur/bn/ta) are merged
when callers ask for a canonical field's synonyms.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.ontology import all_synonyms


class BaselineOverlayMergeTests(SimpleTestCase):
    def test_first_name_carries_western_synonyms(self) -> None:
        syns = set(all_synonyms("first_name", domain="students"))
        self.assertIn("first_name", syns)
        self.assertIn("given_name", syns)

    def test_first_name_carries_german(self) -> None:
        self.assertIn("vorname", set(all_synonyms("first_name", domain="students")))

    def test_first_name_carries_swahili(self) -> None:
        self.assertIn(
            "jina_la_kwanza",
            set(all_synonyms("first_name", domain="students")),
        )

    def test_first_name_carries_japanese(self) -> None:
        syns = set(all_synonyms("first_name", domain="students"))
        self.assertTrue(any("名" in s or "名前" in s for s in syns))

    def test_external_id_carries_indonesian_nis(self) -> None:
        self.assertIn("nis", set(all_synonyms("external_id", domain="students")))

    def test_unknown_field_returns_empty(self) -> None:
        self.assertEqual(all_synonyms("does_not_exist", domain="students"), [])
