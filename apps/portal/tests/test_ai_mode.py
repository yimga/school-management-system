"""AI mode (local/cloud/auto) — configurable switch + functional provider routing.

Covers the pure mapping, the cascade resolver (tenant override > platform default
> auto), the switch endpoint RBAC (operator platform default + per-tenant override),
the functional thread into the gateway tier filter, and the inference-quota guard.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase

import services.ai_helpers as ai_helpers
from apps.platform_runtime.models import RuntimeDefaults
from apps.portal.views_ai_mode import ai_mode_view
from apps.schools.models import School
from services.ai_deployment_posture import (
    VALID_AI_MODES,
    ai_mode_to_allowed_backends,
    normalize_ai_mode,
    resolve_effective_ai_mode,
)

User = get_user_model()


class AiModeMappingTests(SimpleTestCase):
    def test_normalize(self):
        self.assertEqual(normalize_ai_mode(None), "auto")
        self.assertEqual(normalize_ai_mode(""), "auto")
        self.assertEqual(normalize_ai_mode("  CLOUD "), "cloud")
        self.assertEqual(normalize_ai_mode("local"), "local")
        self.assertEqual(normalize_ai_mode("bogus"), "auto")

    def test_mode_to_allowed_backends(self):
        self.assertIsNone(ai_mode_to_allowed_backends("auto"))
        self.assertIsNone(ai_mode_to_allowed_backends(None))
        self.assertEqual(
            ai_mode_to_allowed_backends("cloud"), ["litellm", "ollama", "rules"]
        )
        self.assertEqual(ai_mode_to_allowed_backends("local"), ["ollama", "rules"])

    def test_rules_always_remains_so_calls_degrade(self):
        # Neither switch may strand a call with no usable tier.
        self.assertIn("rules", ai_mode_to_allowed_backends("local"))
        self.assertIn("rules", ai_mode_to_allowed_backends("cloud"))

    def test_local_never_includes_cloud(self):
        self.assertNotIn("litellm", ai_mode_to_allowed_backends("local"))


class ResolveEffectiveAiModeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Mode School", slug="mode-school",
            subdomain="mode-school", is_active=True,
        )

    def test_default_is_auto(self):
        self.assertEqual(resolve_effective_ai_mode(self.school), "auto")

    def test_tenant_override_wins(self):
        self.school.settings = {"runtime_defaults": {"ai_mode": "local"}}
        self.school.save(update_fields=["settings"])
        cache.clear()
        self.assertEqual(resolve_effective_ai_mode(self.school), "local")

    def test_platform_default_applies_without_override(self):
        rd, _ = RuntimeDefaults.objects.get_or_create(pk=1)
        rd.ai_mode = "cloud"
        rd.save(update_fields=["ai_mode"])
        cache.clear()
        self.assertEqual(resolve_effective_ai_mode(self.school), "cloud")

    def test_none_school_is_auto(self):
        self.assertIn(resolve_effective_ai_mode(None), VALID_AI_MODES)


class AiModeEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Switch School", slug="switch-school",
            subdomain="switch-school", is_active=True,
        )
        self.admin = User.objects.create_user(
            username="mode_admin", email="a@example.com", password="x",
            is_staff=True, is_superuser=True,
        )
        self.plain = User.objects.create_user(
            username="mode_plain", email="p@example.com", password="x",
        )

    def _req(self, method, data=None, *, user, school):
        if method == "GET":
            r = self.factory.get("/portal/ai/mode/")
        else:
            r = self.factory.post("/portal/ai/mode/", data or {})
        r.user = user
        r.school = school
        return r

    def test_get_state_for_admin(self):
        resp = ai_mode_view(self._req("GET", user=self.admin, school=self.school))
        self.assertEqual(resp.status_code, 200)
        import json
        body = json.loads(resp.content)
        self.assertTrue(body["ok"])
        self.assertTrue(body["can_set_tenant"])
        self.assertEqual(body["effective_mode"], "auto")
        self.assertEqual(set(body["available_modes"]), set(VALID_AI_MODES))

    def test_anonymous_is_403(self):
        from django.contrib.auth.models import AnonymousUser
        resp = ai_mode_view(self._req("GET", user=AnonymousUser(), school=self.school))
        self.assertEqual(resp.status_code, 403)

    def test_admin_sets_tenant_override(self):
        resp = ai_mode_view(
            self._req("POST", {"scope": "tenant", "mode": "local"}, user=self.admin, school=self.school)
        )
        self.assertEqual(resp.status_code, 200)
        self.school.refresh_from_db()
        self.assertEqual(self.school.settings["runtime_defaults"]["ai_mode"], "local")

    def test_plain_user_cannot_set_tenant(self):
        resp = ai_mode_view(
            self._req("POST", {"scope": "tenant", "mode": "local"}, user=self.plain, school=self.school)
        )
        self.assertEqual(resp.status_code, 403)
        self.school.refresh_from_db()
        self.assertNotIn("runtime_defaults", self.school.settings or {})

    def test_invalid_mode_is_400(self):
        resp = ai_mode_view(
            self._req("POST", {"scope": "tenant", "mode": "quantum"}, user=self.admin, school=self.school)
        )
        self.assertEqual(resp.status_code, 400)

    def test_clearing_tenant_override(self):
        self.school.settings = {"runtime_defaults": {"ai_mode": "local"}}
        self.school.save(update_fields=["settings"])
        resp = ai_mode_view(
            self._req("POST", {"scope": "tenant", "mode": "inherit"}, user=self.admin, school=self.school)
        )
        self.assertEqual(resp.status_code, 200)
        self.school.refresh_from_db()
        self.assertNotIn("ai_mode", self.school.settings.get("runtime_defaults", {}))

    def test_operator_sets_platform_default(self):
        # No request.school -> platform scope; superuser passes control-plane gate.
        resp = ai_mode_view(self._req("POST", {"scope": "platform", "mode": "cloud"}, user=self.admin, school=None))
        self.assertEqual(resp.status_code, 200)
        rd = RuntimeDefaults.objects.get(pk=1)
        self.assertEqual(rd.ai_mode, "cloud")

    def test_plain_user_cannot_set_platform(self):
        resp = ai_mode_view(self._req("POST", {"scope": "platform", "mode": "cloud"}, user=self.plain, school=None))
        self.assertEqual(resp.status_code, 403)


class _AllowGuard:
    """Stand-in for guard_copilot_invoke's result (always allows)."""

    def __init__(self, metadata, prompt):
        self.allowed = True
        self.metadata = metadata
        self.prompt = prompt
        self.denial_reason = None


