"""Wave K (v3.95.0 — 2026-05-26) — Agentic AI kernel tests.

Mock-mode only. Never hits LiteLLM. The helper invoke seam is mocked.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_agentic import (
    ActionContext,
    ActionSpec,
    ExecutionResult,
    ProposedAction,
    execute_action,
    get_action,
    list_actions,
    propose_actions,
    register_action,
    verify_permission,
)


def _ctx(**kw):
    defaults = dict(
        tenant_id="t1",
        user_id="user-42",
        user_roles=("ADMIN",),
        confirmed_by="",
    )
    defaults.update(kw)
    return ActionContext(**defaults)


class RegistryTests(SimpleTestCase):

    def test_seeded_actions_present(self):
        names = {a.name for a in list_actions()}
        for must in ("summarize_attendance_report", "summarize_outstanding_fees",
                     "draft_parent_announcement", "send_parent_message",
                     "mark_student_absent", "apply_fee_waiver",
                     "schedule_parent_callback", "purge_student_record"):
            self.assertIn(must, names)

    def test_register_overwrites_existing(self):
        original = get_action("draft_parent_announcement")
        try:
            register_action(ActionSpec(
                name="draft_parent_announcement",
                description="overridden",
                impact="read_only",
                required_roles=("CUSTOM",),
                requires_confirmation=False,
            ))
            self.assertEqual(get_action("draft_parent_announcement").description, "overridden")
        finally:
            # Restore the seeded spec.
            register_action(original)


class PermissionVerifierTests(SimpleTestCase):

    def test_admin_can_run_anything(self):
        spec = get_action("purge_student_record")
        err = verify_permission(spec, _ctx(user_roles=("ADMIN",)))
        self.assertEqual(err, "")

    def test_missing_tenant_fails(self):
        spec = get_action("summarize_attendance_report")
        err = verify_permission(spec, _ctx(tenant_id=""))
        self.assertIn("tenant_id missing", err)

    def test_missing_user_fails(self):
        spec = get_action("summarize_attendance_report")
        err = verify_permission(spec, _ctx(user_id=""))
        self.assertIn("user_id missing", err)

    def test_wrong_role_blocked(self):
        spec = get_action("apply_fee_waiver")
        # PARENT can't apply waivers.
        err = verify_permission(spec, _ctx(user_roles=("PARENT",)))
        self.assertIn("lacks required role", err)

    def test_correct_role_passes(self):
        spec = get_action("apply_fee_waiver")
        err = verify_permission(spec, _ctx(user_roles=("BURSAR",)))
        self.assertEqual(err, "")


class ProposeActionsTests(SimpleTestCase):

    def test_mock_attendance_keyword(self):
        proposals = propose_actions(
            prompt="How is attendance today in class 5A?",
            ctx=_ctx(),
        )
        names = [p.action for p in proposals]
        self.assertIn("summarize_attendance_report", names)

    def test_mock_fees_keyword(self):
        proposals = propose_actions(
            prompt="Show me outstanding fees for class 6",
            ctx=_ctx(),
        )
        self.assertIn("summarize_outstanding_fees", [p.action for p in proposals])

    def test_mock_empty_prompt_returns_empty(self):
        self.assertEqual(propose_actions(prompt="", ctx=_ctx()), ())
        self.assertEqual(propose_actions(prompt="   ", ctx=_ctx()), ())

    def test_mock_unrecognized_prompt_returns_empty(self):
        self.assertEqual(
            propose_actions(prompt="hello what is the weather", ctx=_ctx()),
            (),
        )

    def test_live_mode_invokes_helper(self):
        captured = {}

        def fake_helper(*, task_id, prompt, schema_hint, tenant_id):
            captured["task_id"] = task_id
            captured["prompt"] = prompt
            captured["tenant_id"] = tenant_id
            return {
                "actions": [
                    {"action": "summarize_attendance_report",
                     "params": {"class_id": "5A", "date_range": "today"},
                     "rationale": "live test",
                     "confidence": 0.85}
                ]
            }

        proposals = propose_actions(
            prompt="show class 5A attendance",
            ctx=_ctx(),
            mock_mode=False,
            helper_invoke_json_task=fake_helper,
        )
        self.assertEqual(captured["task_id"], "ai_agentic.propose_actions")
        self.assertEqual(captured["tenant_id"], "t1")
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].action, "summarize_attendance_report")
        self.assertAlmostEqual(proposals[0].confidence, 0.85)

    def test_live_mode_unknown_action_dropped(self):
        def fake_helper(**_kw):
            return {"actions": [{"action": "make_coffee", "params": {}}]}

        out = propose_actions(prompt="x", ctx=_ctx(),
                               mock_mode=False,
                               helper_invoke_json_task=fake_helper)
        self.assertEqual(out, ())

    def test_live_mode_malformed_response_safe(self):
        def bad_helper(**_kw):
            return "not a dict"

        out = propose_actions(prompt="x", ctx=_ctx(),
                               mock_mode=False,
                               helper_invoke_json_task=bad_helper)
        self.assertEqual(out, ())

    def test_live_mode_helper_exception_swallowed(self):
        def boom(**_kw):
            raise RuntimeError("LiteLLM down")

        out = propose_actions(prompt="x", ctx=_ctx(),
                               mock_mode=False,
                               helper_invoke_json_task=boom)
        self.assertEqual(out, ())


class ExecuteActionTests(SimpleTestCase):

    def test_unknown_action_blocked(self):
        result = execute_action(
            ProposedAction(action="nonexistent", params={}),
            ctx=_ctx(),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.blocked_reason, "unknown_action")

    def test_permission_denied_blocked(self):
        result = execute_action(
            ProposedAction(action="apply_fee_waiver", params={}),
            ctx=_ctx(user_roles=("PARENT",), confirmed_by="user-42"),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.blocked_reason, "permission_denied")

    def test_confirmation_required_but_missing(self):
        result = execute_action(
            ProposedAction(action="apply_fee_waiver", params={}),
            ctx=_ctx(user_roles=("BURSAR",), confirmed_by=""),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.blocked_reason, "confirmation_required")

    def test_read_only_no_confirmation_needed(self):
        result = execute_action(
            ProposedAction(action="summarize_attendance_report", params={}),
            ctx=_ctx(user_roles=("TEACHER",)),
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.audit_id.startswith("ag_"))

    def test_destructive_requires_confirmation(self):
        # Even ADMIN has to confirm a DESTRUCTIVE action.
        result = execute_action(
            ProposedAction(action="purge_student_record", params={}),
            ctx=_ctx(user_roles=("ADMIN",), confirmed_by=""),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.blocked_reason, "confirmation_required")

    def test_confirmed_destructive_runs(self):
        result = execute_action(
            ProposedAction(action="purge_student_record",
                            params={"student_id": "s1", "justification": "duplicate"}),
            ctx=_ctx(user_roles=("ADMIN",), confirmed_by="user-42"),
        )
        self.assertTrue(result.ok)

    def test_runner_executes_when_supplied(self):
        captured = {}

        def runner(prop, c):
            captured["action"] = prop.action
            captured["params"] = prop.params
            captured["user"] = c.user_id
            return {"sent": True}

        result = execute_action(
            ProposedAction(action="send_parent_message",
                            params={"parent_id": "p1", "channel": "whatsapp", "body": "Hi"}),
            ctx=_ctx(user_roles=("COMMS_STAFF",), confirmed_by="user-42"),
            runner=runner,
        )
        self.assertTrue(result.ok)
        self.assertEqual(captured["action"], "send_parent_message")
        self.assertEqual(result.result, {"sent": True})

    def test_runner_exception_caught(self):
        def broken_runner(_p, _c):
            raise RuntimeError("DB down")

        result = execute_action(
            ProposedAction(action="send_parent_message",
                            params={"parent_id": "p1", "channel": "whatsapp", "body": "Hi"}),
            ctx=_ctx(user_roles=("COMMS_STAFF",), confirmed_by="user-42"),
            runner=broken_runner,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.blocked_reason, "runner_exception")
        self.assertIn("DB down", result.error)

    def test_audit_sink_invoked_on_execute(self):
        captured = []

        def sink(rec):
            captured.append(rec)

        execute_action(
            ProposedAction(action="summarize_attendance_report", params={}),
            ctx=_ctx(user_roles=("TEACHER",)),
            runner=lambda *_a: {"ok": True},
            audit_sink=sink,
        )
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["action"], "summarize_attendance_report")
        self.assertTrue(captured[0]["executed"])

    def test_audit_sink_failure_does_not_block(self):
        def broken_sink(_rec):
            raise RuntimeError("audit DB down")

        result = execute_action(
            ProposedAction(action="summarize_attendance_report", params={}),
            ctx=_ctx(user_roles=("TEACHER",)),
            runner=lambda *_a: {"ok": True},
            audit_sink=broken_sink,
        )
        self.assertTrue(result.ok)  # core path still succeeds
