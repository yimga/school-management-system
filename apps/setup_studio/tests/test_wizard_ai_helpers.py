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


class NaturalLanguageIntakeTests(SimpleTestCase):
    def test_no_gateway_falls_back_to_unresolved(self):
        with patch.object(wizard_ai, "_call_gateway", return_value=(None, {})):
            r = wizard_ai.request_natural_language_intake(
                request=None, school=None, wizard_key="x",
                free_text="open Monday to Friday 8am",
                target_fields=["open_days", "open_time"],
            )
        self.assertTrue(r.used_fallback)
        self.assertEqual(r.parsed_fields, {})
        self.assertEqual(r.unresolved_phrases, ["open Monday to Friday 8am"])
        self.assertEqual(r.confidence, 0.0)

    def test_valid_json_parses_fields(self):
        ai_text = (
            '{"parsed_fields": {"open_days": "Mon-Fri", "open_time": "08:00"}, '
            '"unresolved_phrases": [], "confidence": 0.82}'
        )
        with patch.object(wizard_ai, "_call_gateway", return_value=(ai_text, {})):
            r = wizard_ai.request_natural_language_intake(
                request=None, school=None, wizard_key="x",
                free_text="open Monday to Friday 8am",
                target_fields=["open_days", "open_time"],
            )
        self.assertFalse(r.used_fallback)
        self.assertEqual(r.parsed_fields.get("open_days"), "Mon-Fri")
        self.assertEqual(r.parsed_fields.get("open_time"), "08:00")
        self.assertAlmostEqual(r.confidence, 0.82, places=2)

    def test_invalid_json_falls_back(self):
        with patch.object(wizard_ai, "_call_gateway", return_value=("not json {", {})):
            r = wizard_ai.request_natural_language_intake(
                request=None, school=None, wizard_key="x",
                free_text="something", target_fields=["a"],
            )
        self.assertTrue(r.used_fallback)
        self.assertEqual(r.parsed_fields, {})
