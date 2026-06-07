"""Invite-a-school flow: operator console + public accept + binding (2026-06-06).

Operator-console actions are tested at the view layer via RequestFactory so the
assertions target THIS view's logic, not the manager-host / MFA control-plane
middleware (exercised elsewhere). The public accept endpoint is tested through
the full Client since it carries no control-plane gating.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.schools.models import School, TenantInvite
from apps.schools.super_views_invite_school import InviteSchoolConsoleView


class InviteSchoolConsoleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.op = User.objects.create_user(
            username="op-inv@rmc.test", email="op-inv@rmc.test", password="pw-12345",
            is_staff=True, is_superuser=True,
        )
        self.rf = RequestFactory()

    def _req(self, data):
        req = self.rf.post("/super/invite-school/", data)
        req.user = self.op
        req.session = SessionStore()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def _get(self):
        req = self.rf.get("/super/invite-school/")
        req.user = self.op
        req.session = SessionStore()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def test_console_renders(self):
        with mock.patch("apps.schools.super_views_invite_school.render") as rnd:
            rnd.side_effect = lambda r, t, c: HttpResponse("ok")
            resp = InviteSchoolConsoleView.as_view()(self._get())
        self.assertEqual(resp.status_code, 200)

    def test_send_creates_pending_invite(self):
        with mock.patch(
            "apps.schools.super_views_invite_school.send_tenant_invite_email"
        ) as send:
            resp = InviteSchoolConsoleView.as_view()(
                self._req({"action": "send", "email": "head@demo.test",
                           "school_name": "Demo High", "country_code": "ke"})
            )
        self.assertEqual(resp.status_code, 302)
        inv = TenantInvite.objects.get(email="head@demo.test")
        self.assertEqual(inv.status, "pending")
        self.assertEqual(inv.school_name, "Demo High")
        self.assertEqual(inv.country_code, "KE")
        self.assertEqual(inv.invited_by, self.op)
        send.assert_called_once()

    def test_duplicate_send_does_not_create_second(self):
        with mock.patch("apps.schools.super_views_invite_school.send_tenant_invite_email"):
            InviteSchoolConsoleView.as_view()(self._req({"action": "send", "email": "dup@demo.test"}))
            InviteSchoolConsoleView.as_view()(self._req({"action": "send", "email": "dup@demo.test"}))
        self.assertEqual(TenantInvite.objects.filter(email="dup@demo.test").count(), 1)

    def test_revoke(self):
        inv = TenantInvite.objects.create(
            email="rev@demo.test", expires_at=timezone.now() + timedelta(days=7),
        )
        resp = InviteSchoolConsoleView.as_view()(
            self._req({"action": "revoke", "invite_id": str(inv.pk)})
        )
        self.assertEqual(resp.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "revoked")

    def test_resend_extends_and_unrevokes(self):
        inv = TenantInvite.objects.create(
            email="re@demo.test", expires_at=timezone.now() - timedelta(days=1),
            revoked_at=timezone.now(),
        )
        with mock.patch("apps.schools.super_views_invite_school.send_tenant_invite_email") as send:
            InviteSchoolConsoleView.as_view()(
                self._req({"action": "resend", "invite_id": str(inv.pk)})
            )
        inv.refresh_from_db()
        self.assertEqual(inv.status, "pending")
        self.assertGreater(inv.expires_at, timezone.now())
        send.assert_called_once()

    def test_send_rejects_bad_email(self):
        resp = InviteSchoolConsoleView.as_view()(self._req({"action": "send", "email": "nope"}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TenantInvite.objects.filter(email="nope").exists())


@override_settings(ALLOWED_HOSTS=["*"])
class AcceptInviteTests(TestCase):
    def test_valid_token_renders_and_stashes_session(self):
        inv = TenantInvite.objects.create(
            email="newhead@demo.test", school_name="New Academy",
            expires_at=timezone.now() + timedelta(days=7),
        )
        resp = self.client.get(f"/accept-invite/?token={inv.token}", HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "You're invited")
        self.assertEqual(self.client.session.get("tenant_invite_token"), str(inv.token))

    def test_bad_token_is_400(self):
        resp = self.client.get("/accept-invite/?token=not-a-uuid", HTTP_HOST="testserver")
        self.assertContains(resp, "Invitation not valid", status_code=400)

    def test_revoked_token_is_400(self):
        inv = TenantInvite.objects.create(
            email="x@demo.test", expires_at=timezone.now() + timedelta(days=7),
            revoked_at=timezone.now(),
        )
        resp = self.client.get(f"/accept-invite/?token={inv.token}", HTTP_HOST="testserver")
        self.assertEqual(resp.status_code, 400)

    def test_binding_marks_invite_accepted(self):
        from apps.schools.signup_views import _bind_tenant_invite_if_present

        inv = TenantInvite.objects.create(
            email="bind@demo.test", expires_at=timezone.now() + timedelta(days=7),
        )
        school = School.objects.create(
            name="Bound School", slug="bound-sch", subdomain="bound-sch",
            is_active=False, country_code="US", settings={},
        )
        rf = RequestFactory()
        req = rf.post("/signup/")
        req.session = SessionStore()
        req.session["tenant_invite_token"] = str(inv.token)
        _bind_tenant_invite_if_present(req, school)
        inv.refresh_from_db()
        self.assertEqual(inv.status, "accepted")
        self.assertEqual(inv.school_id, school.id)
        self.assertIsNone(req.session.get("tenant_invite_token"))
