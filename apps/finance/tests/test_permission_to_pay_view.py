"""View tests for permission_to_pay wiring (batch 1509).

Covers: role gate, GET form render, POST open happy path, session in-flight
state propagation, hashed IDs in rendered response, guardian-approval step,
authorize step happy path, audit logs free of raw IDs.
"""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.finance.views_permission_to_pay import (
    permission_to_pay_approve,
    permission_to_pay_authorize,
    permission_to_pay_open,
)
from apps.schools.models import School


User = get_user_model()


class PermissionToPayViewTests(TestCase):
    def setUp(self) -> None:
        # Tenant URL names live under config.tenant_urls; RequestFactory
        # bypasses host middleware so we set the urlconf for the test thread.
        set_urlconf("config.tenant_urls")
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="P2P School",
            slug=f"p2p-{uuid.uuid4().hex[:10]}",
            subdomain=f"p2p-{uuid.uuid4().hex[:10]}",
            features={},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="adm@p.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.parent = User.objects.create_user(
            username=f"par-{uuid.uuid4().hex[:8]}",
            email="par@p.test",
            password="x",
            role=User.Role.PARENT,
        )

    def tearDown(self) -> None:
        set_urlconf(None)

    def _req(self, method, path, *, user, data=None, session_carry=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = user
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        if session_carry:
            for k, v in session_carry.items():
                r.session[k] = v
            r.session.save()
        else:
            r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_parent_role_is_denied(self) -> None:
        req = self._req("GET", "/p/", user=self.parent)
        resp = permission_to_pay_open(req)
        self.assertIn(resp.status_code, (302, 403))

    def test_admin_get_renders_open_form(self) -> None:
        req = self._req("GET", "/p/", user=self.admin)
        resp = permission_to_pay_open(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Open request", body)
        self.assertIn("student_id", body)

    def test_open_post_stores_request_in_session_and_renders_hashed(self) -> None:
        req = self._req(
            "POST",
            "/p/",
            user=self.admin,
            data={
                "student_id": "raw-student-DISTINCT-PTPXYZ",
                "event_code": "lab_kit_2026",
                "amount": "25.00",
                "currency": "usd",
                "guardian_threshold": "50.00",
            },
        )
        resp = permission_to_pay_open(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertNotIn("raw-student-DISTINCT-PTPXYZ", body)
        self.assertIn("In-flight request", body)
        self.assertIn("lab_kit_2026", body)

    def test_open_above_threshold_requires_guardian_approval(self) -> None:
        req = self._req(
            "POST",
            "/p/",
            user=self.admin,
            data={
                "student_id": "s1",
                "event_code": "field_trip",
                "amount": "120.00",
                "currency": "USD",
                "guardian_threshold": "50.00",
            },
        )
        resp = permission_to_pay_open(req)
        body = resp.content.decode("utf-8")
        self.assertIn("Required, not yet recorded", body)

    def test_authorize_without_inflight_returns_400(self) -> None:
        req = self._req("POST", "/p/authorize/", user=self.admin)
        resp = permission_to_pay_authorize(req)
        self.assertEqual(resp.status_code, 400)

    def test_approve_without_inflight_returns_400(self) -> None:
        req = self._req(
            "POST",
            "/p/approve/",
            user=self.admin,
            data={"guardian_id": "g", "approved_at_iso": "2026-06-01T08:00:00Z", "method": "portal"},
        )
        resp = permission_to_pay_approve(req)
        self.assertEqual(resp.status_code, 400)

    def test_currency_is_normalised_to_iso_upper(self) -> None:
        req = self._req(
            "POST",
            "/p/",
            user=self.admin,
            data={
                "student_id": "s1",
                "event_code": "lab",
                "amount": "10.00",
                "currency": "eur",
                "guardian_threshold": "50.00",
            },
        )
        resp = permission_to_pay_open(req)
        body = resp.content.decode("utf-8")
        self.assertIn("EUR", body)

    def test_full_flow_open_approve_authorize_paid_state(self) -> None:
        # Step 1: open above-threshold request
        req1 = self._req(
            "POST",
            "/p/",
            user=self.admin,
            data={
                "student_id": "s1",
                "event_code": "trip",
                "amount": "75.00",
                "currency": "USD",
                "guardian_threshold": "50.00",
            },
        )
        resp1 = permission_to_pay_open(req1)
        self.assertEqual(resp1.status_code, 200)
        session_data = dict(req1.session.items())

        # Step 2: record guardian approval against the in-flight session.
        req2 = self._req(
            "POST",
            "/p/approve/",
            user=self.admin,
            data={
                "guardian_id": "guardian-distinct-G",
                "approved_at_iso": "2026-06-01T08:00:00Z",
                "method": "portal",
            },
            session_carry=session_data,
        )
        resp2 = permission_to_pay_approve(req2)
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.content.decode("utf-8")
        self.assertNotIn("guardian-distinct-G", body2)
        session_data = dict(req2.session.items())

        # Step 3: authorize payment.
        req3 = self._req(
            "POST",
            "/p/authorize/",
            user=self.admin,
            session_carry=session_data,
        )
        resp3 = permission_to_pay_authorize(req3)
        self.assertEqual(resp3.status_code, 200)
        body3 = resp3.content.decode("utf-8")
        self.assertIn("Paid", body3)

    def test_audit_log_omits_raw_student_id(self) -> None:
        req = self._req(
            "POST",
            "/p/",
            user=self.admin,
            data={
                "student_id": "raw-student-DISTINCT-LOGCHECK",
                "event_code": "lab",
                "amount": "10.00",
                "currency": "USD",
                "guardian_threshold": "50.00",
            },
        )
        with self.assertLogs(
            "apps.finance.permission_to_pay", level="INFO"
        ) as cm:
            permission_to_pay_open(req)
        log_text = "\n".join(cm.output)
        self.assertNotIn("raw-student-DISTINCT-LOGCHECK", log_text)
