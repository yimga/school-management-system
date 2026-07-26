"""Session-death re-auth must keep the user on their host, not eject to runmycampus.com.

The reported bug: when an OPERATOR (or a base-host-served) session expires and the
user reloads the page, instead of the host-local login form (with ``?next=`` back to
the page) they were bounced all the way out to ``runmycampus.com/discover/``.

Root cause: the manager-host login form was operator-only and only rendered when
``next`` deep-linked to ``/super/`` or ``/admin/`` — a session-death re-auth on any
OTHER operator surface (``/ops/``, ``/siteconfig/``, ``/configuration/`` …) fell
through to campus discovery; and the marketing apex dropped ``next`` entirely when it
handed ``/authentication/login/`` off to discovery.

These MUST-FIRE tests pin the fix:
* a safe, non-toxic, same-host ``next`` (the session-death signature) keeps the
  operator login surface on the manager host — with ``next`` preserved;
* a cold visit (no ``next``) still routes to campus discovery (unchanged);
* toxic tenant-flow ``next`` (MFA/onboarding/activation) still routes to discovery;
* the marketing apex forwards a ``/authentication/login/?next=<operator path>`` to the
  MANAGER host login (next intact) instead of dumping the operator on runmycampus.com.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.manager_login_next import (
    login_next_is_safe_same_host_return,
    manager_login_next_is_operator_intent,
    should_show_manager_login_surface,
)

User = get_user_model()


class SafeSameHostReturnHelperTests(TestCase):
    """``login_next_is_safe_same_host_return`` — the session-death discriminator."""

    def _req(self, query: str = "", *, method: str = "get", host: str = "manager.runmycampus.com"):
        rf = RequestFactory()
        path = "/authentication/login/" + (f"?{query}" if query else "")
        req = getattr(rf, method)(path, HTTP_HOST=host)
        req.user = AnonymousUser()
        return req

    def test_operator_ops_next_is_a_safe_return(self):
        self.assertTrue(login_next_is_safe_same_host_return(self._req("next=/ops/analytics/")))

    def test_siteconfig_next_is_a_safe_return(self):
        self.assertTrue(
            login_next_is_safe_same_host_return(self._req("next=/siteconfig/super/configure/"))
        )

    def test_super_next_is_a_safe_return(self):
        self.assertTrue(login_next_is_safe_same_host_return(self._req("next=/super/schools/")))

    def test_empty_next_is_not_a_return(self):
        # Cold visitor typing the URL — no next.
        self.assertFalse(login_next_is_safe_same_host_return(self._req()))

    def test_toxic_tenant_flow_next_is_not_a_return(self):
        self.assertFalse(
            login_next_is_safe_same_host_return(self._req("next=/authentication/mfa/setup/"))
        )
        self.assertFalse(
            login_next_is_safe_same_host_return(
                self._req("next=/authentication/onboarding/account/abc/")
            )
        )

    def test_offsite_next_is_rejected(self):
        # Open-redirect safety — an absolute off-site URL must never count.
        self.assertFalse(
            login_next_is_safe_same_host_return(self._req("next=https://evil.example.com/x"))
        )

    def test_protocol_relative_next_is_rejected(self):
        self.assertFalse(login_next_is_safe_same_host_return(self._req("next=//evil.example.com/x")))

    def test_post_next_is_honored(self):
        rf = RequestFactory()
        req = rf.post(
            "/authentication/login/",
            {"next": "/ops/analytics/"},
            HTTP_HOST="manager.runmycampus.com",
        )
        req.user = AnonymousUser()
        self.assertTrue(login_next_is_safe_same_host_return(req))


class ShouldShowManagerLoginSurfaceTests(TestCase):
    """Manager login surface must render for a session-death return on ANY operator surface."""

    def _req(self, query: str = ""):
        rf = RequestFactory()
        path = "/authentication/login/" + (f"?{query}" if query else "")
        req = rf.get(path, HTTP_HOST="manager.runmycampus.com")
        req.user = AnonymousUser()
        req.public_host_kind = "manager"
        return req

    def test_ops_next_now_shows_operator_login(self):
        # /ops/ is NOT operator-intent under the legacy /super/+/admin/ check ...
        self.assertFalse(manager_login_next_is_operator_intent("/ops/analytics/"))
        # ... but a safe same-host return path still keeps the operator login surface.
        self.assertTrue(should_show_manager_login_surface(self._req("next=/ops/analytics/")))

    def test_cold_visit_still_falls_through_to_discovery(self):
        # No next, no cp=1 → operator login NOT shown (caller ejects to discovery).
        self.assertFalse(should_show_manager_login_surface(self._req()))

    def test_toxic_next_does_not_show_operator_login(self):
        self.assertFalse(
            should_show_manager_login_surface(self._req("next=/authentication/mfa/setup/"))
        )


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.manager_urls",
    RMC_PUBLIC_SITE_URL="https://runmycampus.com",
)
class ManagerHostSessionDeathIntegrationTests(TestCase):
    def test_operator_ops_next_renders_login_not_discovery(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.get(reverse("accounts:login") + "?next=/ops/dashboard/")
        # 200 = operator login rendered (before the fix this 302'd to discovery).
        self.assertEqual(resp.status_code, 200)

    def test_cold_manager_login_still_ejects_to_discovery(self):
        client = Client(HTTP_HOST="manager.runmycampus.com")
        resp = client.get(reverse("accounts:login"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "https://runmycampus.com/discover/")


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ALLOWED_HOSTS=["runmycampus.com", "manager.runmycampus.com", "testserver"],
)
class ApexLoginForwardsOperatorNextToManagerHostTests(TestCase):
    """Marketing apex must forward an operator-surface session-death login to the
    manager host (next intact), not strand the operator at runmycampus.com/discover/."""

    def _mw(self):
        from apps.schools.middleware import ReservedPublicHostAccessMiddleware

        return ReservedPublicHostAccessMiddleware(lambda r: None)

    def _apex_req(self, full_path: str):
        req = RequestFactory().get(full_path, HTTP_HOST="runmycampus.com")
        req.user = AnonymousUser()
        req.session = {}
        return req

    def test_operator_next_forwards_to_manager_host_with_next(self):
        resp = self._mw().process_request(
            self._apex_req("/authentication/login/?next=/super/schools/")
        )
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("manager.runmycampus.com/authentication/login/", resp.url)
        self.assertIn("super", resp.url)  # next preserved

    def test_ops_next_also_forwards_to_manager_host(self):
        resp = self._mw().process_request(
            self._apex_req("/authentication/login/?next=/ops/analytics/")
        )
        self.assertIsNotNone(resp)
        self.assertIn("manager.runmycampus.com/authentication/login/", resp.url)

    def test_no_next_still_goes_to_discovery(self):
        resp = self._mw().process_request(self._apex_req("/authentication/login/"))
        self.assertIsNotNone(resp)
        self.assertNotIn("manager.", resp.url)  # bare discovery, not manager host

    def test_toxic_tenant_next_still_goes_to_discovery(self):
        resp = self._mw().process_request(
            self._apex_req("/authentication/login/?next=/authentication/mfa/setup/")
        )
        self.assertIsNotNone(resp)
        self.assertNotIn("manager.", resp.url)
