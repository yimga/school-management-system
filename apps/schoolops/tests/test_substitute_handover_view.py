"""View tests for substitute_handover wiring (batch 1509).

Covers: anonymous redirect, role gate, GET form render, POST happy path,
hashed-id output (no raw teacher / substitute ID in response), medical/IEP
authorisation gate, malformed JSON rejection, end-before-start rejection.
"""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.schoolops.views_substitute_handover import substitute_handover_create
from apps.schools.models import School


User = get_user_model()


class SubstituteHandoverViewTests(TestCase):
    def setUp(self) -> None:
        set_urlconf("config.tenant_urls")
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Handover School",
            slug=f"hand-{uuid.uuid4().hex[:10]}",
            subdomain=f"hand-{uuid.uuid4().hex[:10]}",
            features={},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="adm@h.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username=f"t-{uuid.uuid4().hex[:8]}",
            email="t@h.test",
            password="x",
            role=User.Role.TEACHER,
        )

    def tearDown(self) -> None:
        set_urlconf(None)

    def _req(self, method, path, *, user, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = user
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_anonymous_redirects_to_login(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        req = self._req("GET", "/h/", user=AnonymousUser())
        resp = substitute_handover_create(req)
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_teacher_role_is_denied(self) -> None:
        req = self._req("GET", "/h/", user=self.teacher)
        resp = substitute_handover_create(req)
        self.assertIn(resp.status_code, (302, 403))

    def test_admin_get_renders_form(self) -> None:
        req = self._req("GET", "/h/", user=self.admin)
        resp = substitute_handover_create(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("teacher_id", body)
        self.assertIn("substitute_id", body)
        self.assertIn("Build packet", body)

    def test_admin_post_happy_path_renders_hashed_ids(self) -> None:
        req = self._req(
            "POST",
            "/h/",
            user=self.admin,
            data={
                "teacher_id": "raw-teacher-DISTINCT-XYZ",
                "substitute_id": "raw-substitute-DISTINCT-ZZZ",
                "absence_start": "2026-06-01T08:00",
                "absence_end": "2026-06-01T15:00",
                "reason_code": "sick",
                "grace_minutes": "30",
                "seating_chart_ref": "seating-123",
                "lesson_outline_json": json.dumps(
                    [{"period": 1, "topic": "Math", "materials": ["book"]}]
                ),
            },
        )
        resp = substitute_handover_create(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        # Raw IDs MUST NOT appear in the rendered response.
        self.assertNotIn("raw-teacher-DISTINCT-XYZ", body)
        self.assertNotIn("raw-substitute-DISTINCT-ZZZ", body)
        # Packet section should render (Generated packet header + hashed IDs).
        self.assertIn("Generated packet", body)

    def test_post_invalid_dates_renders_error(self) -> None:
        req = self._req(
            "POST",
            "/h/",
            user=self.admin,
            data={
                "teacher_id": "t",
                "substitute_id": "s",
                "absence_start": "2026-06-01T15:00",
                "absence_end": "2026-06-01T08:00",  # end before start
                "grace_minutes": "30",
            },
        )
        resp = substitute_handover_create(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertNotIn("Generated packet", body)

    def test_post_invalid_lesson_outline_json_renders_form_error(self) -> None:
        req = self._req(
            "POST",
            "/h/",
            user=self.admin,
            data={
                "teacher_id": "t",
                "substitute_id": "s",
                "absence_start": "2026-06-01T08:00",
                "absence_end": "2026-06-01T15:00",
                "grace_minutes": "30",
                "lesson_outline_json": "{ not valid json",
            },
        )
        resp = substitute_handover_create(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertNotIn("Generated packet", body)
        self.assertIn("lesson_outline_json", body)

    def test_audit_log_does_not_emit_raw_ids(self) -> None:
        req = self._req(
            "POST",
            "/h/",
            user=self.admin,
            data={
                "teacher_id": "raw-teacher-DISTINCT-FOR-LOGS",
                "substitute_id": "raw-substitute-DISTINCT-FOR-LOGS",
                "absence_start": "2026-06-01T08:00",
                "absence_end": "2026-06-01T15:00",
                "grace_minutes": "30",
            },
        )
        with self.assertLogs(
            "apps.schoolops.views_substitute_handover", level="INFO"
        ) as cm:
            substitute_handover_create(req)
        log_text = "\n".join(cm.output)
        self.assertNotIn("raw-teacher-DISTINCT-FOR-LOGS", log_text)
        self.assertNotIn("raw-substitute-DISTINCT-FOR-LOGS", log_text)

    def test_medical_iep_gate_admin_can_expose(self) -> None:
        req = self._req(
            "POST",
            "/h/",
            user=self.admin,
            data={
                "teacher_id": "t",
                "substitute_id": "s",
                "absence_start": "2026-06-01T08:00",
                "absence_end": "2026-06-01T15:00",
                "grace_minutes": "30",
                "expose_medical_iep": "on",
            },
        )
        resp = substitute_handover_create(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("Exposed by admin", body)

    def test_medical_iep_gate_default_stays_gated(self) -> None:
        req = self._req(
            "POST",
            "/h/",
            user=self.admin,
            data={
                "teacher_id": "t",
                "substitute_id": "s",
                "absence_start": "2026-06-01T08:00",
                "absence_end": "2026-06-01T15:00",
                "grace_minutes": "30",
                # expose_medical_iep deliberately omitted
            },
        )
        resp = substitute_handover_create(req)
        body = resp.content.decode("utf-8")
        self.assertIn("Gated (not exposed)", body)
