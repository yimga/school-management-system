"""Agentic AI — Phase 3 (destructive, DUAL-CONTROL) tests.

Two layers:
- ``DualControlLogicTests`` patch the compliance-backed runner so the gate logic
  (flags, eligibility, typed phrase, requester≠approver, expiry, single-finalize,
  reject) is exercised deterministically without people/compliance fixtures.
- ``EraseRequestDelegationTests`` build real School / User / StudentProfile rows
  and prove the request half creates a real PENDING ``EraseRequest`` and the
  approve half drives it to COMPLETED via the sanctioned GDPR erasure pipeline —
  i.e. Phase 3 opens NO new delete path.
"""

from __future__ import annotations

import os
import uuid
from unittest import mock

from django.test import TestCase

from services import ai_agentic_service as svc
from services.ai_agentic import ActionContext, ProposedAction

_RUNNERS_MOD = "services.ai_agentic_runners_destructive"


def _ctx(tenant_id: str, user_id: str = "77", roles=("ADMIN",)):
    return ActionContext(tenant_id=tenant_id, user_id=user_id, user_roles=tuple(roles))


# An approver who satisfies the "≥1 DPO in the pair" rule (default-on).
_DPO_ROLES = ("ADMIN", "DPO")


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
        RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED="1",
        RMC_AI_AGENTIC_ENABLED="1",
        RUNMYCAMPUS_AI_ENABLED="1",
        RMC_AI_AGENTIC_DESTRUCTIVE_MAX_PER_HOUR="5",
    )


