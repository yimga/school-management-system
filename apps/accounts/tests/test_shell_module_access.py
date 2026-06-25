"""Regression seal: shell modules must stay registered for tenant hosts.

Manager host (``public_host_kind == "manager"``) bypasses ModuleAccessMiddleware, so
missing entries here only surface on tenant subdomains — e.g. assist-dock presence
heartbeats and platform-runtime remote-support polls 403 with
``Module access check for unknown module … -> denied``.
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.accounts.middleware import ModuleAccessMiddleware
from apps.accounts.permissions import MODULE_ACCESS_DEFAULTS, can_access_module


def _noop_response(request):
    from django.http import HttpResponse

    return HttpResponse(status=200)


class ShellModuleAccessSeal(SimpleTestCase):
    def test_assist_dock_is_a_registered_module(self):
        self.assertIn(
            "assist_dock",
            MODULE_ACCESS_DEFAULTS,
            msg="assist_dock missing from MODULE_ACCESS_DEFAULTS → tenant "
            "assist-dock heartbeats 403 on every POST.",
        )

    def test_platform_runtime_is_a_registered_module(self):
        self.assertIn(
            "platform_runtime",
            MODULE_ACCESS_DEFAULTS,
            msg="platform_runtime missing from MODULE_ACCESS_DEFAULTS → tenant "
            "remote-support heartbeat/poll 403 on every POST.",
        )

    def test_authenticated_tenant_roles_can_write_shell_modules(self):
        user = mock.Mock(is_authenticated=True, is_superuser=False, is_staff=False)
        user.has_feature_permission = mock.Mock(return_value=False)
        for role in ("ADMIN", "TEACHER", "PARENT"):
            user.role = role
            self.assertTrue(
                can_access_module(user, "assist_dock", action="write"),
                msg=f"{role} blocked from assist_dock write",
            )
            self.assertTrue(
                can_access_module(user, "platform_runtime", action="write"),
                msg=f"{role} blocked from platform_runtime write",
            )


class ShellModuleAccessMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.middleware = ModuleAccessMiddleware(_noop_response)
        self.factory = RequestFactory()

    def test_assist_dock_heartbeat_not_denied_for_tenant_admin(self):
        user = mock.Mock(is_authenticated=True, is_superuser=False, is_staff=False)
        user.role = "ADMIN"
        user.has_feature_permission = mock.Mock(return_value=False)
        request = self.factory.post("/assist-dock/presence/heartbeat/")
        request.user = user
        request.public_host_kind = "tenant"
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_platform_runtime_remote_support_heartbeat_not_denied(self):
        user = mock.Mock(is_authenticated=True, is_superuser=False, is_staff=False)
        user.role = "ADMIN"
        user.has_feature_permission = mock.Mock(return_value=False)
        request = self.factory.post("/platform-runtime/remote-support/heartbeat/")
        request.user = user
        request.public_host_kind = "tenant"
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
