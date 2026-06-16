"""Per-tenant impersonation gate: operators are scoped to assigned tenants.

Holding the platform.impersonate scope says an operator MAY impersonate; the
OperatorTenantAssignment gate says into WHICH tenant. switch_to_tenant returns
403 unless the actor is a superuser, holds an active assignment for the target
school, or holds an active JIT grant (the existing engine, integrated here).

No DB: the assignment lookup (has_active) is mocked so these run as fast
SimpleTestCases; the JIT branch exercises the real pure check_jit_authorization,
and is_active() is pure.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase
from django.utils import timezone

from apps.platform_runtime.models_operator_identity import OperatorTenantAssignment
from apps.schools.super_views_impersonation import operator_can_impersonate_school

_HAS_ACTIVE = (
    "apps.platform_runtime.models_operator_identity."
    "OperatorTenantAssignment.has_active"
)


class _User:
    def __init__(self, pk, is_superuser=False):
        self.pk = pk
        self.id = pk
        self.is_superuser = is_superuser


class _School:
    def __init__(self, pk, settings=None):
        self.pk = pk
        self.id = pk
        self.settings = settings or {}


def _jit(settings_grants):
    return {"operator_access": {"jit_grants": settings_grants}}


class OperatorImpersonationGateTests(SimpleTestCase):
    def test_superuser_bypasses_assignment_gate(self):
        # Root of trust — never self-lock before any assignment exists.
        self.assertTrue(
            operator_can_impersonate_school(_User(1, is_superuser=True), _School(10))
        )

    def test_active_assignment_grants_access(self):
        with mock.patch(_HAS_ACTIVE, return_value=True):
            self.assertTrue(
                operator_can_impersonate_school(_User(7), _School(10))
            )

    def test_active_jit_grant_grants_access(self):
        school = _School(
            10,
            settings=_jit(
                [
                    {
                        "operator_user_id": 7,
                        "expires_at_iso": "2999-01-01T00:00:00+00:00",
                        "reason": "ticket-42",
                    }
                ]
            ),
        )
        with mock.patch(_HAS_ACTIVE, return_value=False):
            self.assertTrue(operator_can_impersonate_school(_User(7), school))

    def test_no_assignment_no_jit_denies(self):
        with mock.patch(_HAS_ACTIVE, return_value=False):
            self.assertFalse(
                operator_can_impersonate_school(_User(7), _School(10))
            )

    def test_expired_jit_grant_denies(self):
        school = _School(
            10,
            settings=_jit(
                [
                    {
                        "operator_user_id": 7,
                        "expires_at_iso": "2000-01-01T00:00:00+00:00",
                        "reason": "stale",
                    }
                ]
            ),
        )
        with mock.patch(_HAS_ACTIVE, return_value=False):
            self.assertFalse(operator_can_impersonate_school(_User(7), school))

    def test_jit_grant_for_other_operator_denies(self):
        school = _School(
            10,
            settings=_jit(
                [
                    {
                        "operator_user_id": 999,
                        "expires_at_iso": "2999-01-01T00:00:00+00:00",
                        "reason": "someone-else",
                    }
                ]
            ),
        )
        with mock.patch(_HAS_ACTIVE, return_value=False):
            self.assertFalse(operator_can_impersonate_school(_User(7), school))


class OperatorTenantAssignmentModelTests(SimpleTestCase):
    def test_is_active_true_when_unrevoked_unexpired(self):
        a = OperatorTenantAssignment(operator_id=1, school_id=2)
        self.assertTrue(a.is_active())

    def test_is_active_false_when_revoked(self):
        a = OperatorTenantAssignment(
            operator_id=1, school_id=2, revoked_at=timezone.now()
        )
        self.assertFalse(a.is_active())

    def test_is_active_false_when_expired(self):
        a = OperatorTenantAssignment(
            operator_id=1,
            school_id=2,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(a.is_active())

    def test_is_active_true_when_expiry_in_future(self):
        a = OperatorTenantAssignment(
            operator_id=1,
            school_id=2,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(a.is_active())


class OperatorTenantAssignmentAuditTests(SimpleTestCase):
    """The grant/revoke lifecycle must emit an AuditLog row (best-effort)."""

    def test_record_lifecycle_audit_emits_expected_action(self):
        from apps.compliance.models_audit import AuditLog

        a = OperatorTenantAssignment(operator_id=1, school_id="s-1")
        with mock.patch.object(AuditLog.objects, "create") as create:
            a.record_lifecycle_audit(
                actor=_User(9),
                action=AuditLog.Action.PERMISSION_GRANT,
                reason="granted via admin",
            )
        self.assertEqual(create.call_count, 1)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["action"], AuditLog.Action.PERMISSION_GRANT)
        self.assertEqual(kwargs["model_name"], "OperatorTenantAssignment")
        self.assertEqual(kwargs["app_label"], "platform_runtime")
        self.assertEqual(kwargs["sensitivity"], AuditLog.Sensitivity.HIGH)
        self.assertEqual(kwargs["new_values"]["operator_id"], 1)

    def test_record_lifecycle_audit_never_raises_on_failure(self):
        from apps.compliance.models_audit import AuditLog

        a = OperatorTenantAssignment(operator_id=1, school_id="s-1")
        # Audit DB hiccup must not break the grant — helper swallows + logs.
        with mock.patch.object(
            AuditLog.objects, "create", side_effect=RuntimeError("db down")
        ):
            a.record_lifecycle_audit(
                actor=_User(9),
                action=AuditLog.Action.PERMISSION_GRANT,
                reason="x",
            )
