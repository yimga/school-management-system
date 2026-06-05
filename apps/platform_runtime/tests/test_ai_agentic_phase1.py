"""Agentic AI — Phase 1 (read-only) orchestration tests.

Covers the four invariants from ``docs/AI_AGENTIC_ACTIONS_DESIGN.md``:
flag-gated/default-off, read-only ONLY, server-side confirmation, every-attempt-audited.
"""

from __future__ import annotations

import os
from unittest import mock

from django.test import TestCase

from services import ai_agentic_service as svc
from services.ai_agentic import ActionContext, ProposedAction


def _ctx():
    return ActionContext(tenant_id="platform", user_id="42", user_roles=("ADMIN",))


class _EnvFlag:
    """Context manager to set/unset env flags around a test body."""

    def __init__(self, **flags):
        self._flags = flags
        self._prev: dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self._flags.items():
            self._prev[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, prev in self._prev.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class GateTests(TestCase):
    def test_flag_off_is_disabled_even_with_platform_ai_on(self):
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED=None, RUNMYCAMPUS_AI_ENABLED="1"):
            self.assertFalse(svc.agentic_phase1_enabled(school=None))

    def test_flag_on_and_platform_on_is_enabled(self):
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            self.assertTrue(svc.agentic_phase1_enabled(school=None))

    def test_flag_on_but_platform_off_is_disabled(self):
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED=None):
            self.assertFalse(svc.agentic_phase1_enabled(school=None))


class ReadOnlySurfaceTests(TestCase):
    def test_available_actions_are_read_only_and_bridged(self):
        names = {a.name for a in svc.available_readonly_actions()}
        # The three bridged read-only runners — and nothing mutating/destructive.
        self.assertIn("summarize_attendance_report", names)
        self.assertIn("summarize_outstanding_fees", names)
        self.assertIn("draft_parent_announcement", names)
        self.assertNotIn("send_parent_message", names)
        self.assertNotIn("mark_student_absent", names)
        self.assertNotIn("purge_student_record", names)

    def test_propose_filters_out_mutating_actions(self):
        with mock.patch("services.ai_helpers.is_ai_available", return_value=False):
            # "send to parent" maps to a MUTATING action in the mock router.
            out = svc.propose(prompt="please send to parent a note", ctx=_ctx())
        self.assertEqual(out, ())

    def test_propose_returns_read_only_match(self):
        with mock.patch("services.ai_helpers.is_ai_available", return_value=False):
            out = svc.propose(prompt="give me an attendance summary", ctx=_ctx())
        self.assertTrue(out)
        self.assertEqual(out[0].action, "summarize_attendance_report")


class ExecuteAndAuditTests(TestCase):
    databases = {"default"}

    def test_execute_read_only_writes_audit_and_confirms_server_side(self):
        from apps.platform_runtime.models_agentic_audit import AIAgenticActionAudit

        before = AIAgenticActionAudit.objects.count()
        proposed = ProposedAction(
            action="draft_parent_announcement",
            params={"topic": "sports day", "audience": "all_parents", "locale": "en"},
        )
        result = svc.execute(
            proposed=proposed, ctx=_ctx(), confirmed_by_user_id="42", school=None,
        )
        self.assertTrue(result.ok)
        self.assertIn("draft", result.result)
        self.assertEqual(AIAgenticActionAudit.objects.count(), before + 1)
        row = AIAgenticActionAudit.objects.order_by("-created_at").first()
        self.assertEqual(row.action, "draft_parent_announcement")
        self.assertEqual(row.impact, "read_only")
        self.assertEqual(row.outcome, "ok")
        self.assertTrue(row.executed)
        # confirmed_by hashed, never raw; actor hashed, never raw user id.
        self.assertTrue(row.confirmed_by_hash)
        self.assertNotEqual(row.actor_user_id_hash, "42")

    def test_execute_refuses_mutating_action_and_audits_block(self):
        from apps.platform_runtime.models_agentic_audit import AIAgenticActionAudit

        # Even though send_parent_message is a REGISTERED spec, Phase 1 refuses it.
        proposed = ProposedAction(action="send_parent_message", params={"channel": "sms"})
        result = svc.execute(
            proposed=proposed, ctx=_ctx(), confirmed_by_user_id="42", school=None,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.blocked_reason, "not_read_only")
        row = AIAgenticActionAudit.objects.order_by("-created_at").first()
        self.assertEqual(row.action, "send_parent_message")
        self.assertEqual(row.outcome, "blocked")
        self.assertFalse(row.executed)

    def test_audit_row_is_append_only(self):
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionAuditReadOnlyError,
        )

        proposed = ProposedAction(action="draft_parent_announcement", params={})
        svc.execute(proposed=proposed, ctx=_ctx(), confirmed_by_user_id="42", school=None)
        row = AIAgenticActionAudit.objects.order_by("-created_at").first()
        row.outcome = "error"
        with self.assertRaises(AIAgenticActionAuditReadOnlyError):
            row.save()
        with self.assertRaises(Exception):
            row.delete()
