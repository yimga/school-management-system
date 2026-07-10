"""PDP enforcement promotion (2026-07-09) — surface-level proof battery.

Proves, at the HTTP/view layer, that the three promoted IAM surfaces are
REALLY enforced (not decoratively):

  - parity: the population each surface's own RBAC gate admits still passes
    (via the seeded baseline allow-rules, NOT god-mode);
  - denial: outsiders raise PermissionDenied at the PDP layer;
  - bindingness: a tenant deny rule (priority < 500) blocks an
    otherwise-allowed admin — operator policy has teeth now;
  - kill switch: deactivating a baseline rule fail-closes its surface;
  - failure injection: a crashing parity probe or a crashing decide() both
    fail CLOSED in enforce mode;
  - rollback: advisory mode never blocks; off mode never logs.
"""

from __future__ import annotations

import os
import unittest
import uuid
from unittest import mock

from django.conf import settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.views_tenant_identity import (
    tenant_identity_regulator_grant,
    tenant_identity_roster,
)
from apps.policies.models import PolicyDecisionLog, PolicyRule
from apps.schools.models import School, SchoolMembership

_BASELINE_CODES = (
    "iam-baseline-access-role-manage",
    "iam-baseline-tenant-identity-manage",
    "iam-baseline-regulatory-access-grant",
)


