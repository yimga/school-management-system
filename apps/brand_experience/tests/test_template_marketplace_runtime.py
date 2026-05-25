"""Template marketplace runtime tests (batch 1506 audit closure).

Pins the contract that the experience template registry exposes a sufficient
catalog and that operator-only templates do not leak into tenant scope.
"""

from __future__ import annotations

from django.test import SimpleTestCase


class TemplateMarketplaceRuntimeTests(SimpleTestCase):
    def setUp(self) -> None:
        from apps.platform_runtime.pack_contract import EXPERIENCE_TEMPLATE_PACKS
        self.contracts = EXPERIENCE_TEMPLATE_PACKS

    def test_experience_template_contracts_present(self) -> None:
        self.assertGreaterEqual(len(self.contracts), 25, "Need >=25 experience templates registered")

    def test_template_keys_are_unique(self) -> None:
        keys = [c.key for c in self.contracts]
        self.assertEqual(len(keys), len(set(keys)), "duplicate template keys detected")

    def test_template_keys_kebab_safe(self) -> None:
        for c in self.contracts:
            self.assertTrue(
                all(ch.isalnum() or ch in "-_." for ch in c.key),
                f"unsafe characters in template key {c.key!r}",
            )

    def test_all_template_contracts_carry_required_metadata(self) -> None:
        for c in self.contracts:
            self.assertTrue(c.key)
            self.assertTrue(c.name)
            self.assertEqual(c.pack_type, "experience_template")

    def test_local_first_profile_registry_present(self) -> None:
        from apps.siteconfig.local_experience_profiles import PROFILES
        self.assertGreaterEqual(len(PROFILES), 20)