class GateTests(TestCase):
    def test_sub_flag_off_disabled_even_when_phase1_on(self):
        with _EnvFlag(RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED=None,
                      RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            self.assertFalse(svc.agentic_destructive_enabled(school=None))

    def test_all_flags_on_enabled(self):
        with _all_flags_on():
            self.assertTrue(svc.agentic_destructive_enabled(school=None))

    def test_available_destructive_actions_are_nonreversible_with_runner(self):
        names = {a.name for a in svc.available_destructive_actions()}
        self.assertEqual(names, {"purge_student_record"})

    def test_confirm_phrase_shape(self):
        self.assertEqual(svc._destructive_confirm_phrase("42"), "ERASE 42")

    def test_roles_include_dpo_uses_enum(self):
        self.assertTrue(svc._roles_include_dpo(("ADMIN", "DPO")))
        self.assertFalse(svc._roles_include_dpo(("ADMIN", "PRINCIPAL")))

    def test_require_dpo_default_on(self):
        with _EnvFlag(RMC_AI_AGENTIC_DESTRUCTIVE_REQUIRE_DPO=None):
            self.assertTrue(svc._destructive_require_dpo())
        with _EnvFlag(RMC_AI_AGENTIC_DESTRUCTIVE_REQUIRE_DPO="0"):
            self.assertFalse(svc._destructive_require_dpo())


# --- Patched runner: isolates the dual-control gate logic --------------------

def _fake_create_ok(proposed, ctx):
    sid = str((proposed.params or {}).get("student_id") or "")
    return {"ok": True, "erase_request_id": 4242, "student_pk": sid or "42"}


class DualControlLogicTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.tenant_id = "t-" + uuid.uuid4().hex[:8]
        self._runner_calls: list = []

        def _fake_runner(proposed, ctx):
            self._runner_calls.append(
                (str((proposed.params or {}).get("_erase_request_id")), ctx.confirmed_by)
            )
            return {"ok": True, "status": "completed"}

        self._fake_runner = _fake_runner
        # Patch the source module so the service's lazy imports see the fakes.
        self._patchers = [
            mock.patch(f"{_RUNNERS_MOD}.create_purge_request", _fake_create_ok),
            mock.patch(f"{_RUNNERS_MOD}.OPT_IN_DESTRUCTIVE_RUNNERS",
                       {"purge_student_record": _fake_runner}),
            mock.patch(f"{_RUNNERS_MOD}.reject_purge_request",
                       lambda erid: {"ok": True, "erase_request_id": erid, "status": "rejected"}),
        ]
        for p in self._patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patchers])

    def _proposed(self, student_id="42"):
        return ProposedAction(action="purge_student_record",
                              params={"student_id": student_id, "justification": "test"})

    def _request(self, *, user_id="77", phrase="ERASE 42", student_id="42", roles=("ADMIN",)):
        return svc.request_destructive_action(
            proposed=self._proposed(student_id), ctx=_ctx(self.tenant_id, user_id, roles),
            requested_by_user_id=user_id, confirm_phrase=phrase, school=None,
        )

    def test_request_blocked_when_flag_off(self):
        with _EnvFlag(RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED=None,
                      RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            r = self._request()
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "destructive_disabled")

    def test_request_bad_phrase_refused(self):
        with _all_flags_on():
            r = self._request(phrase="erase 42")  # wrong case / format
        self.assertFalse(r.ok)
        self.assertEqual(r.blocked_reason, "bad_confirm_phrase")

    def test_request_ok_writes_pending_request_row(self):
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit, AIAgenticActionOutcome, AIAgenticActionPhase,
        )
        with _all_flags_on():
            r = self._request()
        self.assertTrue(r.ok, r.error)
        self.assertTrue(r.audit_id)
        row = AIAgenticActionAudit.objects.get(
            audit_id=r.audit_id, phase=AIAgenticActionPhase.REQUEST)
        self.assertEqual(row.outcome, AIAgenticActionOutcome.PENDING)
        self.assertEqual(row.reversal_payload.get("erase_request_id"), "4242")
        # Appears in the pending list.
        pend = svc.pending_destructive_requests(tenant_id=self.tenant_id)
        self.assertEqual([p["audit_id"] for p in pend], [r.audit_id])

    def test_self_approval_forbidden(self):
        with _all_flags_on():
            r = self._request(user_id="77")
            rev = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "77"),
                approver_user_id="77", confirm_phrase="ERASE 42", school=None,
            )
        self.assertFalse(rev.ok)
        self.assertEqual(rev.blocked_reason, "self_approval_forbidden")
        self.assertEqual(self._runner_calls, [])  # never ran

    def test_distinct_approver_executes_and_finalizes(self):
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit, AIAgenticActionPhase,
        )
        with _all_flags_on():
            r = self._request(user_id="77")
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88", _DPO_ROLES),
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertTrue(ap.ok, ap.error)
        # The sanctioned runner ran with the request's erase id + the approver.
        self.assertEqual(self._runner_calls, [("4242", "88")])
        # Three-row trail: request / approval / outcome, all sharing the id.
        phases = set(
            AIAgenticActionAudit.objects.filter(audit_id=r.audit_id)
            .values_list("phase", flat=True)
        )
        self.assertEqual(
            phases,
            {AIAgenticActionPhase.REQUEST, AIAgenticActionPhase.APPROVAL,
             AIAgenticActionPhase.OUTCOME},
        )

    def test_approve_bad_phrase_refused(self):
        with _all_flags_on():
            r = self._request(user_id="77")
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88", _DPO_ROLES),
                approver_user_id="88", confirm_phrase="ERASE wrong", school=None,
            )
        self.assertFalse(ap.ok)
        self.assertEqual(ap.blocked_reason, "bad_confirm_phrase")
        self.assertEqual(self._runner_calls, [])

    def test_expired_request_cannot_be_approved(self):
        with _all_flags_on():
            r = self._request(user_id="77")
            with mock.patch.object(svc, "_DESTRUCTIVE_REQUEST_TTL_SECONDS", -1):
                ap = svc.approve_destructive_action(
                    audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88"),
                    approver_user_id="88", confirm_phrase="ERASE 42", school=None,
                )
        self.assertFalse(ap.ok)
        self.assertEqual(ap.blocked_reason, "request_expired")
        self.assertEqual(self._runner_calls, [])

    def test_double_approve_refused(self):
        with _all_flags_on():
            r = self._request(user_id="77")
            ap1 = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88", _DPO_ROLES),
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
            self.assertTrue(ap1.ok)
            ap2 = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "99"),
                approver_user_id="99", confirm_phrase="ERASE 42", school=None,
            )
        self.assertFalse(ap2.ok)
        self.assertEqual(ap2.blocked_reason, "already_finalized")

    def test_reject_cancels_and_blocks_later_approve(self):
        with _all_flags_on():
            r = self._request(user_id="77")
            rej = svc.reject_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "77"),
                actor_user_id="77", school=None,
            )
            self.assertTrue(rej.ok, rej.error)
            # No longer pending.
            self.assertEqual(svc.pending_destructive_requests(tenant_id=self.tenant_id), [])
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88"),
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertFalse(ap.ok)
        self.assertEqual(ap.blocked_reason, "already_finalized")
        self.assertEqual(self._runner_calls, [])

    def test_blocked_approval_is_audited_but_does_not_finalize(self):
        from apps.platform_runtime.models_agentic_audit import (
            AIAgenticActionAudit, AIAgenticActionOutcome, AIAgenticActionPhase,
        )
        with _all_flags_on():
            r = self._request(user_id="77")
            # Self-approval attempt: blocked, but must leave a trail.
            svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "77"),
                approver_user_id="77", confirm_phrase="ERASE 42", school=None,
            )
            # A blocked APPROVAL-phase row was recorded...
            blocked = AIAgenticActionAudit.objects.filter(
                audit_id=r.audit_id, phase=AIAgenticActionPhase.APPROVAL,
                outcome=AIAgenticActionOutcome.BLOCKED,
            )
            self.assertEqual(blocked.count(), 1)
            self.assertEqual(blocked.first().blocked_reason, "self_approval_forbidden")
            # ...but the request did NOT finalize — a legitimate approver still works.
            self.assertEqual([p["audit_id"] for p in
                              svc.pending_destructive_requests(tenant_id=self.tenant_id)],
                             [r.audit_id])
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88", _DPO_ROLES),
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertTrue(ap.ok, ap.error)
        self.assertEqual(self._runner_calls, [("4242", "88")])

    def test_approve_unknown_id_refused(self):
        with _all_flags_on():
            ap = svc.approve_destructive_action(
                audit_id="ag_doesnotexist", ctx=_ctx(self.tenant_id, "88"),
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertFalse(ap.ok)
        self.assertEqual(ap.blocked_reason, "not_found")

    def test_dpo_required_blocks_pair_without_dpo(self):
        # Requester ADMIN, approver ADMIN (distinct, correct phrase) — but neither
        # is a DPO, so the data-protection dual-control rule blocks it.
        with _all_flags_on():
            r = self._request(user_id="77")  # requester roles = ("ADMIN",)
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88"),  # ("ADMIN",)
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertFalse(ap.ok)
        self.assertEqual(ap.blocked_reason, "dpo_required")
        self.assertEqual(self._runner_calls, [])  # never ran

    def test_dpo_satisfied_by_requester(self):
        # If party A (requester) is a DPO, an ADMIN-only approver is sufficient.
        with _all_flags_on():
            r = self._request(user_id="77", roles=_DPO_ROLES)
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88"),  # ADMIN only
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertTrue(ap.ok, ap.error)
        self.assertEqual(self._runner_calls, [("4242", "88")])

    def test_dpo_requirement_can_be_disabled(self):
        # With the requirement off, an ADMIN/ADMIN pair is allowed.
        with _EnvFlag(RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED="1", RMC_AI_AGENTIC_ENABLED="1",
                      RUNMYCAMPUS_AI_ENABLED="1", RMC_AI_AGENTIC_DESTRUCTIVE_MAX_PER_HOUR="5",
                      RMC_AI_AGENTIC_DESTRUCTIVE_REQUIRE_DPO="0"):
            r = self._request(user_id="77")
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id, ctx=_ctx(self.tenant_id, "88"),
                approver_user_id="88", confirm_phrase="ERASE 42", school=None,
            )
        self.assertTrue(ap.ok, ap.error)


