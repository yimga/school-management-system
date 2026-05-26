"""Tests for apps.platform_runtime.runtime_defaults_first_class.set_runtime_default.

Per-tenant runtime-default override shim called by the Unified Wizard
Framework's whitelabel writer. Lands values in
``school.settings["runtime_defaults"][<field>]`` (NOT on the singleton).
"""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime import runtime_defaults_first_class as rd
from apps.schools.models import School


class SetRuntimeDefaultTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Runtime School",
            slug="runtime-school",
            subdomain="runtime-school",
            is_active=True,
        )

    def _override(self, field: str):
        self.school.refresh_from_db()
        rd_bucket = (self.school.settings or {}).get("runtime_defaults") or {}
        return rd_bucket.get(field)

    def test_wizard_brand_keys_land(self):
        ok = rd.set_runtime_default(
            school=self.school,
            field="brand_palette_key",
            value="kerala_heritage_emerald",
        )
        self.assertTrue(ok)
        self.assertEqual(self._override("brand_palette_key"), "kerala_heritage_emerald")

    def test_singleton_first_class_fields_also_allowed(self):
        ok = rd.set_runtime_default(
            school=self.school,
            field="company_name",
            value="Riverside Academy",
        )
        self.assertTrue(ok)
        self.assertEqual(self._override("company_name"), "Riverside Academy")

    def test_unknown_field_rejected(self):
        ok = rd.set_runtime_default(
            school=self.school,
            field="random_bogus_field",
            value="x",
        )
        self.assertFalse(ok)
        self.assertIsNone(self._override("random_bogus_field"))

    def test_idempotent_same_value(self):
        rd.set_runtime_default(
            school=self.school, field="brand_primary_color", value="#4F46E5"
        )
        self.assertFalse(
            rd.set_runtime_default(
                school=self.school, field="brand_primary_color", value="#4F46E5"
            )
        )

    def test_no_op_inputs(self):
        self.assertFalse(rd.set_runtime_default(school=None, field="company_name", value="x"))
        self.assertFalse(rd.set_runtime_default(school=self.school, field="", value="x"))
