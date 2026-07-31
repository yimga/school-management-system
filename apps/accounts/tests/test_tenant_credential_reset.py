"""Tenant-admin credential recovery — reset another member's password / MFA.

Covers the capability gate (superuser / tenant-admin tier / assignable code),
the cross-tenant + owner-protection invariants, the temp-password + forced-change
action, the MFA-device reset, and the per-user MFA-setup deferral ("skip for a
period") including the strict-principal refusal.
"""

import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.middleware import RequireMFAMiddleware

from apps.accounts.credential_reset import (
    RESET_CREDENTIALS_CODE,
    admin_reset_mfa,
    admin_reset_password,
    can_reset_credentials,
    can_reset_target,
    generate_temp_password,
)
from apps.accounts.mfa_deferral import (
    MFA_SETUP_DEFERRAL_MAX_DAYS,
    clear_mfa_setup_deferral,
    defer_mfa_setup,
    mfa_setup_deferral_active,
    mfa_setup_deferral_days_remaining,
    normalize_deferral_days,
)
from apps.accounts.mfa_setup_flow import mfa_has_device
from apps.accounts.models import Permission, User
from apps.accounts.views_mfa import mfa_defer
from apps.accounts.views_tenant_identity import (
    tenant_identity_reset_mfa,
    tenant_identity_reset_password,
)
from apps.schools.models import School, SchoolMembership


