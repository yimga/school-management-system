"""Agentic AI — Phase 2 (mutating, reversible, confirm-gated) tests.

Exercises every gate: sub-flag default-off, reversible-only eligibility,
server-side confirmation, single-use confirm token, rate limit, the
intent-before-outcome two-row audit, and the reversal path.
"""

from __future__ import annotations

import os
import uuid

from django.test import TestCase

from services import ai_agentic_service as svc
from services.ai_agentic import ActionContext, ProposedAction
from apps.schools.models import School


def _ctx(tenant_id: str):
    return ActionContext(tenant_id=tenant_id, user_id="77", user_roles=("ADMIN",))


class _EnvFlag:
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


def _all_flags_on():
    return _EnvFlag(
        RMC_AI_AGENTIC_MUTATING_ENABLED="1",
        RMC_AI_AGENTIC_ENABLED="1",
        RUNMYCAMPUS_AI_ENABLED="1",
        RMC_AI_AGENTIC_MUTATING_MAX_PER_HOUR="30",
    )


class MutatingGateTests(TestCase):
    def test_sub_flag_off_disabled_even_when_phase1_on(self):
        with _EnvFlag(RMC_AI_AGENTIC_MUTATING_ENABLED=None,
                      RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            self.assertFalse(svc.agentic_mutating_enabled(school=None))

    def test_all_flags_on_enabled(self):
        with _all_flags_on():
            self.assertTrue(svc.agentic_mutating_enabled(school=None))

    def test_available_mutating_actions_are_reversible_only(self):
        names = {a.name for a in svc.available_mutating_actions()}
        self.assertEqual(names, {"mark_student_absent", "schedule_parent_callback"})
        # send_parent_message is mutating but NOT reversible -> excluded.
        self.assertNotIn("send_parent_message", names)


class ConfirmAndExecuteTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.school = School.objects.create(
            name="P2",
            slug=f"p2-{uuid.uuid4().hex[:8]}",
            subdomain=f"p2-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        self.tenant_id = str(self.school.id)

    def _token(self, action, params, user_id="77"):
        return svc.issue_confirm_token(action=action, params=params, user_id=user_id)

    def test_blocked_when_sub_flag_off(self):
        proposed = ProposedAction(action="schedule_parent_callback", params={"parent_id": "9"})
        with _EnvFlag(RMC_AI_AGENTIC_MUTATING_ENABLED=None,
                      RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", confirm_token="x", school=self.school,
            )
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "mutating_disabled")

    def test_non_reversible_action_refused(self):
        proposed = ProposedAction(action="send_parent_message", params={"parent_id": "9"})
        with _all_flags_on():
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77",
                confirm_token=self._token("send_parent_message", {"parent_id": "9"}),
                school=self.school,
            )
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "not_mutating_eligible")

    def test_missing_confirmation_refused(self):
        params = {"parent_id": "9"}
        proposed = ProposedAction(action="schedule_parent_callback", params=params)
        with _all_flags_on():
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="", confirm_token=self._token("schedule_parent_callback", params),
                school=self.school,
            )
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "confirmation_required")

    def test_bad_confirm_token_refused(self):
        params = {"parent_id": "9"}
        proposed = ProposedAction(action="schedule_parent_callback", params=params)
        with _all_flags_on():
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", confirm_token="forged-token",
                school=self.school,
            )
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "bad_confirm_token")

    def test_rate_limited(self):
        params = {"parent_id": "9"}
        proposed = ProposedAction(action="schedule_parent_callback", params=params)
        with _EnvFlag(RMC_AI_AGENTIC_MUTATING_ENABLED="1", RMC_AI_AGENTIC_ENABLED="1",
                      RUNMYCAMPUS_AI_ENABLED="1", RMC_AI_AGENTIC_MUTATING_MAX_PER_HOUR="0"):
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", confirm_token=self._token("schedule_parent_callback", params),
                school=self.school,
            )
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "rate_limited")

    def test_happy_path_executes_writes_two_rows_and_confirms_server_side(self):
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit,
            AIAgenticActionOutcome,
            AIAgenticActionPhase,
        )

        params = {"parent_id": "42", "preferred_time": "2026-06-10T10:00"}
        proposed = ProposedAction(action="schedule_parent_callback", params=params)
        with _all_flags_on():
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", confirm_token=self._token("schedule_parent_callback", params),
                school=self.school,
            )
        self.assertTrue(r.ok, r.error)
        self.assertTrue(r.audit_id)

        # Two rows share the audit_id: an intent (pending) and an outcome (ok).
        rows = AIAgenticActionAudit.objects.filter(audit_id=r.audit_id)
        self.assertEqual(rows.count(), 2)
        intent = rows.get(phase=AIAgenticActionPhase.INTENT)
        outcome = rows.get(phase=AIAgenticActionPhase.OUTCOME)
        self.assertEqual(intent.outcome, AIAgenticActionOutcome.PENDING)
        self.assertEqual(outcome.outcome, AIAgenticActionOutcome.OK)
        self.assertTrue(outcome.executed)
        # confirmed_by recorded as a hash of the server-supplied id, never raw.
        self.assertTrue(outcome.confirmed_by_hash)
        self.assertNotEqual(outcome.confirmed_by_hash, "77")
        # The entry actually landed in the tenant queue, carrying a reversal handle.
        self.school.refresh_from_db()
        queue = (self.school.settings or {}).get("callback_queue") or []
        self.assertEqual(len(queue), 1)
        self.assertTrue(queue[0].get("entry_id"))

    def test_reverse_action_removes_entry_and_blocks_double_reverse(self):
        params = {"parent_id": "42"}
        proposed = ProposedAction(action="schedule_parent_callback", params=params)
        with _all_flags_on():
            r = svc.confirm_and_execute(
                proposed=proposed, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", confirm_token=self._token("schedule_parent_callback", params),
                school=self.school,
            )
            self.assertTrue(r.ok)
            self.school.refresh_from_db()
            self.assertEqual(len((self.school.settings or {}).get("callback_queue") or []), 1)

            rev = svc.reverse_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", school=self.school,
            )
            self.assertTrue(rev.ok, rev.error)
            self.school.refresh_from_db()
            self.assertEqual(len((self.school.settings or {}).get("callback_queue") or []), 0)

            # Second reverse is refused.
            rev2 = svc.reverse_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", school=self.school,
            )
            self.assertFalse(rev2.ok)
            self.assertEqual(rev2.blocked_reason, "already_reversed")

    def test_reverse_unknown_audit_id_refused(self):
        with _all_flags_on():
            rev = svc.reverse_action(
                audit_id="ag_doesnotexist", ctx=_ctx(self.tenant_id),
                confirmed_by_user_id="77", school=self.school,
            )
        self.assertFalse(rev.ok)
        self.assertEqual(rev.blocked_reason, "not_found")
