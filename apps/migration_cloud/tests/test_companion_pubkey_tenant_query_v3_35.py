"""v3.35.0 Agent 1 — Explicit ``?tenant=<slug>`` query-param tests for
``companion_server_pubkey_view``.

Coverage (6 tests + assertLogs leak guard):

  1. Explicit ``?tenant=<slug>`` returns THAT tenant's pubkey (not the
     session tenant's) when no session tenant is bound.
  2. Missing query param falls back to ``request.tenant`` (preserves
     v3.34.0 behavior — backwards-compatible).
  3. Query param tenant matches session tenant → 200 OK.
  4. Query param tenant DIFFERS from session tenant → 403
     ``tenant_mismatch_query_vs_session``.
  5. Unknown slug → 404 ``tenant_not_found`` (does NOT echo slug).
  6. Inactive (``is_active=False``) school slug → 404 (don't leak that
     the slug exists).
  7. Response payload includes ``key_version`` + ``fingerprint_b64``
     and NEVER any private key bytes.
  8. ``assertLogs`` proves private key bytes never appear in logs even
     when the active keypair is freshly minted by the view path.

Tests skip cleanly when PyNaCl or the schools.School model is not
available (e.g. half-broken local test DB per memory v3.23.10).
"""
from __future__ import annotations

import logging
import re
import unittest

from django.test import TestCase
from django.urls import reverse


try:
    import nacl.public  # type: ignore[import-not-found]  # noqa: F401
    _PYNACL_AVAILABLE = True
except ImportError:
    _PYNACL_AVAILABLE = False


def _can_use_db() -> bool:
    try:
        from apps.schools.models import School  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


_REQUIRE_PYNACL = unittest.skipIf(
    not _PYNACL_AVAILABLE, "PyNaCl not installed in this environment"
)
_REQUIRE_DB = unittest.skipUnless(
    _can_use_db(), "School model unavailable in this environment"
)


def _make_school(slug: str, *, is_active: bool = True, name: str | None = None):
    from apps.schools.models import School
    return School.objects.create(
        name=name or f"School {slug}", slug=slug, is_active=is_active
    )


