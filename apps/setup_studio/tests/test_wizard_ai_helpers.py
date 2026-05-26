"""Tests for wizard_ai — sanitization, fallback behavior, metric emission."""

from django.test import SimpleTestCase
from unittest.mock import patch

from apps.setup_studio import wizard_ai


class ContextSanitizationTests(SimpleTestCase):
    def test_drops_password(self):
        out = wizard_ai._sanitize_context({"country": "IN", "password": "secret"})
        self.assertIn("country", out)
        self.assertNotIn("password", out)

    def test_drops_token(self):
        out = wizard_ai._sanitize_context({"api_token": "x", "country": "IN"})
        self.assertNotIn("api_token", out)

    def test_drops_email(self):
        out = wizard_ai._sanitize_context({"parent_email": "x@y.co", "country": "IN"})
        self.assertNotIn("parent_email", out)

    def test_drops_phone(self):
        out = wizard_ai._sanitize_context({"phone_number": "+1...", "country": "IN"})
        self.assertNotIn("phone_number", out)

    def test_recursive_dict(self):
        out = wizard_ai._sanitize_context({
            "outer": {"password": "x", "country": "BR"},
            "country": "BR",
        })
        self.assertIn("outer", out)
        self.assertNotIn("password", out["outer"])

    def test_recursive_list_of_dicts(self):
        out = wizard_ai._sanitize_context({
            "rows": [{"name": "ok", "secret_key": "x"}, {"name": "ok2"}],
        })
        self.assertEqual(len(out["rows"]), 2)
        self.assertNotIn("secret_key", out["rows"][0])

    def test_passes_safe_keys(self):
        out = wizard_ai._sanitize_context({"country_code": "IN", "school_type": "k12"})
        self.assertEqual(out, {"country_code": "IN", "school_type": "k12"})


class FallbackOnUnavailableTests(SimpleTestCase):
    def test_unknown_prompt_key_falls_back(self):
        result = wizard_ai.request_smart_defaults(
            request=None,
            school=None,
            wizard_key="x",
            step_key="y",
            prompt_key="prompt.does.not.exist",
            context={},
            options=[],
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.suggestions, {})

    def test_known_prompt_no_gateway_falls_back(self):
        with patch.object(wizard_ai, "_call_gateway", return_value=(None, {})):
            result = wizard_ai.request_smart_defaults(
                request=None,
                school=None,
                wizard_key="x",
                step_key="y",
                prompt_key="prompt.fintech.suggest_apm",
                context={"country_code": "IN"},
                options=[{"value": "upi_rupay"}],
            )
            self.assertTrue(result.used_fallback)
            self.assertEqual(result.suggestions.get("recommended_apm_key"), "upi_rupay")

    def test_gateway_invalid_json_falls_back(self):
        with patch.object(wizard_ai, "_call_gateway", return_value=("not valid json {", {})):
            result = wizard_ai.request_smart_defaults(
                request=None, school=None,
                wizard_key="x", step_key="y",
                prompt_key="prompt.fintech.suggest_apm",
                context={"country_code": "BR"},
                options=[{"value": "pix_brcode"}],
            )
            self.assertTrue(result.used_fallback)

    def test_gateway_valid_json_success(self):
        ai_text = '{"recommended_apm_key": "upi_rupay", "fallback_apm_keys": [], "confidence": 0.9, "rationale_token": "x"}'
        with patch.object(wizard_ai, "_call_gateway", return_value=(ai_text, {})):
            result = wizard_ai.request_smart_defaults(
                request=None, school=None,
                wizard_key="x", step_key="y",
                prompt_key="prompt.fintech.suggest_apm",
                context={"country_code": "IN"},
                options=[{"value": "upi_rupay"}],
            )
            self.assertFalse(result.used_fallback)
            self.assertEqual(result.suggestions["recommended_apm_key"], "upi_rupay")


class TranslationMeshTests(SimpleTestCase):
    def test_fallback_returns_failed_locales(self):
        with patch.object(wizard_ai, "_call_gateway", return_value=(None, {})):
            r = wizard_ai.request_translation_mesh(
                request=None, school=None,
                wizard_key="x", source_locale="en",
                target_locales=["fr", "es"],
                message="Hello",
            )
            self.assertTrue(r.used_fallback)
            self.assertEqual(set(r.failed_locales), {"fr", "es"})
            self.assertEqual(r.translations, {})

    def test_success_path(self):
        ai_text = '{"translations": {"fr": "Bonjour", "es": "Hola"}, "confidence": 0.9}'
        with patch.object(wizard_ai, "_call_gateway", return_value=(ai_text, {})):
            r = wizard_ai.request_translation_mesh(
                request=None, school=None,
                wizard_key="x", source_locale="en",
                target_locales=["fr", "es"],
                message="Hello",
            )
            self.assertFalse(r.used_fallback)
            self.assertEqual(r.translations.get("fr"), "Bonjour")
            self.assertEqual(r.translations.get("es"), "Hola")
            self.assertEqual(r.failed_locales, [])

    def test_partial_translation_partial_failure(self):
        ai_text = '{"translations": {"fr": "Bonjour"}, "confidence": 0.7}'
        with patch.object(wizard_ai, "_call_gateway", return_value=(ai_text, {})):
            r = wizard_ai.request_translation_mesh(
                request=None, school=None,
                wizard_key="x", source_locale="en",
                target_locales=["fr", "es"],
                message="Hello",
            )
            self.assertFalse(r.used_fallback)
            self.assertEqual(r.failed_locales, ["es"])


class BranchRationaleTests(SimpleTestCase):
    def test_fallback_returns_generic_text(self):
        with patch.object(wizard_ai, "_call_gateway", return_value=(None, {})):
            r = wizard_ai.request_branch_rationale(
                request=None, school=None,
                wizard_key="x", step_key="y",
                prior_answers={"country": "IN"},
                branch_taken="default",
            )
            self.assertTrue(r.used_fallback)
            self.assertGreater(len(r.rationale_text), 0)

    def test_truncates_long_rationale(self):
        ai_text = '{"rationale_text": "' + ("a" * 500) + '", "confidence": 0.8}'
        with patch.object(wizard_ai, "_call_gateway", return_value=(ai_text, {})):
            r = wizard_ai.request_branch_rationale(
                request=None, school=None,
                wizard_key="x", step_key="y",
                prior_answers={},
                branch_taken="default",
            )
            self.assertLessEqual(len(r.rationale_text), 280)
