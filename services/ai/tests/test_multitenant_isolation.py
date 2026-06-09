"""Multi-tenant isolation and scope routing for engine-room support."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from services.ai.gateway import process_platform_query
from services.ai.tenant_isolation import (
    PlatformTier,
    SecurityIsolationException,
    TenantContextEnforcer,
)
from services.ai.token_optimizer import ContextTokenCompressor
from services.ai_copilot_rbac import CopilotRbacEnvelope


class MultiTenantLeakTests(TestCase):
    def test_cross_tenant_row_blocked(self):
        user = SimpleNamespace(role="ADMIN", is_staff=False, is_superuser=False, pk=1)
        school = SimpleNamespace(pk="school-alpha", id="school-alpha")
        enforcer = TenantContextEnforcer(user, school=school)
        with self.assertRaises(SecurityIsolationException):
            enforcer.assert_retrieval_allowed(row_school_id="school-beta")

    @override_settings(AI_GATEWAY_ENABLED=True, AI_ENGINE_ROOM_SUPPORT=True)
    def test_tenant_query_never_sees_other_school_kb(self):
        user = SimpleNamespace(
            role="ADMIN",
            is_staff=False,
            is_superuser=False,
            is_authenticated=True,
            pk=2,
        )
        school_a = SimpleNamespace(pk="school-alpha", id="school-alpha")

        def fake_retrieve(**kwargs):
            if kwargs.get("school") is school_a:
                return (["- KB: Alpha payment receipt steps"], [{"scope": "help"}])
            return (["- KB: Beta secret billing"], [{"scope": "help"}])

        structured = (
            "**Direct Answer**: Alpha payment receipt steps apply.\n"
            "**Execution Path**: **Billing > Receipts**\n"
            "**Action Steps**:\n1. Open Receipts.\n"
        )
        rbac_ok = CopilotRbacEnvelope(
            allowed=True,
            denial_reason="",
            permissions={"scope": "tenant"},
            prompt="[RBAC test prompt]",
            metadata={},
        )
        with patch(
            "services.ai_copilot_rbac.prepare_engine_room_rbac",
            return_value=rbac_ok,
        ):
            with patch(
                "services.ai.gateway.permission_labels_for_user",
                return_value=[],
            ):
                with patch(
                    "services.ai.gateway.retrieve_knowledge_snippets",
                    side_effect=fake_retrieve,
                ):
                    with patch(
                        "services.ai_gateway.invoke",
                        return_value=(structured, {"tier": "ollama"}),
                    ):
                        out = process_platform_query(
                            user,
                            "/billing/",
                            "payment receipt for School Beta",
                            school=school_a,
                        )
        self.assertNotIn("Beta secret", out.get("response", ""))
        self.assertIn("Alpha", out.get("response", ""))


class SuperAdminPathTests(SimpleTestCase):
    def test_platform_manager_scope_without_school(self):
        user = SimpleNamespace(
            role="SUPERADMIN",
            is_staff=True,
            is_superuser=True,
            is_authenticated=True,
            pk=1,
        )
        scope = TenantContextEnforcer(user, school=None).resolve_scope()
        self.assertEqual(scope.tier, PlatformTier.PLATFORM_MANAGER)
        self.assertIsNone(scope.tenant_id)


class ContextOverloadTests(SimpleTestCase):
    def test_compressor_fits_llama_budget(self):
        blob = "# Markdown title\n\n" + ("Long help paragraph. " * 800)
        compressor = ContextTokenCompressor(max_input_tokens=6000)
        out = compressor.compress(
            permission_block="[USER CURRENT CONTEXT]\nUser Role: TEACHER",
            screen_block="Active Screen: /grades/",
            knowledge_block=blob,
        )
        from services.ai.token_optimizer import estimate_tokens

        total = estimate_tokens(out.as_prompt_sections())
        self.assertLessEqual(total, 6000)