class AiModeThreadingTests(TestCase):
    """The switch is real: the resolved mode reaches the gateway as allowed_backends."""

    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Thread School", slug="thread-school",
            subdomain="thread-school", is_active=True,
            settings={"runtime_defaults": {"ai_mode": "local"}},
        )

    def _invoke_capturing(self):
        captured = {}

        def fake_gateway_invoke(task, prompt, user_query="", metadata=None, response_schema=None):
            captured["md"] = metadata
            return ("ok", metadata or {})

        with patch("services.ai_helpers.is_ai_available", return_value=True), patch(
            "services.ai_copilot_rbac.guard_copilot_invoke",
            side_effect=lambda **kw: _AllowGuard(kw["metadata"], kw["prompt"]),
        ), patch("services.ai_gateway.invoke", fake_gateway_invoke), patch(
            "services.ai_helpers_quota.check_inference_quota", return_value=(True, 100)
        ):
            ai_helpers.invoke_with_request(
                task_type="general_chat", prompt="hello", school=self.school
            )
        return captured

    def test_local_mode_threads_ollama_only(self):
        captured = self._invoke_capturing()
        self.assertEqual(captured["md"].get("allowed_backends"), ["ollama", "rules"])
        self.assertEqual(captured["md"].get("ai_mode"), "local")

    def test_quota_exhausted_returns_none(self):
        with patch("services.ai_helpers.is_ai_available", return_value=True), patch(
            "services.ai_helpers_quota.check_inference_quota", return_value=(False, 0)
        ):
            result = ai_helpers.invoke_with_request(
                task_type="general_chat", prompt="hello", school=self.school
            )
        self.assertIsNone(result)
