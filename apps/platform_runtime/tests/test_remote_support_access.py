"""Remote Support P0 — scope/tier wiring + operator and in-school access gates."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.platform_runtime import operator_identity as oi
from apps.platform_runtime import remote_support_access as rsa


class _U:
    def __init__(
        self, *, authed=True, superuser=False, staff=False, role=None, feat=None
    ):
        self.is_authenticated = authed
        self.is_superuser = superuser
        self.is_staff = staff
        self.role = role
        if feat is not None:
            self.has_feature_permission = feat


class _School:
    def __init__(self, settings=None):
        self.pk = 1
        self.id = 1
        self.settings = settings or {}


class TierScopeWiringTests(SimpleTestCase):
    def test_scope_registered_in_all_platform_scopes(self):
        self.assertIn(oi.PLATFORM_SCOPE_TENANT_SUPPORT, oi.ALL_PLATFORM_SCOPES)

    def test_tenant_support_tier_has_scope_without_impersonate(self):
        scopes = oi.TIER_SCOPES["tenant_support"]
        self.assertIn(oi.PLATFORM_SCOPE_TENANT_SUPPORT, scopes)
        self.assertNotIn(oi.PLATFORM_SCOPE_IMPERSONATE, scopes)

    def test_support_tier_has_both_support_and_impersonate(self):
        scopes = oi.TIER_SCOPES["support"]
        self.assertIn(oi.PLATFORM_SCOPE_TENANT_SUPPORT, scopes)
        self.assertIn(oi.PLATFORM_SCOPE_IMPERSONATE, scopes)

    def test_break_glass_inherits_new_scope(self):
        self.assertIn(
            oi.PLATFORM_SCOPE_TENANT_SUPPORT, oi.TIER_SCOPES["break_glass"]
        )

    def test_tier_choices_include_tenant_support(self):
        self.assertIn("tenant_support", [k for k, _ in oi.TIER_CHOICES])


class OperatorRemoteSupportGateTests(SimpleTestCase):
    def test_superuser_authorized_for_any_tenant(self):
        self.assertTrue(
            rsa.operator_is_authorized_for_tenant(_U(superuser=True), _School())
        )

    def test_denies_without_scope(self):
        with mock.patch.object(rsa, "user_has_platform_scope", return_value=False):
            self.assertFalse(rsa.operator_can_remote_support(_U(), _School()))

    def test_grants_with_scope_and_tenant_auth(self):
        with mock.patch.object(
            rsa, "user_has_platform_scope", return_value=True
        ), mock.patch.object(
            rsa, "operator_is_authorized_for_tenant", return_value=True
        ):
            self.assertTrue(rsa.operator_can_remote_support(_U(), _School()))

    def test_scope_but_not_authorized_for_tenant_denies(self):
        with mock.patch.object(
            rsa, "user_has_platform_scope", return_value=True
        ), mock.patch.object(
            rsa, "operator_is_authorized_for_tenant", return_value=False
        ):
            self.assertFalse(rsa.operator_can_remote_support(_U(), _School()))

    def test_unauthenticated_denied(self):
        self.assertFalse(rsa.operator_can_remote_support(_U(authed=False), _School()))

    def test_active_jit_grant_authorizes_for_tenant(self):
        school = _School(
            settings={
                "operator_access": {
                    "jit_grants": [
                        {
                            "operator_user_id": 5,
                            "expires_at_iso": "2999-01-01T00:00:00+00:00",
                            "reason": "ticket",
                        }
                    ]
                }
            }
        )
        u = _U()
        u.id = 5
        u.pk = 5
        with mock.patch(
            "apps.platform_runtime.models_operator_identity."
            "OperatorTenantAssignment.has_active",
            return_value=False,
        ):
            self.assertTrue(rsa.operator_is_authorized_for_tenant(u, school))


class InSchoolSupportGateTests(SimpleTestCase):
    def test_admin_role_can_support(self):
        role = get_user_model().Role.ADMIN
        self.assertTrue(
            rsa.user_can_provide_school_support(_U(role=role), _School())
        )

    def test_feature_permission_grants(self):
        feat = mock.Mock(return_value=True)
        u = _U(role="PARENT", feat=feat)
        self.assertTrue(rsa.user_can_provide_school_support(u, _School()))
        feat.assert_called_once()

    def test_plain_user_without_permission_denied(self):
        u = _U(role="PARENT", feat=mock.Mock(return_value=False))
        self.assertFalse(rsa.user_can_provide_school_support(u, _School()))

    def test_unauthenticated_denied(self):
        self.assertFalse(
            rsa.user_can_provide_school_support(_U(authed=False), _School())
        )
