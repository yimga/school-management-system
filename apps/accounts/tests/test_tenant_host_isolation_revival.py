"""Wave 2 (H2) — the operator->tenant isolation guards must actually run.

Both TenantHostControlPlaneIsolationMiddleware and ImpersonationReadOnlyGuardMiddleware
previously early-returned on ``public_host_kind == "tenant"`` — a value that host
resolution never produces — so they were dead code on every live tenant host. They now
key off the positive ``request.is_tenant_host`` marker. These tests are the regression
seal: with the marker set, the guards act; without it, they pass through; and normal
tenant users are never impacted.
"""
from unittest import mock

from django.http import HttpResponse, HttpResponseForbidden
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.middleware import (
    ImpersonationReadOnlyGuardMiddleware,
    TenantHostControlPlaneIsolationMiddleware,
    _impersonation_expired,
)


def _ok(request):
    return HttpResponse("OK")


class TenantHostControlPlaneIsolationRevivalTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.mw = TenantHostControlPlaneIsolationMiddleware(_ok)

    def _req(self, path="/portal/parent/", *, tenant_host=True, role="SUPERADMIN",
             is_superuser=False, imp=None):
        req = self.rf.get(path)
        req.is_tenant_host = tenant_host
        req.user = mock.Mock(is_authenticated=True, is_superuser=is_superuser, role=role)
        req.session = {"impersonation": imp} if imp is not None else {}
        req.school = mock.Mock(id=1)
        return req

    def test_superadmin_without_impersonation_redirected(self):
        # The core revival: a SUPERADMIN-role operator on a tenant host without a
        # matching impersonation session is bounced back to /super/.
        resp = self.mw(self._req())
        self.assertEqual(resp.status_code, 302)

    def test_superadmin_with_matching_impersonation_passes(self):
        resp = self.mw(self._req(imp={"school_id": "1"}))
        self.assertEqual(resp.content, b"OK")

    def test_normal_tenant_role_passes(self):
        # A normal tenant user is one WITH a SchoolMembership, so it is not a control-plane
        # operator and the guard passes it straight through. (The mock has no DB-backed
        # membership, and some envs list ADMIN in CONTROL_PLANE_OPERATOR_ROLES, so model the
        # real operator predicate directly rather than depend on env config.)
        with mock.patch(
            "apps.schools.control_plane.user_has_control_plane_access", return_value=False
        ):
            resp = self.mw(self._req(role="ADMIN"))
        self.assertEqual(resp.content, b"OK")

    def test_lower_tier_operator_without_impersonation_redirected(self):
        # A non-SUPERADMIN operator (support/observer PlatformOperatorProfile holder) must ALSO
        # be confined to the signed impersonation flow — it can no longer browse a tenant host
        # directly. user_has_control_plane_access is the operator predicate; True means operator.
        with mock.patch(
            "apps.schools.control_plane.user_has_control_plane_access", return_value=True
        ):
            resp = self.mw(self._req(role="SUPPORT"))
        self.assertEqual(resp.status_code, 302)

    def test_lower_tier_operator_with_matching_impersonation_passes(self):
        # ...but the SAME operator, inside a matching signed impersonation session, is allowed.
        with mock.patch(
            "apps.schools.control_plane.user_has_control_plane_access", return_value=True
        ):
            resp = self.mw(self._req(role="SUPPORT", imp={"school_id": "1"}))
        self.assertEqual(resp.content, b"OK")

    def test_superuser_break_glass_exempt(self):
        resp = self.mw(self._req(is_superuser=True))
        self.assertEqual(resp.content, b"OK")

    def test_non_tenant_host_skips_guard(self):
        resp = self.mw(self._req(tenant_host=False))
        self.assertEqual(resp.content, b"OK")

    # ── Wave 6 (H7): dedicated impersonation-session TTL ────────────────────────
    def test_superadmin_with_fresh_impersonation_passes(self):
        fresh = int(timezone.now().timestamp())
        resp = self.mw(self._req(imp={"school_id": "1", "granted_at": fresh}))
        self.assertEqual(resp.content, b"OK")

    def test_superadmin_with_expired_impersonation_redirected(self):
        old = int(timezone.now().timestamp()) - 10 * 3600
        resp = self.mw(self._req(imp={"school_id": "1", "granted_at": old}))
        self.assertEqual(resp.status_code, 302)

    # ── Wave 6 (H6): break-glass superuser tenant-host access is recorded ───────
    def test_break_glass_superuser_access_is_audited(self):
        from django.core.cache import cache

        cache.clear()
        with self.assertLogs("security.break_glass", level="WARNING") as cm:
            resp = self.mw(self._req(is_superuser=True))
        self.assertEqual(resp.content, b"OK")
        self.assertTrue(any("break-glass" in m for m in cm.output))


class ImpersonationTTLHelperTest(TestCase):
    def test_fresh_not_expired(self):
        self.assertFalse(
            _impersonation_expired({"granted_at": int(timezone.now().timestamp())})
        )

    def test_old_expired(self):
        self.assertTrue(
            _impersonation_expired(
                {"granted_at": int(timezone.now().timestamp()) - 99999}
            )
        )

    def test_legacy_marker_without_timestamp_not_expired(self):
        self.assertFalse(_impersonation_expired({"school_id": "1"}))


class ImpersonationReadOnlyGuardRevivalTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.mw = ImpersonationReadOnlyGuardMiddleware(_ok)

    def _post(self, path, *, tenant_host=True, imp=None):
        req = self.rf.post(path)
        req.is_tenant_host = tenant_host
        req.session = {"impersonation": imp} if imp is not None else {}
        req.school = mock.Mock(id=1)
        return req

    def test_write_blocked_during_readonly_impersonation(self):
        req = self._post("/finance/pay/", imp={"school_id": "1", "read_only": True})
        resp = self.mw.process_request(req)
        self.assertIsInstance(resp, HttpResponseForbidden)

    def test_write_allowed_without_impersonation(self):
        # Normal tenant user (no impersonation session) is never impacted.
        self.assertIsNone(self.mw.process_request(self._post("/finance/pay/")))

    def test_write_allowed_when_impersonation_not_readonly(self):
        req = self._post("/finance/pay/", imp={"school_id": "1", "read_only": False})
        self.assertIsNone(self.mw.process_request(req))

    def test_non_tenant_host_skips(self):
        req = self._post(
            "/finance/pay/", tenant_host=False, imp={"school_id": "1", "read_only": True}
        )
        self.assertIsNone(self.mw.process_request(req))
