"""Unit tests for services.ai_guided_fallback."""

from django.test import SimpleTestCase

from services.ai_guided_fallback import build_guided_fallback
from services.ai_schemas import validate_guided_assistant


class AIGuidedFallbackUnitTests(SimpleTestCase):
    def test_build_guided_fallback_nonempty_summary(self):
        out = build_guided_fallback(
            task_type="interop_assistant",
            user_query="How do I connect OneRoster?",
            rag_snippets=[{"scope": "help", "metadata": {"source": "interop doc"}}],
            live_provider_available=False,
        )
        validated = validate_guided_assistant(out)
        self.assertGreater(len(validated["summary"]), 40)
        self.assertTrue(validated["cautions"])

    def test_build_guided_fallback_live_provider_omits_connect_caution(self):
        out = build_guided_fallback(
            task_type="general_chat",
            user_query="Hello",
            live_provider_available=True,
        )
        summary = out.get("summary", "")
        self.assertNotIn("Ollama", summary)