class _IamSurfaceFixture(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="PDP School",
            slug=f"pdp-{uuid.uuid4().hex[:10]}",
            subdomain=f"pdp-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        # Deliberately NOT a superuser: proves the baseline-rule path, not god-mode.
        self.admin = User.objects.create_user(
            username=f"pdpadm-{uuid.uuid4().hex[:6]}",
            email="pdp-admin@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username=f"pdptch-{uuid.uuid4().hex[:6]}",
            email="pdp-teacher@example.com",
            password="pass12345678",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        SchoolMembership.objects.create(
            user=self.teacher,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        self.factory = RequestFactory()

    def _request(self, user, path: str):
        request = self.factory.get(path)
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _baseline(self, code: str) -> PolicyRule:
        return PolicyRule.objects.get(school__isnull=True, code=code)


class SeededBaselineRuleTests(_IamSurfaceFixture):
    def test_baseline_rules_seeded_with_parity_condition(self) -> None:
        for code in _BASELINE_CODES:
            rule = self._baseline(code)
            self.assertTrue(rule.is_active, code)
            self.assertEqual(rule.effect, PolicyRule.Effect.ALLOW, code)
            self.assertEqual(rule.priority, 500, code)
            self.assertEqual(
                rule.conditions,
                [{"attr": "subject.rbac_allowed", "op": "eq", "value": True}],
                code,
            )

    @unittest.skipIf(
        os.environ.get("POLICY_PDP_ENFORCEMENT_MODE"),
        "environment overrides the deployed default",
    )
    def test_deployed_default_mode_is_enforce(self) -> None:
        self.assertEqual(settings.POLICY_PDP_ENFORCEMENT_MODE, "enforce")


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="enforce")
class EnforcedSurfaceTests(_IamSurfaceFixture):
    def test_roster_admin_allowed_via_baseline_rule_not_god_mode(self) -> None:
        response = tenant_identity_roster(self._request(self.admin, "/backend/identity/"))
        self.assertEqual(response.status_code, 200)
        log = PolicyDecisionLog.objects.order_by("-created_at").first()
        self.assertEqual(log.effect, "allow")
        self.assertEqual(log.matched_rule.code, "iam-baseline-tenant-identity-manage")

    def test_regulator_grant_admin_allowed_via_baseline_rule(self) -> None:
        response = tenant_identity_regulator_grant(
            self._request(self.admin, "/backend/identity/regulator-grant/")
        )
        self.assertEqual(response.status_code, 200)
        log = PolicyDecisionLog.objects.order_by("-created_at").first()
        self.assertEqual(log.effect, "allow")
        self.assertEqual(
            log.matched_rule.code, "iam-baseline-regulatory-access-grant"
        )

    def test_roster_teacher_denied_at_pdp_layer(self) -> None:
        with self.assertRaises(PermissionDenied):
            tenant_identity_roster(self._request(self.teacher, "/backend/identity/"))
        log = PolicyDecisionLog.objects.order_by("-created_at").first()
        self.assertEqual(log.effect, "implicit_deny")

    def test_tenant_deny_rule_binds_on_otherwise_allowed_admin(self) -> None:
        PolicyRule.objects.create(
            school=self.school,
            code="deny-this-admin-identity",
            name="tenant deny",
            effect=PolicyRule.Effect.DENY,
            subject_match={"user_id": self.admin.pk},
            action_match={"actions": ["manage"]},
            resource_match={"entity": "tenant_identity"},
            priority=10,
        )
        with self.assertRaises(PermissionDenied):
            tenant_identity_roster(self._request(self.admin, "/backend/identity/"))
        log = PolicyDecisionLog.objects.order_by("-created_at").first()
        self.assertEqual(log.effect, "deny")
        self.assertEqual(log.matched_rule.code, "deny-this-admin-identity")

    def test_kill_switch_fail_closes_surface(self) -> None:
        rule = self._baseline("iam-baseline-tenant-identity-manage")
        rule.is_active = False
        rule.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            tenant_identity_roster(self._request(self.admin, "/backend/identity/"))

    def test_superuser_god_mode_survives_kill_switch(self) -> None:
        PolicyRule.objects.filter(
            school__isnull=True, code__in=_BASELINE_CODES
        ).update(is_active=False)
        root = User.objects.create_user(
            username=f"pdproot-{uuid.uuid4().hex[:6]}",
            email="pdp-root@example.com",
            password="pass12345678",
            role=User.Role.ADMIN,
            is_superuser=True,
        )
        SchoolMembership.objects.create(
            user=root, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        response = tenant_identity_roster(self._request(root, "/backend/identity/"))
        self.assertEqual(response.status_code, 200)

    def test_probe_crash_fails_closed(self) -> None:
        with mock.patch(
            "apps.accounts.views_tenant_identity._can_manage_tenant_identity",
            side_effect=RuntimeError("gate down"),
        ):
            with self.assertRaises(PermissionDenied):
                tenant_identity_roster(self._request(self.admin, "/backend/identity/"))

    def test_decide_crash_fails_closed(self) -> None:
        with mock.patch(
            "apps.policies.enforcement.decide", side_effect=RuntimeError("pdp down")
        ):
            with self.assertRaises(PermissionDenied):
                tenant_identity_roster(self._request(self.admin, "/backend/identity/"))


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="enforce")
class RbacDashboardEnforcedTests(_IamSurfaceFixture):
    def _client_for(self, user) -> Client:
        client = Client()
        client.force_login(user)
        session = client.session
        session["school_id"] = str(self.school.id)
        session.save()
        return client

    def test_admin_allowed_via_baseline_rule(self) -> None:
        response = self._client_for(self.admin).get(reverse("accounts:rbac"))
        self.assertEqual(response.status_code, 200)
        log = PolicyDecisionLog.objects.order_by("-created_at").first()
        self.assertEqual(log.effect, "allow")
        self.assertEqual(log.matched_rule.code, "iam-baseline-access-role-manage")

    def test_anonymous_still_redirects_to_login(self) -> None:
        # Guard-placement proof: the PDP sits INSIDE @login_required, so an
        # anonymous user gets the login redirect, never a bare 403.
        response = Client().get(reverse("accounts:rbac"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_kill_switch_fail_closes_dashboard(self) -> None:
        rule = self._baseline("iam-baseline-access-role-manage")
        rule.is_active = False
        rule.save(update_fields=["is_active"])
        response = self._client_for(self.admin).get(reverse("accounts:rbac"))
        self.assertEqual(response.status_code, 403)


class RollbackModeTests(_IamSurfaceFixture):
    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="advisory")
    def test_advisory_mode_never_blocks_even_without_baseline_rules(self) -> None:
        PolicyRule.objects.filter(
            school__isnull=True, code__in=_BASELINE_CODES
        ).update(is_active=False)
        response = tenant_identity_roster(self._request(self.admin, "/backend/identity/"))
        self.assertEqual(response.status_code, 200)
        # The teacher still hits the view body's own gate (branded 403 path).
        response = tenant_identity_roster(
            self._request(self.teacher, "/backend/identity/")
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="off")
    def test_off_mode_writes_no_decision_log(self) -> None:
        before = PolicyDecisionLog.objects.count()
        response = tenant_identity_roster(self._request(self.admin, "/backend/identity/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PolicyDecisionLog.objects.count(), before)
