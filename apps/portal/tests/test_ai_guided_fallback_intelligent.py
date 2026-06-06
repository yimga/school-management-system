"""Intelligent degraded-mode guided fallback (no Ollama fluff)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from services.ai_guided_fallback import build_guided_fallback


@override_settings(OLLAMA_REQUIRE_LIVE=False, AI_ALLOW_RULES_FALLBACK=True)
class IntelligentGuidedFallbackTests(SimpleTestCase):
    def test_studio_query_uses_studio_hint_not_ollama_ops_lead(self):
        out = build_guided_fallback(
            task_type="general_chat",
            user_query="How do I configure Tenant Studio branding?",
            live_provider_available=False,
        )
        summary = out.get("summary") or ""
        self.assertIn("Studio", summary)
        self.assertNotIn("Configure Ollama on the platform host", summary)

    def test_rag_snippets_surface_in_summary(self):
        out = build_guided_fallback(
            task_type="interop_assistant",
            user_query="OneRoster sync",
            rag_snippets=[
                {
                    "scope": "help",
                    "metadata": {
                        "source": "interop guide",
                        "text": "Enable district interop from Configure > District LMS.",
                    },
                }
            ],
            live_provider_available=False,
        )
        summary = out.get("summary") or ""
        self.assertIn("district interop", summary.lower())
        self.assertGreater(len(out.get("actions") or []), 0)

    @patch("services.ai.topology_map.search_topology")
    def test_topology_actions_when_request_present(self, mock_search):
        mock_search.return_value = [
            {
                "label": "AI Center",
                "path_label": "**Platform > AI Center**",
                "url": "https://school.test/siteconfig/ai-center/",
                "locked": False,
                "score": 3,
            }
        ]
        request = RequestFactory().get("/")
        request.user = MagicMock(is_authenticated=True)
        request.school = None
        out = build_guided_fallback(
            task_type="general_chat",
            user_query="open ai center",
            live_provider_available=False,
            metadata={"request": request},
        )
        titles = [a.get("title") for a in out.get("actions") or []]
        self.assertTrue(any("AI Center" in (t or "") for t in titles))

    def test_add_tenant_query_includes_rapid_create_path(self):
        request = RequestFactory().get("/")
        request.user = MagicMock(is_authenticated=True, is_staff=True, is_superuser=True)
        request.public_host_kind = "manager"
        request.school = None
        out = build_guided_fallback(
            task_type="studio_os_assistant",
            user_query="how can i add a tenant",
            live_provider_available=False,
            metadata={
                "request": request,
                "permissions": {
                    "can_provision_tenants": True,
                    "can_view_fleet_ops": True,
                    "scope": "admin",
                },
            },
        )
        summary = out.get("summary") or ""
        self.assertIn("Rapid Create", summary)
        actions = out.get("actions") or []
        self.assertTrue(any("Rapid" in (a.get("title") or "") for a in actions))
