"""Tests for ai_fallbacks — every key in PROMPT_LIBRARY must have a matching fallback."""

from django.test import SimpleTestCase

from apps.setup_studio import ai_fallbacks, ai_prompts


class FallbackCoverageTests(SimpleTestCase):
    def test_every_prompt_has_fallback(self):
        missing = [k for k in ai_prompts.PROMPT_LIBRARY if k not in ai_fallbacks.FALLBACK_REGISTRY]
        self.assertEqual(missing, [], f"Missing fallbacks for prompt keys: {missing}")

    def test_every_fallback_returns_dict(self):
        for key, fn in ai_fallbacks.FALLBACK_REGISTRY.items():
            with self.subTest(prompt_key=key):
                result = fn({}, [])
                self.assertIsInstance(result, dict, f"{key} fallback did not return dict")

    def test_fintech_apm_country_specific(self):
        out_in = ai_fallbacks.fallback_prompt_fintech_suggest_apm({"country_code": "IN"}, [])
        out_br = ai_fallbacks.fallback_prompt_fintech_suggest_apm({"country_code": "BR"}, [])
        self.assertEqual(out_in["recommended_apm_key"], "upi_rupay")
        self.assertEqual(out_br["recommended_apm_key"], "pix_brcode")

    def test_translation_mesh_fallback_returns_empty(self):
        out = ai_fallbacks.fallback_prompt_comms_translate_template({}, [])
        self.assertEqual(out["translations"], {})
        self.assertEqual(out["confidence"], 0.0)