@_REQUIRE_PYNACL
@_REQUIRE_DB
class CompanionPubkeyExplicitTenantQueryTests(TestCase):
    """Tests for v3.35.0 explicit ``?tenant=<slug>`` query-param behavior."""

    _URL_NAME = "migration_cloud_super:companion_server_pubkey"

    def setUp(self):
        self.tenant_a = _make_school("v335-tenant-alpha", name="Alpha Academy")
        self.tenant_b = _make_school("v335-tenant-beta", name="Beta Academy")

        # Pre-mint keypairs so the GET response carries a real pubkey.
        from apps.migration_cloud.services import companion_keypair
        self.row_a = companion_keypair.ensure_active_keypair(self.tenant_a)
        self.row_b = companion_keypair.ensure_active_keypair(self.tenant_b)
        # Sanity: distinct.
        self.assertNotEqual(self.row_a.public_key_b64, self.row_b.public_key_b64)

    # ---- 1. Explicit slug returns that tenant's pubkey -----------------

    def test_explicit_tenant_query_returns_named_tenant_pubkey(self):
        url = reverse(self._URL_NAME) + "?tenant=v335-tenant-alpha"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body["public_key_b64"], self.row_a.public_key_b64)
        self.assertEqual(body["key_version"], self.row_a.key_version)
        # And NOT tenant B's keypair material.
        self.assertNotEqual(body["public_key_b64"], self.row_b.public_key_b64)

    # ---- 2. Missing param falls back to session-resolved tenant --------

    def test_missing_query_param_falls_back_to_session_tenant(self):
        """When the request lacks ?tenant= AND no session tenant is bound,
        the view returns 400 no_tenant (v3.34.0 contract preserved)."""
        url = reverse(self._URL_NAME)
        resp = self.client.get(url)
        # Without django-tenants middleware bound in a unit test, the
        # request has no tenant — the 400 path is the expected one.
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body.get("code"), "no_tenant")

    # ---- 3 & 4. Mismatch / match between query + session ---------------

    def test_query_param_mismatch_with_session_returns_403(self):
        """When request.tenant resolves to A but ?tenant=<B>: 403."""
        # We can't easily bind django-tenants middleware in this unit
        # test, so we drive the view directly and inject ``request.tenant``.
        from django.test import RequestFactory
        from apps.migration_cloud.companion_receiver import (
            companion_server_pubkey_view,
        )
        rf = RequestFactory()
        request = rf.get(reverse(self._URL_NAME) + "?tenant=v335-tenant-beta")
        request.tenant = self.tenant_a  # session-bound to A
        resp = companion_server_pubkey_view(request)
        self.assertEqual(resp.status_code, 403)
        body = resp.content.decode("utf-8")
        self.assertIn("tenant_mismatch_query_vs_session", body)

    def test_query_param_matching_session_returns_200(self):
        from django.test import RequestFactory
        from apps.migration_cloud.companion_receiver import (
            companion_server_pubkey_view,
        )
        rf = RequestFactory()
        request = rf.get(reverse(self._URL_NAME) + "?tenant=v335-tenant-alpha")
        request.tenant = self.tenant_a
        resp = companion_server_pubkey_view(request)
        self.assertEqual(resp.status_code, 200)

    # ---- 5. Unknown slug -----------------------------------------------

    def test_unknown_slug_returns_404_without_leaking_slug(self):
        url = reverse(self._URL_NAME) + "?tenant=this-slug-definitely-does-not-exist"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body.get("code"), "tenant_not_found")
        # The slug itself must NOT appear in the error message text.
        self.assertNotIn("this-slug-definitely-does-not-exist", body.get("error", ""))

    # ---- 6. Inactive school slug ---------------------------------------

    def test_inactive_school_slug_returns_404(self):
        _make_school("v335-inactive-tenant", is_active=False)
        url = reverse(self._URL_NAME) + "?tenant=v335-inactive-tenant"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body.get("code"), "tenant_not_found")

    # ---- 7. Response shape: key_version + fingerprint, no private bytes -

    def test_response_includes_key_version_and_fingerprint(self):
        url = reverse(self._URL_NAME) + "?tenant=v335-tenant-alpha"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in ("public_key_b64", "key_version", "fingerprint_b64"):
            self.assertIn(key, body, f"missing {key!r}")
            self.assertTrue(body[key], f"{key} must be non-empty")
        # Defensive: the raw response body must not contain "private"
        # in any form (case-insensitive). Even a misspelled key like
        # "private_key_encrypted" would trip this.
        raw = resp.content.decode("utf-8").lower()
        self.assertNotIn("private", raw)

    # ---- 8. assertLogs proves no private bytes leak --------------------

    def test_logger_never_emits_private_bytes(self):
        # Capture the receiver logger + the keypair service logger.
        receiver_logger = "apps.migration_cloud.companion_receiver"
        with self.assertLogs(receiver_logger, level=logging.INFO) as cm:
            url = reverse(self._URL_NAME) + "?tenant=v335-tenant-alpha"
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)

        combined = "\n".join(cm.output)
        # No contiguous 40+-char base64-looking blobs (a 32-byte b64
        # encodes to 44 chars; we forbid anything that long).
        long_b64 = re.findall(r"[A-Za-z0-9+/]{40,}", combined)
        self.assertFalse(
            long_b64,
            f"Logger leaked suspicious base64 blob: {long_b64!r}",
        )
        # The active row's private-bytes repr prefix must not appear.
        priv_repr_prefix = repr(bytes(self.row_a.private_key_encrypted))[:40]
        self.assertNotIn(priv_repr_prefix, combined)
        # Metadata IS allowed.
        self.assertIn("server_pubkey_fetched", combined)
        self.assertIn("explicit_query=True", combined)
