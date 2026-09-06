"""Host-accurate test clients: drive a view through the urlconf a REAL host gets.

``ROOT_URLCONF`` is not what serves a request on this deployment.
``apps.schools.middleware.UrlConfSwitcherMiddleware`` reassigns ``request.urlconf``
from the ``Host`` header on every request, so an ``@override_settings(
ROOT_URLCONF="config.tenant_urls")`` on a test that then calls ``self.client.get(...)``
without a host is **silently discarded**: the default test host is ``testserver``,
``public_host_kind("testserver")`` is ``"local"``, and the middleware hands that
request ``config.urls`` -- the DEVELOPER urlconf, which no real host is ever served.

Measured, not assumed (``test_host_routing_contract_2026_09_02.py`` pins all of it):

    host                          request.urlconf      public_host_kind  request.school
    testserver                    config.urls          local             None
    <sub>.runmycampus.com         config.tenant_urls   tenant            <School>
    manager.runmycampus.com       config.manager_urls  manager           None
    runmycampus.com               config.public_urls   base              None

The developer urlconf is a SUPERSET, so a route deleted from ``config.tenant_urls``
still resolves under ``testserver`` and the test stays green while the tenant host
404s. That is the failure mode this module exists to make impossible; see
``scripts/scan_test_host_fidelity.py`` for the gate that keeps it from coming back.

Use ``TenantHostTestCase`` (or ``tenant_client``) instead of overriding
``ROOT_URLCONF``. The base class asserts in ``setUp`` that a probe request really
did resolve on ``config.tenant_urls``, so if host classification ever changes these
tests fail loudly rather than quietly reverting to the developer surface.
"""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, TransactionTestCase, override_settings

from apps.test_utils.seed_preserving import RestoresSeedCatalogMixin

BASE_DOMAIN = "runmycampus.com"
MANAGER_HOST = f"manager.{BASE_DOMAIN}"
PUBLIC_HOST = BASE_DOMAIN

TENANT_URLCONF = "config.tenant_urls"
MANAGER_URLCONF = "config.manager_urls"
PUBLIC_URLCONF = "config.public_urls"
DEVELOPER_URLCONF = "config.urls"

#: Settings a host-accurate test needs.
#:
#: There is deliberately **no** ``ROOT_URLCONF`` key. Setting it would be worse than
#: useless here: the middleware overrides it per request, so it cannot help, and its
#: presence is exactly what convinces a reader the test is on the tenant surface when
#: it is not. ``ALLOWED_HOSTS`` must admit the generated host, and
#: ``MULTI_TENANT_BASE_DOMAIN`` is what ``get_canonical_base_domain()`` reads to decide
#: that ``<sub>.runmycampus.com`` is a tenant rather than an unknown host.
HOST_ROUTED_SETTINGS = dict(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN=BASE_DOMAIN,
    SESSION_PINNING_ENABLED=False,
)

host_routed = override_settings(**HOST_ROUTED_SETTINGS)


def tenant_host(school_or_subdomain) -> str:
    """Return the canonical tenant host for a ``School`` (or a bare subdomain)."""
    subdomain = getattr(school_or_subdomain, "subdomain", school_or_subdomain)
    subdomain = (subdomain or "").strip().lower()
    if not subdomain:
        raise ValueError(
            "a tenant host needs a non-empty subdomain; School.subdomain is blank. "
            "A blank subdomain also collides on the unique index the moment a second "
            "school is created -- always set one explicitly in tests."
        )
    return f"{subdomain}.{BASE_DOMAIN}"


def tenant_client(host: str, **extra) -> Client:
    """A ``Client`` whose every request carries a tenant ``Host`` header."""
    return Client(HTTP_HOST=host, raise_request_exception=False, **extra)


def public_client(**extra) -> Client:
    """A ``Client`` on the base domain, which the middleware routes to public_urls.

    This is the surface a prospective school meets: signup, verification, the
    marketing pages. It binds no school, by design.
    """
    return Client(HTTP_HOST=PUBLIC_HOST, raise_request_exception=False, **extra)


def manager_client(**extra) -> Client:
    """A ``Client`` on the control-plane host, routed to manager_urls.

    Unauthenticated. For an MFA-satisfied operator session use
    ``apps.test_utils.http_clients.login_manager_client``, which also binds the
    separate manager session cookie.
    """
    return Client(HTTP_HOST=MANAGER_HOST, raise_request_exception=False, **extra)


