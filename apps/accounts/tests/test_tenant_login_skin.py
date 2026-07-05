"""Wave B — the tenant-host login page never wears the operator skin.

A tenant subdomain must render the school-branded login (``auth/login.html``),
never the control-plane "Manager / Control plane sign-in" skin
(``auth/manager_login.html``). Before the fix, an authenticated visitor bounced to
``/authentication/login/`` on a tenant host got the operator skin because
``should_show_manager_login_surface`` returns True for any authenticated user.
"""

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.manager_login_next import use_operator_login_template


@override_settings(ALLOWED_HOSTS=["*"])
class TenantLoginSkinTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _req(
        self,
        *,
        host="owner-school.runmycampus.com",
        public_host_kind=None,
        is_tenant_host=False,
        authenticated=False,
        query="",
    ):
        path = "/authentication/login/" + (("?" + query) if query else "")
        req = self.factory.get(path, HTTP_HOST=host)
        req.public_host_kind = public_host_kind
        req.is_tenant_host = is_tenant_host
        req.user = SimpleNamespace(is_authenticated=authenticated)
        return req

    def test_tenant_host_authenticated_gets_tenant_skin(self):
        """The exact bug: authenticated user on a tenant host, tenant skin."""
        req = self._req(is_tenant_host=True, authenticated=True, query="next=/finance/")
        self.assertFalse(use_operator_login_template(req))

    def test_tenant_host_next_super_still_tenant_skin(self):
        req = self._req(is_tenant_host=True, query="next=/super/schools/")
        self.assertFalse(use_operator_login_template(req))

    def test_tenant_host_cp1_still_tenant_skin(self):
        req = self._req(is_tenant_host=True, query="cp=1")
        self.assertFalse(use_operator_login_template(req))

    def test_manager_host_gets_operator_skin(self):
        req = self._req(
            host="manager.runmycampus.com", public_host_kind="manager"
        )
        self.assertTrue(use_operator_login_template(req))

    def test_base_host_operator_intent_still_operator_skin(self):
        """Non-tenant base/public host keeps the existing operator-intent heuristic."""
        req = self._req(
            host="runmycampus.com", public_host_kind="base", query="next=/super/x/"
        )
        self.assertTrue(use_operator_login_template(req))

    def test_base_host_plain_gets_tenant_skin(self):
        req = self._req(host="runmycampus.com", public_host_kind="base")
        self.assertFalse(use_operator_login_template(req))
