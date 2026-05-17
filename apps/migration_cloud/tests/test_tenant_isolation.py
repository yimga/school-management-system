"""Tenant-isolation gate for Migration Cloud bundle lookups (v3.17 hardening).

The audit identified a cross-tenant enumeration risk: bundle-detail views were
resolving bundles via plain ``get_object_or_404`` with no tenant scoping. A
portal user at School A could read School B's bundle by guessing its ID.

The fix wraps every bundle lookup in ``_tenant_scoped_bundle(request, id, shell)``
which:

  * in ``super`` shell (operator): returns the bundle without scoping (operators
    legitimately see all schools' bundles)
  * in ``portal`` shell (tenant): returns the bundle ONLY if its ``school_id``
    matches the caller's active tenant; mismatch raises ``Http404``, NEVER 403,
    so an attacker cannot distinguish "exists at another tenant" from "doesn't
    exist at all"

These tests use ``SimpleTestCase`` with mocks so they survive the sqlite
test-DB contention pattern we hit earlier.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from apps.migration_cloud import views as mc_views


class _FakeBundle:
    """Stand-in for MigrationBundle.objects.get-or-404 — has the ``school_id`` field
    the helper checks."""

    def __init__(self, pk: int = 42, school_id: int | None = 7):
        self.pk = pk
        self.school_id = school_id


class TenantScopedBundleResolverTests(SimpleTestCase):
    """``_tenant_scoped_bundle`` is the single security gate for bundle access."""

    def setUp(self):
        self.rf = RequestFactory()

    def _request_for_school(self, school_pk: int | None):
        req = self.rf.get("/x/")
        req.school = SimpleNamespace(pk=school_pk) if school_pk is not None else None
        return req

    def _patch_lookup(self, bundle: _FakeBundle | None):
        """Replace get_object_or_404 with a mock that returns the supplied bundle
        (or raises Http404 when bundle is None)."""
        if bundle is None:
            return mock.patch.object(
                mc_views,
                "get_object_or_404",
                side_effect=Http404("missing"),
            )
        return mock.patch.object(
            mc_views,
            "get_object_or_404",
            return_value=bundle,
        )

    def test_super_shell_returns_any_bundle(self):
        """Operator shell legitimately sees all bundles; no scoping applied."""
        bundle = _FakeBundle(pk=1, school_id=99)
        req = self._request_for_school(school_pk=1)  # operator's school != bundle's
        with self._patch_lookup(bundle):
            got = mc_views._tenant_scoped_bundle(req, bundle_id=1, shell="super")
        self.assertIs(got, bundle)

    def test_portal_same_tenant_returns_bundle(self):
        """Portal shell returns the bundle when the school matches."""
        bundle = _FakeBundle(pk=2, school_id=7)
        req = self._request_for_school(school_pk=7)
        with self._patch_lookup(bundle):
            got = mc_views._tenant_scoped_bundle(req, bundle_id=2, shell="portal")
        self.assertIs(got, bundle)

    def test_portal_cross_tenant_raises_404(self):
        """Portal shell at School A asking for School B's bundle → 404,
        NOT 403. We never reveal existence."""
        bundle = _FakeBundle(pk=3, school_id=99)
        req = self._request_for_school(school_pk=7)
        with self._patch_lookup(bundle):
            with self.assertRaises(Http404):
                mc_views._tenant_scoped_bundle(req, bundle_id=3, shell="portal")

    def test_portal_anonymous_request_raises_404(self):
        """Portal shell without a resolved tenant (no request.school) → 404.
        Should never silently grant access to bundles."""
        bundle = _FakeBundle(pk=4, school_id=7)
        req = self.rf.get("/x/")
        # No request.school assigned
        with self._patch_lookup(bundle):
            with self.assertRaises(Http404):
                mc_views._tenant_scoped_bundle(req, bundle_id=4, shell="portal")

    def test_portal_unbound_bundle_blocked_for_tenants(self):
        """Bundle with school_id=None (pre-tenant staging) is operator-only —
        portal users at any school must not see it."""
        bundle = _FakeBundle(pk=5, school_id=None)
        req = self._request_for_school(school_pk=7)
        with self._patch_lookup(bundle):
            with self.assertRaises(Http404):
                mc_views._tenant_scoped_bundle(req, bundle_id=5, shell="portal")

    def test_missing_bundle_propagates_404_unchanged(self):
        """If the bundle doesn't exist at all, the underlying Http404 from
        ``get_object_or_404`` propagates — and is indistinguishable from the
        cross-tenant 404 above. That's the whole point: an attacker probing
        for bundle IDs sees identical responses for ``missing`` vs ``elsewhere``."""
        req = self._request_for_school(school_pk=7)
        with self._patch_lookup(None):
            with self.assertRaises(Http404):
                mc_views._tenant_scoped_bundle(req, bundle_id=999, shell="portal")

    def test_request_tenant_attribute_fallback(self):
        """Some surfaces set ``request.tenant`` instead of ``request.school``.
        The helper accepts either — verifies the OR chain in the implementation."""
        bundle = _FakeBundle(pk=6, school_id=42)
        req = self.rf.get("/x/")
        req.school = None  # not set
        req.tenant = SimpleNamespace(pk=42)
        with self._patch_lookup(bundle):
            got = mc_views._tenant_scoped_bundle(req, bundle_id=6, shell="portal")
        self.assertIs(got, bundle)
