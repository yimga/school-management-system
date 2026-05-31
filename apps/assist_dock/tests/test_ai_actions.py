"""v4.00.94 Wave D — AI action vocabulary + invocation tests."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.assist_dock import default_ai_actions  # noqa: F401 — seed
from apps.assist_dock.ai_actions import (
    PROMPT_MAX_CHARS,
    RESPONSE_MAX_CHARS,
    AIAction,
    actions_as_jsonable,
    get_action,
    invoke_action,
    register_action,
    render_prompt,
    unregister_action,
)


class ActionValidationTests(SimpleTestCase):
    def test_id_required(self):
        with self.assertRaises(ValueError):
            AIAction(id="", label="x", prompt_template="hi")

    def test_prompt_template_required(self):
        with self.assertRaises(ValueError):
            AIAction(id="x", label="x", prompt_template="")

    def test_valid_constructs(self):
        a = AIAction(id="x", label="X", prompt_template="hi {role}")
        self.assertEqual(a.id, "x")


class DefaultsSeededTests(SimpleTestCase):
    def test_four_default_actions_present(self):
        for action_id in ("summarize", "explain", "draft", "translate"):
            self.assertIsNotNone(
                get_action(action_id), f"missing default action {action_id!r}"
            )


class RenderPromptTests(SimpleTestCase):
    def test_substitutes_known_keys(self):
        a = AIAction(
            id="x",
            label="X",
            prompt_template="page={page_path} role={role} q={user_query}",
        )
        prompt = render_prompt(
            a,
            {
                "page_path": "/portal/dashboard/",
                "role": "TEACHER",
                "user_query": "why?",
            },
        )
        self.assertIn("/portal/dashboard/", prompt)
        self.assertIn("TEACHER", prompt)
        self.assertIn("why?", prompt)

    def test_unknown_substitution_falls_back_to_template(self):
        a = AIAction(id="x", label="X", prompt_template="hi {nope}")
        prompt = render_prompt(a, {})
        self.assertTrue(prompt.startswith("hi "))

    def test_truncated_to_max(self):
        big = "{page_excerpt}"
        a = AIAction(id="x", label="X", prompt_template=big)
        ctx = {"page_excerpt": "a" * 5000}
        out = render_prompt(a, ctx)
        # page_excerpt is itself capped at 2000 chars before substitution.
        self.assertLessEqual(len(out), PROMPT_MAX_CHARS)

    def test_role_extracted_from_context(self):
        a = AIAction(id="x", label="X", prompt_template="role={role}")
        prompt = render_prompt(a, {"role": "BURSAR"})
        self.assertIn("BURSAR", prompt)


class InvokeActionTests(SimpleTestCase):
    def setUp(self):
        self.request = mock.Mock()
        self.request.user = mock.Mock(is_authenticated=True, active_role="TEACHER")

    def test_unknown_action_returns_error_envelope(self):
        out = invoke_action(action_id="does-not-exist", request=self.request)
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "unknown_action")

    def test_gateway_unavailable_envelope(self):
        try:
            register_action(AIAction(id="t1", label="T1", prompt_template="hi"))
            with mock.patch.dict("sys.modules", {"services.ai_helpers": None}):
                with mock.patch(
                    "builtins.__import__", side_effect=ImportError("no mod")
                ):
                    out = invoke_action(action_id="t1", request=self.request)
            self.assertFalse(out["ok"])
            self.assertEqual(out["error"], "gateway_unavailable")
        finally:
            unregister_action("t1")

    def test_gateway_disabled_by_policy(self):
        try:
            register_action(AIAction(id="t2", label="T2", prompt_template="hi"))
            with mock.patch(
                "services.ai_helpers.invoke_with_request", return_value=None
            ):
                out = invoke_action(action_id="t2", request=self.request)
            self.assertFalse(out["ok"])
            self.assertEqual(out["error"], "ai_disabled_by_policy")
        finally:
            unregister_action("t2")

    def test_gateway_exception_caught(self):
        try:
            register_action(AIAction(id="t3", label="T3", prompt_template="hi"))
            with mock.patch(
                "services.ai_helpers.invoke_with_request",
                side_effect=RuntimeError("boom"),
            ):
                out = invoke_action(action_id="t3", request=self.request)
            self.assertFalse(out["ok"])
            self.assertEqual(out["error"], "gateway_error")
        finally:
            unregister_action("t3")

    def test_success_envelope_returns_text(self):
        try:
            register_action(AIAction(id="t4", label="T4", prompt_template="hi {role}"))
            with mock.patch(
                "services.ai_helpers.invoke_with_request",
                return_value=("Hello TEACHER", {"tier": "litellm"}),
            ):
                out = invoke_action(action_id="t4", request=self.request)
            self.assertTrue(out["ok"])
            self.assertEqual(out["text"], "Hello TEACHER")
            self.assertEqual(out["tier"], "litellm")
            self.assertEqual(out["action_id"], "t4")
        finally:
            unregister_action("t4")

    def test_response_truncated_to_max(self):
        try:
            register_action(AIAction(id="t5", label="T5", prompt_template="hi"))
            big_response = "x" * 10000
            with mock.patch(
                "services.ai_helpers.invoke_with_request",
                return_value=(big_response, {}),
            ):
                out = invoke_action(action_id="t5", request=self.request)
            self.assertEqual(len(out["text"]), RESPONSE_MAX_CHARS)
        finally:
            unregister_action("t5")


class JsonableTests(SimpleTestCase):
    def test_action_as_jsonable_keys(self):
        a = AIAction(id="x", label="X", icon="bi-x", prompt_template="hi", order=15)
        out = actions_as_jsonable([a])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "x")
        self.assertEqual(out[0]["order"], 15)
