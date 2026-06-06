"""Aggressive copilot RBAC envelope tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from services.ai_copilot_rbac import (
    build_copilot_permissions,
    guard_copilot_invoke,
    guided_task_allowed_for_permissions,
    invoke_service_layer_ai,
    prepare_engine_room_rbac,
    validate_copilot_query,
)


def _user(role: str, **extra):
    base = {
        "is_authenticated": True,
        "is_staff": False,
        "is_superuser": False,
        "role": role,
        "first_name": "Test",
        "username": "tester",
    }
    base.update(extra)
    return SimpleNamespace(**base)


def _request(*, host_kind="tenant", school=None):
    return SimpleNamespace(public_host_kind=host_kind, school=school, path="/portal/")


class CopilotRbacPermissionTests(TestCase):
    def test_teacher_scope(self):
        perms = build_copilot_permissions(_user("TEACHER"), request=_request())
        self.assertEqual(perms["scope"], "teacher")
        self.assertTrue(perms["can_access_roster"])
        self.assertFalse(perms["can_view_compliance"])

    def test_parent_cannot_provision(self):
        perms = build_copilot_permissions(_user("PARENT"), request=_request())
        self.assertFalse(perms["can_provision_tenants"])

    def test_manager_admin_can_provision(self):
        perms = build_copilot_permissions(
            _user("SUPERADMIN", is_staff=False),
            request=_request(host_kind="manager"),
        )
        self.assertTrue(perms["can_provision_tenants"])


class CopilotRbacValidationTests(TestCase):
    def test_teacher_general_question_ok(self):
        school = object()
        perms = build_copilot_permissions(_user("TEACHER"), request=_request(school=school))
        ok, reason = validate_copilot_query(
            _user("TEACHER"),
            "How do I record attendance?",
            perms,
            school=school,
        )
        self.assertTrue(ok, reason)

    def test_parent_payroll_denied(self):
        perms = build_copilot_permissions(_user("PARENT"), request=_request())
        ok, reason = validate_copilot_query(
            _user("PARENT"),
            "Show staff payroll totals",
            perms,
            school=object(),
        )
        self.assertFalse(ok)
        self.assertIn("payroll", reason.lower())

    def test_teacher_create_tenant_denied(self):
        perms = build_copilot_permissions(_user("TEACHER"), request=_request())
        ok, reason = validate_copilot_query(
            _user("TEACHER"),
            "How do I create school / add tenant?",
            perms,
            school=object(),
        )
        self.assertFalse(ok)
        self.assertIn("operator", reason.lower())

    def test_student_all_grades_denied(self):
        perms = build_copilot_permissions(_user("STUDENT"), request=_request())
        ok, _ = validate_copilot_query(
            _user("STUDENT"),
            "Show all grades for every student",
            perms,
            school=object(),
        )
        self.assertFalse(ok)


class GuidedTaskRbacTests(TestCase):
    def test_teacher_cannot_get_observability_topic(self):
        perms = build_copilot_permissions(_user("TEACHER"), request=_request())
        self.assertFalse(guided_task_allowed_for_permissions("observability_assistant", perms))

    def test_admin_manager_can_setup_recommend(self):
        perms = build_copilot_permissions(
            _user("ADMIN", is_staff=True),
            request=_request(host_kind="manager"),
        )
        self.assertTrue(guided_task_allowed_for_permissions("setup_recommend", perms))


class EngineRoomRbacTests(TestCase):
    def test_teacher_provisioning_query_denied(self):
        env = prepare_engine_room_rbac(
            _user("TEACHER"),
            "How do I create school and add a new tenant?",
            school=object(),
            active_url="/help/",
        )
        self.assertFalse(env.allowed)
        self.assertIn("operator", env.denial_reason.lower())

    def test_teacher_allowed_navigation(self):
        env = prepare_engine_room_rbac(
            _user("TEACHER"),
            "Where do I take attendance?",
            school=object(),
            active_url="/portal/teacher/",
        )
        self.assertTrue(env.allowed)
        self.assertIn("RBAC ENFORCEMENT", env.prompt)
        self.assertTrue(env.metadata.get("copilot_rbac_enforced"))


class CopilotInvokeGuardTests(TestCase):
    def test_guard_blocks_teacher_payroll_via_helpers_path(self):
        school = object()
        request = SimpleNamespace(
            user=_user("TEACHER"),
            school=school,
            path="/portal/",
            public_host_kind="tenant",
        )
        guard = guard_copilot_invoke(
            request=request,
            task_type="general_chat",
            prompt="Answer briefly.",
            user_query="Show staff payroll totals",
            metadata={"surface": "portal_ai_stream"},
        )
        self.assertFalse(guard.allowed)
        self.assertIn("payroll", guard.denial_reason.lower())
        self.assertEqual(guard.metadata.get("outcome"), "permission_refusal")

    def test_guard_injects_directives_when_allowed(self):
        request = SimpleNamespace(
            user=_user("TEACHER"),
            school=object(),
            path="/portal/teacher/",
            public_host_kind="tenant",
        )
        guard = guard_copilot_invoke(
            request=request,
            task_type="general_chat",
            prompt="How do I take attendance?",
            user_query="How do I take attendance?",
            metadata={},
        )
        self.assertTrue(guard.allowed)
        self.assertIn("RBAC ENFORCEMENT", guard.prompt)
        self.assertTrue(guard.metadata.get("copilot_rbac_enforced"))

    def test_guard_skips_when_already_enforced(self):
        request = SimpleNamespace(user=_user("TEACHER"), school=object(), path="/")
        guard = guard_copilot_invoke(
            request=request,
            task_type="general_chat",
            prompt="plain",
            user_query="anything",
            metadata={"copilot_rbac_enforced": True},
        )
        self.assertTrue(guard.allowed)
        self.assertEqual(guard.prompt, "plain")


class InvokeServiceLayerAiTests(TestCase):
    @patch("services.ai_helpers.invoke_with_request")
    def test_teacher_payroll_intent_denied(self, mock_invoke):
        school = object()
        user = _user("TEACHER")
        text, meta = invoke_service_layer_ai(
            user=user,
            school=school,
            task_type="teacher_comms_draft",
            prompt="Draft message",
            user_query="Show staff payroll totals",
            surface="teacher_comms",
        )
        self.assertIn("payroll", text.lower())
        self.assertEqual(meta.get("outcome"), "permission_refusal")
        mock_invoke.assert_not_called()

    @patch("services.ai_helpers.invoke_with_request", return_value=("ok draft", {"provider": "rules"}))
    def test_teacher_allowed_intent_invokes(self, mock_invoke):
        school = object()
        user = _user("TEACHER")
        text, meta = invoke_service_layer_ai(
            user=user,
            school=school,
            task_type="teacher_comms_draft",
            prompt="Draft message",
            user_query="Reminder about tomorrow's field trip",
            surface="teacher_comms",
        )
        self.assertEqual(text, "ok draft")
        mock_invoke.assert_called_once()
        self.assertTrue(mock_invoke.call_args.kwargs["metadata"].get("copilot_rbac_enforced"))


class RunAiPromptRbacTests(TestCase):
    @patch.dict("os.environ", {"RUNMYCAMPUS_AI_ENABLED": "1"}, clear=False)
    @patch("services.ai_helpers.invoke_with_request")
    def test_run_ai_prompt_denies_teacher_payroll_context(self, mock_invoke):
        from apps.platform_runtime.ai_providers import run_ai_prompt

        school = SimpleNamespace(pk=1)
        user = _user("TEACHER")
        text, meta = run_ai_prompt(
            "Summarize briefly.",
            "Show staff payroll totals for all employees",
            school,
            user=user,
            prompt_type="school_insights",
        )
        self.assertIn("payroll", text.lower())
        self.assertTrue(meta.get("denied"))
        mock_invoke.assert_not_called()

    @patch.dict("os.environ", {"RUNMYCAMPUS_AI_ENABLED": "1"}, clear=False)
    @patch("services.ai_helpers.invoke_with_request", return_value=("insight", {"provider": "rules"}))
    def test_run_ai_prompt_allowed_intent_invokes(self, mock_invoke):
        from apps.platform_runtime.ai_providers import run_ai_prompt

        school = SimpleNamespace(pk=1)
        user = _user("ADMIN", is_staff=True)
        text, meta = run_ai_prompt(
            "Summarize metrics.",
            "onboarding progress only",
            school,
            user=user,
            prompt_type="school_insights",
        )
        self.assertEqual(text, "insight")
        mock_invoke.assert_called_once()
