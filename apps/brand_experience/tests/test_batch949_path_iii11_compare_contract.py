"""
PATH §6.6 III.11 / SOT §11.4 batch 949 — experience pack diff contract owned by brand_experience.

``compare_experience_packs`` backs Studio before/after and pack analytics; pack install rollback
is covered in ``packages.tests.test_experience_packs`` (imports this module).
"""

from __future__ import annotations

from django.test import TestCase

from apps.brand_experience.experience_packs import compare_experience_packs
from apps.brand_experience.models import ThemePack
from apps.packages.models import ExperiencePack


class PathIii11ExperiencePackCompareTests(TestCase):
    """§6.6 III.11: structural contract for theme/experience pack comparison."""

    def setUp(self):
        self.t1 = ThemePack.objects.create(
            name="T1", slug="t1-batch949", is_active=True
        )
        self.t2 = ThemePack.objects.create(
            name="T2", slug="t2-batch949", is_active=True
        )
        self.pack_a = ExperiencePack.objects.create(
            code="exp-batch949-a",
            name="Pack A",
            theme_pack_id=self.t1.pk,
            layout_schema={"k": 1},
            communication_style={"tone": "a"},
            is_active=True,
        )
        self.pack_b = ExperiencePack.objects.create(
            code="exp-batch949-b",
            name="Pack B",
            theme_pack_id=self.t2.pk,
            layout_schema={"k": 2},
            communication_style={"tone": "b"},
            is_active=True,
        )

    def test_compare_experience_packs_returns_stable_keys_for_ui_diff(self):
        out = compare_experience_packs(self.pack_a, self.pack_b)
        self.assertEqual(out["base_code"], "exp-batch949-a")
        self.assertEqual(out["compare_code"], "exp-batch949-b")
        self.assertIsInstance(out["changes"], dict)
        self.assertIsInstance(out["changed_sections"], list)
        self.assertIn("theme_pack_id", out["changed_sections"])

    def test_compare_experience_packs_handles_missing_operand(self):
        out = compare_experience_packs(self.pack_a, None)
        self.assertEqual(out["base_code"], "exp-batch949-a")
        self.assertEqual(out["compare_code"], "")
        self.assertEqual(out["changes"], {})