class EraseRequestDelegationTests(TestCase):
    """Proves Phase 3 rides the existing compliance erasure pipeline (no new
    delete path) — with REAL School / User / StudentProfile fixtures."""

    databases = {"default"}

    def setUp(self):
        from apps.accounts.models import User
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        suffix = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="P3", slug=f"p3-{suffix}", subdomain=f"p3-{suffix}", is_active=True)
        self.tenant_id = str(self.school.id)
        self.student_user = User.objects.create(
            username=f"stu-{suffix}", email=f"stu-{suffix}@example.test",
            role=User.Role.STUDENT.value)
        self.student = StudentProfile.objects.create(
            school=self.school, user=self.student_user,
            first_name="Ada", last_name="Lovelace", student_code=f"SC-{suffix}")
        self.requester = User.objects.create(
            username=f"req-{suffix}", role=User.Role.ADMIN.value)
        # Approver is a DPO so the data-protection dual-control rule is satisfied.
        self.approver = User.objects.create(
            username=f"app-{suffix}", role=User.Role.DPO.value)

    def _proposed(self):
        return ProposedAction(action="purge_student_record",
                              params={"student_id": str(self.student.pk),
                                      "justification": "duplicate record"})

    def test_request_creates_real_pending_erase_request(self):
        from apps.compliance.models import EraseRequest

        with _all_flags_on():
            r = svc.request_destructive_action(
                proposed=self._proposed(),
                ctx=_ctx(self.tenant_id, str(self.requester.id)),
                requested_by_user_id=str(self.requester.id),
                confirm_phrase=f"ERASE {self.student.pk}", school=self.school,
            )
        self.assertTrue(r.ok, r.error)
        er = EraseRequest.objects.get(school=self.school, subject_user=self.student_user)
        self.assertEqual(er.status, EraseRequest.Status.PENDING)
        self.assertEqual(er.requested_by_id, self.requester.id)

    def test_full_dual_control_drives_erasure_to_completed(self):
        from apps.compliance.models import EraseRequest

        with _all_flags_on():
            r = svc.request_destructive_action(
                proposed=self._proposed(),
                ctx=_ctx(self.tenant_id, str(self.requester.id)),
                requested_by_user_id=str(self.requester.id),
                confirm_phrase=f"ERASE {self.student.pk}", school=self.school,
            )
            self.assertTrue(r.ok, r.error)
            ap = svc.approve_destructive_action(
                audit_id=r.audit_id,
                ctx=_ctx(self.tenant_id, str(self.approver.id), _DPO_ROLES),
                approver_user_id=str(self.approver.id),
                confirm_phrase=f"ERASE {self.student.pk}", school=self.school,
            )
        self.assertTrue(ap.ok, ap.error)
        er = EraseRequest.objects.get(school=self.school, subject_user=self.student_user)
        self.assertEqual(er.status, EraseRequest.Status.COMPLETED)
        # The student PII was anonymized by the sanctioned scrub.
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Deleted")
        self.assertFalse(self.student.is_active)
