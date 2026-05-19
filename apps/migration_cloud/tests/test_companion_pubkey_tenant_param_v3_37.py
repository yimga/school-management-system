"""v3.37.0 Agent 1 — Tenant-slug switcher tests for ``companion_server_pubkey_view``.

Coverage (6+ tests + assertLogs leak guard):

  1. No ``?tenant=`` → legacy v3.34.0 behavior preserved (400 no_tenant
     when no session tenant is bound; behavior path is identical).
  2. Valid ``?tenant=<slug>`` returns THAT tenant's pubkey + slug echo.
  3. Unknown ``?tenant=<slug>`` returns 404 ``tenant_not_found`` without
     echoing the slug back in the error string.
  4. Cross-tenant leakage prevented: ``?tenant=B`` returns B's pubkey,
     never A's, even when both tenants have distinct active keypairs.
  5. Response shape includes the exact field contract the popup needs:
     ``tenant_slug``, ``key_version``, ``fingerprint_b64``,
     ``public_key_b64``, ``encryption_scheme``.
  6. ``assertLogs`` proves no private-key bytes ever appear in any log
     line emitted along the explicit-slug path.

Tests skip cleanly when PyNaCl or the ``schools.School`` model is not
available (mirrors v3.35.0 sibling test file convention).
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
class CompanionPubkeyTenantSwitcherTests(TestCase):
    """Tests for v3.37.0 multi-tenant switcher response contract."""

    _URL_NAME = "migration_cloud_super:companion_server_pubkey"

    def setUp(self):
        self.tenant_a = _make_school("v337-tenant-alpha", name="Alpha Academy")
        self.tenant_b = _make_school("v337-tenant-beta", name="Beta Academy")

        from apps.migration_cloud.services import companion_keypair
        self.row_a = companion_keypair.ensure_active_keypair(self.tenant_a)
        self.row_b = companion_keypair.ensure_active_keypair(self.tenant_b)
        # Sanity: distinct keys per tenant.
        self.assertNotEqual(self.row_a.public_key_b64, self.row_b.public_key_b64)

    # ---- 1. No tenant param: legacy 400 no_tenant -----------------------

    def test_no_tenant_query_preserves_legacy_behavior(self):
        """Absence of ?tenant= and no session tenant → 400 no_tenant.

        This is the v3.34.0 contract; v3.37.0 must not change it for
        single-tenant operators who never use the switcher.
        """
        url = reverse(self._URL_NAME)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body.get("code"), "no_tenant")
        # And critically: no ``tenant_slug`` is fabricated when nothing was passed.
        self.assertNotIn("tenant_slug", body)

    # ---- 2. Valid slug returns that tenant's pubkey + slug echo ---------

    def test_valid_tenant_slug_returns_pubkey_and_echoes_slug(self):
        url = reverse(self._URL_NAME) + "?tenant=v337-tenant-alpha"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("tenant_slug"), "v337-tenant-alpha")
        self.assertEqual(body["public_key_b64"], self.row_a.public_key_b64)
        self.assertEqual(body["key_version"], self.row_a.key_version)

    # ---- 3. Unknown slug → 404 without leaking the slug -----------------

    def test_unknown_tenant_slug_returns_404(self):
        url = reverse(self._URL_NAME) + "?tenant=v337-unknown-slug-xyz"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertEqual(body.get("code"), "tenant_not_found")
        # Slug must not appear in the error text (anti-leak).
        self.assertNotIn("v337-unknown-slug-xyz", body.get("error", ""))

    # ---- 4. Cross-tenant leakage prevented ------------------------------

    def test_cross_tenant_no_leakage_query_returns_named_tenant_only(self):
        """Asking for tenant B explicitly must NOT return tenant A's key,
        even when tenant A's keypair is older / "more active" / etc."""
        url = reverse(self._URL_NAME) + "?tenant=v337-tenant-beta"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["public_key_b64"], self.row_b.public_key_b64)
        self.assertEqual(body["tenant_slug"], "v337-tenant-beta")
        # Defense: tenant A's pubkey must NOT appear in this response.
        self.assertNotEqual(body["public_key_b64"], self.row_a.public_key_b64)

    # ---- 5. Response shape ----------------------------------------------

    def test_response_shape_includes_full_contract(self):
        url = reverse(self._URL_NAME) + "?tenant=v337-tenant-alpha"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in (
            "tenant_slug",
            "public_key_b64",
            "key_version",
            "fingerprint_b64",
            "encryption_scheme",
        ):
            self.assertIn(key, body, f"missing {key!r}")
            self.assertTrue(body[key], f"{key} must be non-empty")
        # And the response body must not contain the substring "private"
        # anywhere — even a misspelled "private_key_encrypted" trips this.
        raw = resp.content.decode("utf-8").lower()
        self.assertNotIn("private", raw)

    # ---- 6. assertLogs: no private bytes leak ---------------------------

    def test_logger_never_emits_private_bytes_on_slug_path(self):
        receiver_logger = "apps.migration_cloud.companion_receiver"
        with self.assertLogs(receiver_logger, level=logging.INFO) as cm:
            url = reverse(self._URL_NAME) + "?tenant=v337-tenant-alpha"
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)

        combined = "\n".join(cm.output)
        # No 40+-char base64-looking contiguous blobs (a 32-byte b64 is
        # 44 chars; we forbid anything that long in log output).
        long_b64 = re.findall(r"[A-Za-z0-9+/]{40,}", combined)
        self.assertFalse(
            long_b64,
            f"Logger leaked suspicious base64 blob: {long_b64!r}",
        )
        # The tenant's private-bytes repr prefix must not appear.
        priv_repr_prefix = repr(bytes(self.row_a.private_key_encrypted))[:40]
        self.assertNotIn(priv_repr_prefix, combined)
        # Metadata about the lookup IS expected.
        self.assertIn("server_pubkey_fetched", combined)
        self.assertIn("explicit_query=True", combined)
        self.assertIn("tenant_slug=v337-tenant-alpha", combined)

    # ---- 7. Inactive school slug → 404 ----------------------------------

    def test_inactive_school_slug_returns_404(self):
        _make_school("v337-inactive", is_active=False)
        url = reverse(self._URL_NAME) + "?tenant=v337-inactive"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json().get("code"), "tenant_not_found")

    # ---- 8. Empty ?tenant= falls through to legacy path -----------------

    def test_empty_tenant_param_falls_back_to_session(self):
        """`?tenant=` (empty value) must be treated the same as no param
        at all — never as "lookup slug ''" which would otherwise 404."""
        url = reverse(self._URL_NAME) + "?tenant="
        resp = self.client.get(url)
        # Session-less unit test → 400 no_tenant, not 404 tenant_not_found.
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("code"), "no_tenant")
