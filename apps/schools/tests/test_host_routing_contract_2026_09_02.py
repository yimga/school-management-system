"""The urlconf a request gets comes from its Host header, not from ROOT_URLCONF.

Every assertion here was read off a live request before it was written down. The
headline one is ``test_root_urlconf_override_does_not_survive_a_request``: a test that
sets ``ROOT_URLCONF="config.tenant_urls"`` and then issues a request without a host is
served by ``config.urls``, the developer urlconf, with **no school bound** -- and stays
green, because the developer urlconf mounts a superset of every production route. A
route deleted from ``config.tenant_urls`` therefore keeps passing such a test while
every real tenant 404s.

``apps/test_utils/tenant_hosts.py`` is the fix; ``scripts/scan_test_host_fidelity.py``
is the gate that stops the shape from coming back.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.test_utils.tenant_hosts import (
    BASE_DOMAIN,
    DEVELOPER_URLCONF,
    MANAGER_HOST,
    MANAGER_URLCONF,
    PUBLIC_HOST,
    PUBLIC_URLCONF,
    TENANT_URLCONF,
    TenantHostTestCase,
    assert_resolved_urlconf,
    make_school,
    resolved_urlconf,
    tenant_client,
    tenant_host,
)

_HOST_ROUTED = dict(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN=BASE_DOMAIN,
    SESSION_PINNING_ENABLED=False,
)


@override_settings(**_HOST_ROUTED)
class HostDecidesTheUrlconfTests(TestCase):
    """Pin the host -> urlconf mapping the middleware actually applies."""

    def setUp(self):
        self.school = make_school("routing")
        self.tenant_host = tenant_host(self.school)

    def _urlconf_for(self, host):
        response = self.client.get("/", HTTP_HOST=host)
        return resolved_urlconf(response), response

    def test_tenant_subdomain_gets_the_tenant_urlconf_and_binds_the_school(self):
        urlconf, response = self._urlconf_for(self.tenant_host)
        self.assertEqual(urlconf, TENANT_URLCONF)
        self.assertEqual(response.wsgi_request.school.pk, self.school.pk)
        self.assertTrue(response.wsgi_request.is_tenant_host)
        self.assertEqual(response.wsgi_request.public_host_kind, "tenant")

    def test_manager_host_gets_the_manager_urlconf(self):
        urlconf, response = self._urlconf_for(MANAGER_HOST)
        self.assertEqual(urlconf, MANAGER_URLCONF)
        self.assertEqual(response.wsgi_request.public_host_kind, "manager")

    def test_base_domain_gets_the_public_urlconf_and_binds_no_school(self):
        urlconf, response = self._urlconf_for(PUBLIC_HOST)
        self.assertEqual(urlconf, PUBLIC_URLCONF)
        self.assertIsNone(getattr(response.wsgi_request, "school", None))

    def test_testserver_gets_the_developer_urlconf_and_binds_no_school(self):
        """The default test host is a developer loopback, not any production surface."""
        urlconf, response = self._urlconf_for("testserver")
        self.assertEqual(urlconf, DEVELOPER_URLCONF)
        self.assertEqual(response.wsgi_request.public_host_kind, "local")
        self.assertIsNone(getattr(response.wsgi_request, "school", None))


@override_settings(ROOT_URLCONF=TENANT_URLCONF, **_HOST_ROUTED)
class RootUrlconfOverrideIsDiscardedTests(TestCase):
    """``ROOT_URLCONF`` loses to the Host header. This is the whole trap."""

    def test_root_urlconf_override_does_not_survive_a_request(self):
        # The class-level override claims the tenant urlconf...
        from django.conf import settings

        self.assertEqual(settings.ROOT_URLCONF, TENANT_URLCONF)

        # ...and the request is served by the developer urlconf regardless, because
        # UrlConfSwitcherMiddleware reassigns request.urlconf from the host.
        response = self.client.get("/")
        self.assertEqual(resolved_urlconf(response), DEVELOPER_URLCONF)
        self.assertIsNone(getattr(response.wsgi_request, "school", None))

    def test_the_same_override_is_honoured_once_a_real_host_is_supplied(self):
        """The override was never needed -- the host alone does the work."""
        school = make_school("override")
        response = self.client.get("/", HTTP_HOST=tenant_host(school))
        self.assertEqual(resolved_urlconf(response), TENANT_URLCONF)
        self.assertEqual(response.wsgi_request.school.pk, school.pk)


@override_settings(**_HOST_ROUTED)
class AssertResolvedUrlconfDetectsTheWrongSurfaceTests(TestCase):
    """A detector nobody has watched fail is not evidence. Watch it fail."""

    def test_it_rejects_a_request_served_by_the_developer_urlconf(self):
        response = self.client.get("/", HTTP_HOST="testserver")
        with self.assertRaises(AssertionError) as caught:
            assert_resolved_urlconf(response, TENANT_URLCONF)
        message = str(caught.exception)
        self.assertIn(DEVELOPER_URLCONF, message)
        self.assertIn(TENANT_URLCONF, message)

    def test_it_accepts_a_request_served_by_the_expected_urlconf(self):
        school = make_school("detector")
        response = self.client.get("/", HTTP_HOST=tenant_host(school))
        assert_resolved_urlconf(response, TENANT_URLCONF)  # must not raise

    def test_it_refuses_a_response_that_never_went_through_the_client(self):
        from django.http import HttpResponse

        with self.assertRaises(AssertionError):
            resolved_urlconf(HttpResponse("no request attached"))


class TenantHostTestCaseBindsTheTenantSurfaceTests(TenantHostTestCase):
    """The base class supplies a school, a host, and a client that uses it."""

    def test_setup_bound_a_school_and_a_tenant_host(self):
        self.assertTrue(self.tenant_host.endswith(f".{BASE_DOMAIN}"))
        self.assertEqual(self.tenant_host, f"{self.school.subdomain}.{BASE_DOMAIN}")

    def test_the_default_client_reaches_the_tenant_urlconf_without_extra_kwargs(self):
        """No HTTP_HOST= at the call site; the client already carries it."""
        response = self.client.get("/")
        self.assertTenantUrlconf(response)
        self.assertEqual(response.wsgi_request.school.pk, self.school.pk)


class TenantHostHelpersTests(TestCase):
    """Unit-level guards on the helpers themselves."""

    def test_tenant_host_accepts_a_school_or_a_bare_subdomain(self):
        school = make_school("helper")
        self.assertEqual(tenant_host(school), f"{school.subdomain}.{BASE_DOMAIN}")
        self.assertEqual(tenant_host("greenfield"), f"greenfield.{BASE_DOMAIN}")

    def test_tenant_host_refuses_a_blank_subdomain(self):
        """A blank subdomain is a real value on a unique index, not an absent one."""
        with self.assertRaises(ValueError):
            tenant_host("")
        with self.assertRaises(ValueError):
            tenant_host("   ")

    def test_make_school_gives_every_school_a_distinct_subdomain(self):
        first = make_school("distinct")
        second = make_school("distinct")
        self.assertNotEqual(first.subdomain, second.subdomain)
        self.assertTrue(first.subdomain and second.subdomain)

    def test_tenant_client_carries_the_host_on_every_request(self):
        school = make_school("carried")
        host = tenant_host(school)
        client = tenant_client(host)
        with override_settings(**_HOST_ROUTED):
            response = client.get("/")
        self.assertEqual(resolved_urlconf(response), TENANT_URLCONF)