def _mk_school(tag):
    return School.objects.create(
        name=f"School {tag}",
        slug=f"{tag}-{uuid.uuid4().hex[:8]}",
        subdomain=f"{tag}-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )


def _mk_user(role, password="pass12345678", active=True, usable=True):
    user = User.objects.create_user(
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.test",
        password=password if usable else None,
        role=role,
    )
    if not usable:
        user.set_unusable_password()
    if not active:
        user.is_active = False
    user.save()
    return user


def _member(user, school, *, owner=False, role=None):
    SchoolMembership.objects.create(
        user=user,
        school=school,
        role=role or user.role,
        is_primary=True,
        is_school_owner=owner,
    )


def _rf_request(user, school, *, method="post", data=None):
    rf = RequestFactory()
    req = getattr(rf, method)("/", data or {})
    req.user = user
    req.school = school
    req.session = SessionStore()
    req.session.create()
    req._messages = FallbackStorage(req)
    return req


class CredentialResetGateTests(TestCase):
    def setUp(self):
        self.school_a = _mk_school("a")
        self.school_b = _mk_school("b")
        self.owner = _mk_user(User.Role.ADMIN)
        _member(self.owner, self.school_a, owner=True)
        self.admin = _mk_user(User.Role.ADMIN)
        _member(self.admin, self.school_a)
        self.teacher = _mk_user(User.Role.TEACHER)
        _member(self.teacher, self.school_a)
        self.target = _mk_user(User.Role.TEACHER)
        _member(self.target, self.school_a)
        self.outsider = _mk_user(User.Role.TEACHER)
        _member(self.outsider, self.school_b)

    def test_permission_code_is_seeded(self):
        self.assertTrue(
            Permission.objects.filter(code=RESET_CREDENTIALS_CODE).exists(),
            "migration 0057 must seed the identity.reset_credentials permission",
        )

    def test_admin_tier_holds_capability_by_default(self):
        self.assertTrue(can_reset_credentials(self.admin, self.school_a))
        self.assertTrue(can_reset_credentials(self.owner, self.school_a))

    def test_plain_role_lacks_capability(self):
        self.assertFalse(can_reset_credentials(self.teacher, self.school_a))

    def test_capability_is_assignable_to_any_role(self):
        perm, _ = Permission.objects.get_or_create(
            code=RESET_CREDENTIALS_CODE, defaults={"name": "Reset credentials"}
        )
        self.teacher.feature_permissions.add(perm)
        self.assertTrue(can_reset_credentials(self.teacher, self.school_a))

    def test_cross_tenant_actor_is_denied(self):
        # An admin whose only membership is school_b cannot act on school_a.
        admin_b = _mk_user(User.Role.ADMIN)
        _member(admin_b, self.school_b)
        self.assertFalse(can_reset_credentials(admin_b, self.school_a))

    def test_cannot_reset_cross_tenant_member(self):
        self.assertFalse(can_reset_target(self.admin, self.outsider, self.school_a))

    def test_non_owner_cannot_reset_an_owner(self):
        self.assertFalse(can_reset_target(self.admin, self.owner, self.school_a))

    def test_owner_can_reset_an_admin(self):
        self.assertTrue(can_reset_target(self.owner, self.admin, self.school_a))

    def test_owner_can_reset_another_owner(self):
        owner2 = _mk_user(User.Role.ADMIN)
        _member(owner2, self.school_a, owner=True)
        self.assertTrue(can_reset_target(self.owner, owner2, self.school_a))

    def test_suspended_admin_loses_capability(self):
        m = SchoolMembership.objects.get(user=self.admin, school=self.school_a)
        m.suspended_at = timezone.now()
        m.save(update_fields=["suspended_at"])
        self.assertFalse(can_reset_credentials(self.admin, self.school_a))

    def test_tenant_admin_cannot_reset_platform_superuser(self):
        su = _mk_user(User.Role.ADMIN)
        su.is_superuser = True
        su.save(update_fields=["is_superuser"])
        _member(su, self.school_a)
        self.assertFalse(can_reset_target(self.admin, su, self.school_a))


class CredentialResetActionTests(TestCase):
    def setUp(self):
        self.school = _mk_school("act")
        self.owner = _mk_user(User.Role.ADMIN)
        _member(self.owner, self.school, owner=True)
        self.target = _mk_user(User.Role.TEACHER, password="oldpass12345")
        _member(self.target, self.school)

    def test_generate_temp_password_is_strong_and_unambiguous(self):
        pw = generate_temp_password()
        self.assertGreaterEqual(len(pw), 12)
        self.assertFalse(set("0O1lI") & set(pw))
        self.assertNotEqual(pw, generate_temp_password())

    def test_reset_password_sets_temp_and_forces_change(self):
        temp = admin_reset_password(self.owner, self.target, self.school)
        self.target.refresh_from_db()
        self.assertTrue(self.target.requires_password_change)
        self.assertTrue(self.target.check_password(temp))
        self.assertFalse(self.target.check_password("oldpass12345"))

    def test_reset_password_activates_never_claimed_account(self):
        pending = _mk_user(User.Role.TEACHER, active=False, usable=False)
        _member(pending, self.school)
        temp = admin_reset_password(self.owner, pending, self.school)
        pending.refresh_from_db()
        self.assertTrue(pending.is_active)
        self.assertTrue(pending.requires_password_change)
        self.assertTrue(pending.check_password(temp))

    def test_reset_password_reactivates_inactive_account(self):
        # An inactive account (even one with a REAL password) is reactivated by an
        # explicit admin reset — otherwise the temp password is dead on arrival,
        # since authenticate() rejects any inactive account (the novijonongni bug).
        # The reactivation is surfaced to the admin by the view, not silent.
        disabled = _mk_user(User.Role.TEACHER, password="realpass12345", active=False)
        _member(disabled, self.school)
        temp = admin_reset_password(self.owner, disabled, self.school)
        disabled.refresh_from_db()
        self.assertTrue(disabled.is_active)
        self.assertTrue(disabled.requires_password_change)
        # The freshly-issued temp password now actually works for authentication.
        self.assertTrue(disabled.check_password(temp))

    def test_reset_makes_inactive_account_authenticable(self):
        # End-to-end repro of the novijonongni bug: before the fix, authenticate()
        # returned None for the inactive account no matter the temp password, so the
        # login form showed the generic "invalid username or password". After the
        # reset reactivates it, authenticate() resolves the user.
        from django.contrib.auth import authenticate

        disabled = _mk_user(User.Role.TEACHER, password="realpass12345", active=False)
        _member(disabled, self.school)
        self.assertIsNone(
            authenticate(username=disabled.get_username(), password="realpass12345")
        )
        temp = admin_reset_password(self.owner, disabled, self.school)
        resolved = authenticate(username=disabled.get_username(), password=temp)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, disabled.pk)

    def test_set_temporary_password_reports_reactivation(self):
        # Shared core used by BOTH the tenant and operator resets. Returns
        # (temp_password, was_reactivated) and reactivates an inactive account.
        from apps.accounts.credential_reset import set_temporary_password

        active = _mk_user(User.Role.TEACHER, password="p12345678", active=True)
        temp, reactivated = set_temporary_password(active)
        self.assertFalse(reactivated)
        self.assertTrue(active.check_password(temp))
        self.assertTrue(active.requires_password_change)

        inactive = _mk_user(User.Role.TEACHER, password="p12345678", active=False)
        temp2, reactivated2 = set_temporary_password(inactive)
        self.assertTrue(reactivated2)
        self.assertTrue(inactive.is_active)
        self.assertTrue(inactive.check_password(temp2))

    def test_reset_mfa_clears_devices_and_deferral(self):
        TOTPDevice.objects.create(user=self.target, name="d", confirmed=True)
        defer_mfa_setup(self.target, days=7)
        self.assertTrue(mfa_has_device(self.target))
        admin_reset_mfa(self.owner, self.target, self.school)
        self.target.refresh_from_db()
        self.assertFalse(mfa_has_device(self.target))
        self.assertEqual(TOTPDevice.objects.filter(user=self.target).count(), 0)
        self.assertFalse(mfa_setup_deferral_active(self.target))

    def test_reset_mfa_is_idempotent_for_never_enrolled(self):
        # Never enrolled → no-op, no error ("reset everything so they can re-enrol").
        admin_reset_mfa(self.owner, self.target, self.school)
        self.assertFalse(mfa_has_device(self.target))