def resolved_urlconf(response) -> str:
    """The urlconf that actually served ``response``.

    Reads ``request.urlconf`` off the real request the client built, which is what
    Django's resolver consults -- not ``settings.ROOT_URLCONF``, which the middleware
    has already overridden by the time any view runs.
    """
    request = getattr(response, "wsgi_request", None)
    if request is None:
        raise AssertionError(
            "response carries no wsgi_request; pass a response from the Django test "
            "client, not a bare HttpResponse."
        )
    return getattr(request, "urlconf", None) or DEVELOPER_URLCONF


def assert_resolved_urlconf(response, expected: str) -> None:
    """Fail unless ``response`` was served by ``expected``.

    Call this in any test that means to exercise a production host surface. Without
    it, a request that quietly fell back to the developer urlconf still passes,
    because the developer urlconf mounts a superset of every host's routes.
    """
    actual = resolved_urlconf(response)
    if actual != expected:
        host = response.wsgi_request.get_host()
        raise AssertionError(
            f"request to {host!r} resolved on {actual!r}, expected {expected!r}. "
            f"The urlconf comes from the Host header via UrlConfSwitcherMiddleware; "
            f"overriding ROOT_URLCONF does not change it."
        )


def make_school(subdomain_prefix: str = "harness", **fields):
    """Create an active ``School`` with a unique subdomain and matching slug.

    ``School.subdomain`` is unique, and a blank one is a value like any other, so the
    second ``School.objects.create()`` without an explicit subdomain fails on the
    unique index rather than on anything to do with the test. The suffix makes each
    call safe under ``TransactionTestCase``, which does not roll back between tests.
    """
    from apps.schools.models import School

    suffix = uuid.uuid4().hex[:8]
    name = f"{subdomain_prefix}-{suffix}"
    fields.setdefault("name", f"Harness School {suffix}")
    fields.setdefault("is_active", True)
    return School.objects.create(slug=name, subdomain=name, **fields)


class _TenantHostMixin:
    """Bind ``self.school``, ``self.tenant_host`` and a host-accurate ``self.client``.

    ``setUp`` ends by proving the binding actually happened. That probe is the point
    of the class: every other guarantee here is a convention a future edit can break
    silently, and this one cannot be broken silently.
    """

    tenant_subdomain_prefix = "harness"

    def setUp(self):
        super().setUp()
        self.school = make_school(self.tenant_subdomain_prefix)
        self.tenant_host = tenant_host(self.school)
        self.client = tenant_client(self.tenant_host)
        self.assert_tenant_routing()

    def assert_tenant_routing(self):
        """Prove a request on this host reaches the tenant urlconf with a school bound."""
        response = self.client.get("/", HTTP_HOST=self.tenant_host)
        assert_resolved_urlconf(response, TENANT_URLCONF)
        bound = getattr(response.wsgi_request, "school", None)
        if getattr(bound, "pk", None) != self.school.pk:
            raise AssertionError(
                f"host {self.tenant_host!r} resolved on {TENANT_URLCONF} but bound "
                f"school {bound!r}, expected {self.school!r}. TenantMiddleware "
                f"resolves the school from the host; check School.subdomain and "
                f"is_active."
            )

    def assertTenantUrlconf(self, response):
        """Assert ``response`` was served by ``config.tenant_urls``."""
        assert_resolved_urlconf(response, TENANT_URLCONF)


@host_routed
class TenantHostTestCase(_TenantHostMixin, TestCase):
    """``TestCase`` whose client speaks to a real tenant host."""


@host_routed
class TenantHostTransactionTestCase(
    RestoresSeedCatalogMixin, _TenantHostMixin, TransactionTestCase
):
    """``TransactionTestCase`` variant.

    Prefer ``TenantHostTestCase``: a real transaction is only worth its cost when
    the test needs one (threads, a live server, DDL).

    A ``TransactionTestCase`` truncates every table on teardown and does not roll
    it back, which used to mean 'order these last' -- advice that pytest cannot
    honour, since it runs in collection order. ``RestoresSeedCatalogMixin`` removes
    the need for the ordering entirely by restoring the post-migration snapshot
    after the flush; see ``apps/test_utils/seed_preserving.py``.
    """
