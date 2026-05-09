"""Tests for the central settings registry."""

from __future__ import annotations

from django.test import SimpleTestCase

from config.settings_registry import (
    SETTINGS_REGISTRY,
    SettingSpec,
    all_setting_names,
    find_spec,
)


class SettingsRegistryTests(SimpleTestCase):
    def test_registry_is_non_empty(self):
        self.assertGreater(len(SETTINGS_REGISTRY), 0)

    def test_every_spec_has_required_fields(self):
        for spec in SETTINGS_REGISTRY:
            self.assertIsInstance(spec, SettingSpec)
            self.assertTrue(spec.name and spec.name == spec.name.upper())
            self.assertTrue(spec.type)
            self.assertIsInstance(spec.default, str)
            self.assertTrue(spec.owner)
            self.assertTrue(spec.purpose)

    def test_setting_names_are_unique(self):
        names = [spec.name for spec in SETTINGS_REGISTRY]
        self.assertEqual(len(names), len(set(names)))

    def test_all_setting_names_returns_set(self):
        names = all_setting_names()
        self.assertIsInstance(names, set)
        self.assertIn("RATE_LIMIT_ENABLED", names)
        self.assertIn("STRIPE_SECRET_KEY", names)

    def test_find_spec_known(self):
        spec = find_spec("STRIPE_WEBHOOK_SECRET")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.owner, "payments")

    def test_find_spec_unknown(self):
        self.assertIsNone(find_spec("NOT_A_REAL_SETTING_XYZ"))

    def test_security_critical_settings_declared(self):
        names = all_setting_names()
        for required in (
            "SESSION_COOKIE_HTTPONLY",
            "CSRF_COOKIE_HTTPONLY",
            "X_FRAME_OPTIONS",
            "SECURE_REFERRER_POLICY",
            "SECURE_HSTS_SECONDS",
            "RATE_LIMIT_ENABLED",
        ):
            self.assertIn(required, names, f"missing security setting: {required}")