class CredentialResetViewTests(TestCase):
    def setUp(self):
        self.school = _mk_school("view")
        self.owner = _mk_user(User.Role.ADMIN)
        _member(self.owner, self.school, owner=True)
        self.teacher = _mk_user(User.Role.TEACHER)
        _member(self.teacher, self.school)
        self.target = _mk_user(User.Role.TEACHER, password="oldpass12345")
        _member(self.target, self.school)

    def test_reset_password_view_authorized(self):
        req = _rf_request(self.owner, self.school)
        resp = tenant_identity_reset_password(req, self.target.pk)
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.requires_password_change)

    def test_reset_password_view_forbidden_for_plain_teacher(self):
        req = _rf_request(self.teacher, self.school)
        resp = tenant_identity_reset_password(req, self.target.pk)
        self.assertEqual(resp.status_code, 403)
        self.target.refresh_from_db()
        self.assertFalse(self.target.requires_password_change)

    def test_reset_mfa_view_authorized(self):
        TOTPDevice.objects.create(user=self.target, name="d", confirmed=True)
        req = _rf_request(self.owner, self.school)
        resp = tenant_identity_reset_mfa(req, self.target.pk)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(mfa_has_device(self.target))

    def test_reset_mfa_view_forbidden_for_plain_teacher(self):
        TOTPDevice.objects.create(user=self.target, name="d", confirmed=True)
        req = _rf_request(self.teacher, self.school)
        resp = tenant_identity_reset_mfa(req, self.target.pk)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(mfa_has_device(self.target))


class MfaDeferralTests(TestCase):
    def setUp(self):
        self.school = _mk_school("defer")
        self.owner = _mk_user(User.Role.ADMIN)
        _member(self.owner, self.school, owner=True)
        self.teacher = _mk_user(User.Role.TEACHER)
        _member(self.teacher, self.school)

    def test_normalize_deferral_days_clamps(self):
        self.assertEqual(normalize_deferral_days("7"), 7)
        self.assertEqual(normalize_deferral_days(9999), MFA_SETUP_DEFERRAL_MAX_DAYS)
        self.assertEqual(normalize_deferral_days(0), 7)
        self.assertEqual(normalize_deferral_days("junk"), 7)
        self.assertEqual(normalize_deferral_days(-3), 7)

    def test_defer_and_clear(self):
        self.assertFalse(mfa_setup_deferral_active(self.teacher))
        defer_mfa_setup(self.teacher, days=14)
        self.teacher.refresh_from_db()
        self.assertTrue(mfa_setup_deferral_active(self.teacher))
        self.assertGreaterEqual(mfa_setup_deferral_days_remaining(self.teacher), 13)
        clear_mfa_setup_deferral(self.teacher)
        self.teacher.refresh_from_db()
        self.assertFalse(mfa_setup_deferral_active(self.teacher))

    def test_expired_deferral_is_inactive(self):
        self.teacher.mfa_setup_deferred_until = timezone.now() - timedelta(days=1)
        self.teacher.save(update_fields=["mfa_setup_deferred_until"])
        self.assertFalse(mfa_setup_deferral_active(self.teacher))

    def test_mfa_defer_view_sets_window_for_nonstrict_user(self):
        req = _rf_request(self.teacher, self.school, data={"days": "14"})
        resp = mfa_defer(req)
        self.assertEqual(resp.status_code, 302)
        self.teacher.refresh_from_db()
        self.assertTrue(mfa_setup_deferral_active(self.teacher))

    def test_mfa_defer_view_refused_for_owner(self):
        # An active school owner must always be strict — they can't skip MFA.
        req = _rf_request(self.owner, self.school, data={"days": "14"})
        resp = mfa_defer(req)
        self.assertEqual(resp.status_code, 302)  # redirected back to setup
        self.owner.refresh_from_db()
        self.assertFalse(mfa_setup_deferral_active(self.owner))


class MfaDeferralMiddlewareTests(TestCase):
    """End-to-end through RequireMFAMiddleware: an active deferral downgrades the
    strict wall to a pass-through for a softenable principal, but never for a
    strict one (superuser / platform admin / active owner)."""

    def setUp(self):
        self.factory = RequestFactory()

    def _run(self, user, *, mode="strict"):
        site = mock.Mock(
            require_mfa_all_staff=True,
            require_mfa_roles=[],
            mfa_enforcement_mode=mode,
            mfa_grace_period_days=7,
        )
        with mock.patch(
            "apps.accounts.middleware.get_effective_site_settings", return_value=site
        ):
            request = self.factory.get("/portal/")
            request.user = user
            request.session = {}
            return RequireMFAMiddleware(lambda r: HttpResponse("ok"))(request)

    def test_deferral_lets_softenable_user_through(self):
        user = _mk_user(User.Role.ADMIN)  # not owner, not superuser
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        defer_mfa_setup(user, days=7)
        resp = self._run(user)
        self.assertEqual(resp.status_code, 200)

    def test_no_deferral_still_hard_walls(self):
        user = _mk_user(User.Role.ADMIN)
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        resp = self._run(user)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/mfa/setup", resp.url)

    def test_strict_principal_cannot_defer_the_wall(self):
        user = _mk_user(User.Role.ADMIN)
        user.is_staff = True
        user.is_superuser = True  # always-strict principal
        user.save(update_fields=["is_staff", "is_superuser"])
        defer_mfa_setup(user, days=7)
        resp = self._run(user)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/mfa/setup", resp.url)
