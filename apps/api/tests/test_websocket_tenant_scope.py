"""WebSocket tenant binding — host congruence + scoped group names."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, tag

from apps.schools.channels_tenant_middleware import (
    _bind_websocket_tenant_scope_sync,
    tenant_sync_room_name,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@tag("tenants_rls")
class WebSocketTenantScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name=f"WS A {uid}",
            slug=f"wsa-{uid}",
            subdomain=f"wsa{uid}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name=f"WS B {uid}",
            slug=f"wsb-{uid}",
            subdomain=f"wsb{uid}",
            is_active=True,
        )
        cls.user_a = User.objects.create_user(
            username=f"ws_user_a_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=cls.user_a,
            school=cls.school_a,
            role="ADMIN",
            is_primary=True,
        )

    def _run_bind(self, *, host: str, user, session_school_id: str | None = None):
        scope = {
            "type": "websocket",
            "user": user,
            "session": {"school_id": session_school_id} if session_school_id else {},
            "cookies": {},
            "headers": [(b"host", host.encode())],
            "path": "/ws/students/",
        }
        _bind_websocket_tenant_scope_sync(scope)
        return scope

    def test_matching_host_and_session_binds_school(self):
        host = f"{self.school_a.subdomain}.runmycampus.com"
        scope = self._run_bind(
            host=host,
            user=self.user_a,
            session_school_id=str(self.school_a.pk),
        )
        self.assertFalse(scope["school_access_denied"])
        self.assertEqual(scope["school_id"], str(self.school_a.pk))
        group = tenant_sync_room_name("students_sync", scope)
        self.assertEqual(group, f"students_sync_{self.school_a.pk}_{self.user_a.pk}")

    def test_session_school_mismatch_host_denies(self):
        host = f"{self.school_a.subdomain}.runmycampus.com"
        scope = self._run_bind(
            host=host,
            user=self.user_a,
            session_school_id=str(self.school_b.pk),
        )
        self.assertTrue(scope["school_access_denied"])
        self.assertIsNone(tenant_sync_room_name("students_sync", scope))

    def test_unauthenticated_scope_denied(self):
        from django.contrib.auth.models import AnonymousUser

        scope = self._run_bind(
            host=f"{self.school_a.subdomain}.runmycampus.com",
            user=AnonymousUser(),
        )
        self.assertTrue(scope["school_access_denied"])

    def test_asgi_stack_wires_tenant_middleware(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = root.joinpath("config", "asgi.py").read_text(encoding="utf-8")
        self.assertIn("TenantChannelsMiddleware", text)
        self.assertIn("AuthMiddlewareStack", text)

    def test_legacy_consumer_uses_tenant_scoped_prefix(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath("consumers.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("students_sync", source)
        self.assertIn("tenant_sync_room_name", source)
        self.assertNotIn('f"students_sync_{self.user.id}"', source)
