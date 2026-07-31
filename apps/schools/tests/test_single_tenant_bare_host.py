"""SINGLE_TENANT bare-hostname resolution (sovereign on-prem edge box).

A single-school mini-PC serves ONE school and should be reachable at a bare LAN
hostname / IP without per-school subdomain DNS. The helper ``_get_single_tenant_school``
existed but was never wired into ``_resolve_school_from_request``; these tests lock
the wiring AND its safety: the fallback fires ONLY when ``SINGLE_TENANT`` is on and
exactly one active school exists, so multi-tenant / cloud deployments are untouched.
"""
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.middleware import _resolve_school_from_request
from apps.schools.models import School

_BASE = "gilead.local"
_BARE_HOST = "mini-pc.lan"  # not a subdomain of _BASE, not localhost → unmatched


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN=_BASE)
class SingleTenantBareHostTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Gilead Tech High", slug="gilead-tech", subdomain="gilead", is_active=True
        )

    def _req(self, host):
        return self.rf.get("/", HTTP_HOST=host)

    @override_settings(SINGLE_TENANT=True)
    def test_bare_host_resolves_to_single_school(self):
        self.assertEqual(_resolve_school_from_request(self._req(_BARE_HOST)), self.school)

    @override_settings(SINGLE_TENANT=True)
    def test_base_domain_also_resolves_when_single_tenant(self):
        # On an edge box there is no public marketing surface, so even the base
        # domain resolves to the one school (in multi-tenant it stays public/None).
        self.assertEqual(_resolve_school_from_request(self._req(_BASE)), self.school)

    @override_settings(SINGLE_TENANT=False)
    def test_bare_host_does_not_resolve_when_flag_off(self):
        # Default (cloud/multi-tenant) behaviour is unchanged: an unmatched bare host
        # resolves to no tenant.
        self.assertIsNone(_resolve_school_from_request(self._req(_BARE_HOST)))

    @override_settings(SINGLE_TENANT=True)
    def test_two_active_schools_is_ambiguous_returns_none(self):
        # Safety: the fallback must never guess when more than one school exists.
        School.objects.create(name="Other", slug="other", subdomain="other", is_active=True)
        self.assertIsNone(_resolve_school_from_request(self._req(_BARE_HOST)))

    @override_settings(SINGLE_TENANT=True)
    def test_real_subdomain_still_resolves_normally(self):
        # A genuine subdomain match resolves via the normal path (the single-tenant
        # catch-all is only a last resort).
        self.assertEqual(
            _resolve_school_from_request(self._req(f"gilead.{_BASE}")), self.school
        )
