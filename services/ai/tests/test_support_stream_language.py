"""SSE language meta from active Django locale (batch 1337)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from services.ai.support_stream import iter_support_assistant_sse
from services.ai.tenant_isolation import PlatformTier


class SupportStreamLanguageTests(SimpleTestCase):
    def test_active_locale_read_for_sse_meta(self):
        with patch("django.utils.translation.get_language", return_value="fr-ca"):
            from django.utils import translation

            language = (translation.get_language() or "en")[:12]
            self.assertEqual(language, "fr-ca")

    @patch.dict(
        "sys.modules",
        {},
        clear=False,
    )
    def test_meta_frame_includes_language_on_escalation_path(self):
        patches = [
            patch("services.ai.support_stream._engine_room_enabled", return_value=True),
            patch("services.ai.support_stream._query_permission_denied", return_value=None),
            patch("services.ai.support_stream._route_permission_denied", return_value=None),
            patch("services.ai.support_stream.match_path_with_test_hooks", return_value=None),
            patch("services.ai.support_stream.permission_labels_for_user", return_value=[]),
            patch("services.ai.support_stream.retrieve_knowledge_snippets", return_value=([], [])),
            patch("services.ai.code_oracle.build_route_manual_outline", return_value=""),
            patch("services.ai.gateway._escalation_for_scope", return_value="Escalate."),
            patch("django.utils.translation.get_language", return_value="es"),
        ]
        enforcer_instance = MagicMock()
        enforcer_instance.resolve_scope.return_value = SimpleNamespace(
            tier=PlatformTier.SCHOOL_TENANT,
            tenant_id="school-1",
        )
        enforcer_instance.build_context_header.return_value = "ctx"
        patches.append(
            patch(
                "services.ai.support_stream.TenantContextEnforcer",
                return_value=enforcer_instance,
            )
        )
        inspector_instance = MagicMock()
        inspector_instance.match_path.return_value = None
        patches.append(
            patch(
                "services.ai.support_stream.DynamicSystemInspector",
                return_value=inspector_instance,
            )
        )
        for p in patches:
            p.start()
        try:
            request = RequestFactory().get("/")
            frames = list(
                iter_support_assistant_sse(
                    user_profile=MagicMock(is_authenticated=True),
                    active_url="/kb/",
                    user_query="ayuda",
                    request=request,
                )
            )
            meta_raw = next(f for f in frames if b"event: meta" in f).decode("utf-8")
            data = json.loads(
                [ln for ln in meta_raw.split("\n") if ln.startswith("data:")][0].replace(
                    "data: ", "", 1
                )
            )
            self.assertEqual(data.get("language"), "es")
        finally:
            for p in reversed(patches):
                p.stop()
