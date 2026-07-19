"""Operator "resend owner setup email" button: honest messaging + redirect.

Exercises the view function directly (the operator gate is applied at the URL
layer, like every other tenant-360 action). The dispatch itself is patched so the
tests pin the message branches — configured / not-configured / no-recipients /
school-not-found — and the redirect back to tenant-360, without sending real mail.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.super_views_owner_email import resend_owner_setup_email_view

_DISPATCH = "apps.schools.super_views_owner_email.dispatch_setup_email_for_school"


class ResendOwnerEmailViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        slug = f"gil-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Gilead", slug=slug, subdomain=slug, is_active=True
        )
        self.operator = User.objects.create_user(
            username="op", email="op@x.com", password="pass12345678",
            is_staff=True, is_superuser=True,
        )

    def _post(self, school_id):
        req = self.factory.post(f"/super/schools/{school_id}/resend-owner-setup-email/")
        req.user = self.operator
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def _messages(self, req):
        return [(m.level_tag, str(m)) for m in get_messages(req)]

    def test_get_is_not_allowed(self):
        req = self.factory.get(f"/super/schools/{self.school.pk}/resend-owner-setup-email/")
        req.user = self.operator
        resp = resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        self.assertEqual(resp.status_code, 405)

    def test_unknown_school_errors_to_dashboard(self):
        req = self._post(uuid.uuid4())
        resp = resend_owner_setup_email_view(req, school_id=str(uuid.uuid4()))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("super:dashboard"))
        self.assertTrue(any("error" in tag for tag, _m in self._messages(req)))

    def test_success_message_and_redirect(self):
        req = self._post(self.school.pk)
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 2, "sent": 2, "configured": True},
        ) as disp:
            resp = resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        disp.assert_called_once()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, reverse("super:tenant_360", args=[str(self.school.pk)])
        )
        msgs = self._messages(req)
        self.assertTrue(any("success" in tag for tag, _m in msgs))
        self.assertTrue(any("2 owner" in m for _t, m in msgs))

    def test_not_configured_warns_honestly(self):
        req = self._post(self.school.pk)
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 1, "sent": 0, "configured": False},
        ):
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        msgs = self._messages(req)
        self.assertTrue(any("warning" in tag for tag, _m in msgs))
        self.assertTrue(any("EMAIL_HOST_USER" in m for _t, m in msgs))

    def test_no_recipients_warns(self):
        req = self._post(self.school.pk)
        with mock.patch(
            _DISPATCH,
            return_value={"found": True, "recipients": 0, "sent": 0, "configured": True},
        ):
            resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        msgs = self._messages(req)
        self.assertTrue(any("warning" in tag for tag, _m in msgs))
        self.assertTrue(any("No active owner" in m for _t, m in msgs))

    def test_end_to_end_sends_to_active_owner(self):
        # No dispatch patch — exercise the real dispatch with the mail send mocked.
        owner = User.objects.create_user(
            username="own", email="owner@x.com", password="pass12345678",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=owner, school=self.school, role=User.Role.ADMIN,
            is_primary=True, is_school_owner=True, suspended_at=None,
        )
        req = self._post(self.school.pk)
        with mock.patch(
            "apps.schools.welcome_email.send_welcome_email", return_value=True
        ) as send:
            resp = resend_owner_setup_email_view(req, school_id=str(self.school.pk))
        send.assert_called_once_with(str(self.school.pk), "owner@x.com")
        self.assertEqual(resp.status_code, 302)
