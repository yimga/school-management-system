"""Operator MFA-policy screen: operator-gated, writes the operator-exclusive key.

Verifies the screen enforces the platform floor (baseline roles locked + excluded
from stored data), stores only real role tokens, is reachable only by operators,
and that what it writes is exactly what resolve_operator_mfa reads back.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.mfa_defaults import resolve_operator_mfa
from apps.accounts.models import User
from apps.schools.models import School
from apps.schools.super_views_mfa_policy import tenant_mfa_policy


class SuperMfaPolicyViewTests(TestCase):
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
        self.tenant_user = User.objects.create_user(
            username="t", email="t@x.com", password="pass12345678",
        )

    def _req(self, *, method="get", user=None, data=None):
        path = f"/super/security/schools/{self.school.pk}/mfa-policy/"
        req = getattr(self.factory, method)(path, data or {})
        req.user = user
        req.public_host_kind = "manager"
        req.school = None
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def test_non_operator_is_forbidden(self):
        resp = tenant_mfa_policy(
            self._req(user=self.tenant_user), school_id=str(self.school.pk)
        )
        self.assertEqual(resp.status_code, 403)

    def test_operator_get_builds_context_with_locked_floor(self):
        captured = {}

        def fake_render(request, template, context):
            captured.update(context)
            return HttpResponse("ok")

        with mock.patch(
            "apps.schools.super_views_mfa_policy.render", side_effect=fake_render
        ):
            resp = tenant_mfa_policy(
                self._req(user=self.operator), school_id=str(self.school.pk)
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(captured["school"], self.school)
        # At least one role row is a locked floor role (e.g. ADMIN).
        self.assertTrue(any(r["locked"] for r in captured["role_rows"]))

    def test_operator_post_writes_policy_and_excludes_floor(self):
        resp = tenant_mfa_policy(
            self._req(
                method="post",
                user=self.operator,
                data={"require_all_staff": "1", "required_roles": ["TEACHER", "ADMIN"]},
            ),
            school_id=str(self.school.pk),
        )
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        stored = self.school.settings["operator_mfa"]
        self.assertTrue(stored["require_all_staff"])
        self.assertIn("TEACHER", stored["required_roles"])
        # ADMIN is a baseline floor role -> implicit, not stored here.
        self.assertNotIn("ADMIN", stored["required_roles"])

    def test_written_policy_is_read_back_by_resolver(self):
        tenant_mfa_policy(
            self._req(
                method="post",
                user=self.operator,
                data={"require_all_staff": "1", "required_roles": ["TEACHER"]},
            ),
            school_id=str(self.school.pk),
        )
        self.school.refresh_from_db()
        policy = resolve_operator_mfa(self.school)
        self.assertTrue(policy.require_all_staff)
        self.assertIn("TEACHER", policy.required_roles)

    def test_bogus_role_tokens_are_dropped(self):
        tenant_mfa_policy(
            self._req(
                method="post",
                user=self.operator,
                data={"required_roles": ["NOT_A_ROLE", "TEACHER"]},
            ),
            school_id=str(self.school.pk),
        )
        self.school.refresh_from_db()
        self.assertEqual(self.school.settings["operator_mfa"]["required_roles"], ["TEACHER"])
