"""v3.40.0 Agent 1 — tests for the HashiCorp Vault Transit backend.

Coverage matrix:

  Dry-run mode (no live Vault)
  ----------------------------
  * sign() returns a 128-char base64 string
  * sign() is deterministic for a fixed pre-image
  * sign() varies when pre-image varies
  * verify() returns True for a matching signature
  * verify() returns False for a mismatched signature
  * key_version() returns 1 in dry-run

  Live-mode plumbing (via mocked urllib.request.urlopen)
  -----------------------------------------------------
  * sign() POSTs to /v1/transit/hmac/<key>
  * sign() strips the vault:vN: prefix from the response
  * verify() POSTs to /v1/transit/verify/<key>/sha2-512
  * key_version() reads data.latest_version from /v1/transit/keys/<key>
  * Missing VAULT_ADDR surfaces VaultBackendError, not Exception
  * Missing VAULT_TOKEN surfaces VaultBackendError, not Exception
  * Invalid VAULT_ADDR scheme surfaces VaultBackendError
  * HTTPError from urlopen surfaces VaultBackendError (typed)
  * URLError from urlopen surfaces VaultBackendError (typed)
  * Namespace header set when MIGRATION_CLOUD_VAULT_NAMESPACE configured

  Integration with audit_root_signing
  -----------------------------------
  * compute_root_signature dispatches to vault when backend selector set
  * verify_root_signature dispatches to vault when backend selector set
  * AWS/Azure/GCP backends still raise NotImplementedError

  Log hygiene
  -----------
  * Token never appears in any log output
  * Signature bytes never appear in any log output
  * Pre-image bytes never appear in any log output (only sha256 prefix)
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import unittest
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.migration_cloud.services.audit_root_signing import (
    SIGNING_BACKEND_VAULT,
    RESERVED_BACKENDS_HSM,
    IMPLEMENTED_HSM_BACKENDS,
    compute_root_signature,
    verify_root_signature,
)
from apps.migration_cloud.services.hsm_vault import (
    VaultBackendError,
    VaultTransitBackend,
)


# A pre-image we'll reuse across tests. Realistic but innocuous bytes.
_PRE_IMAGE = b'{"event_type":"companion.upload","id":"abc"}'
_TEST_TOKEN = "s.ThisIsAFakeVaultTokenDoNotLogMe"


class _FakeEvent:
    """Minimal duck-typed audit event (mirrors test_audit_root_signing_v3_39)."""

    def __init__(
        self,
        *,
        id_="00000000-0000-0000-0000-000000000001",
        tenant_id_hash="abc123def456",
        event_type="companion.upload",
        actor_id=None,
        event_subject_hash=None,
        payload_summary=None,
        created_at_iso="2026-05-19T10:00:00+00:00",
        prev_event_hash="genesis",
        root_key_signature=None,
    ):
        self.id = id_
        self.tenant_id_hash = tenant_id_hash
        self.event_type = event_type
        self.actor_id = actor_id
        self.event_subject_hash = event_subject_hash
        self.payload_summary = payload_summary or {}
        self.created_at_iso = created_at_iso
        self.prev_event_hash = prev_event_hash
        self.root_key_signature = root_key_signature


def _mock_http_response(body_dict, status=200):
    """Return a mock context-manager-able response for urlopen."""
    raw = json.dumps(body_dict).encode("utf-8")
    m = mock.MagicMock()
    m.__enter__ = mock.MagicMock(return_value=m)
    m.__exit__ = mock.MagicMock(return_value=False)
    m.read = mock.MagicMock(return_value=raw)
    m.status = status
    return m


# ─── 1. Dry-run mode ─────────────────────────────────────────────────────


@override_settings(DEBUG=True)
class VaultDryRunTests(SimpleTestCase):
    """Dry-run mode. Post-2026-07-24 audit (E-5) it fails CLOSED unless
    DEBUG is on, so a misconfigured prod Vault backend can never mint a
    forgeable hardcoded-seed signature — hence @override_settings(DEBUG=True)."""

    def setUp(self):
        # Force dry-run on regardless of host env.
        self._env_patcher = mock.patch.dict(
            os.environ,
            {"MIGRATION_CLOUD_VAULT_DRY_RUN": "1"},
            clear=False,
        )
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    def test_sign_returns_128_char_string(self):
        backend = VaultTransitBackend()
        sig = backend.sign(_PRE_IMAGE)
        self.assertIsInstance(sig, str)
        self.assertEqual(len(sig), 128)

    def test_sign_is_deterministic(self):
        backend = VaultTransitBackend()
        s1 = backend.sign(_PRE_IMAGE)
        s2 = backend.sign(_PRE_IMAGE)
        self.assertEqual(s1, s2)

    def test_sign_varies_when_pre_image_varies(self):
        backend = VaultTransitBackend()
        s1 = backend.sign(_PRE_IMAGE)
        s2 = backend.sign(_PRE_IMAGE + b"X")
        self.assertNotEqual(s1, s2)

    def test_verify_true_for_matching_signature(self):
        backend = VaultTransitBackend()
        sig = backend.sign(_PRE_IMAGE)
        self.assertTrue(backend.verify(_PRE_IMAGE, sig))

    def test_verify_false_for_mismatched_signature(self):
        backend = VaultTransitBackend()
        sig = backend.sign(_PRE_IMAGE)
        # Tamper one char
        tampered = ("0" if sig[0] != "0" else "1") + sig[1:]
        self.assertFalse(backend.verify(_PRE_IMAGE, tampered))

    def test_verify_false_for_empty_signature(self):
        backend = VaultTransitBackend()
        self.assertFalse(backend.verify(_PRE_IMAGE, ""))

    def test_key_version_returns_one_in_dry_run(self):
        backend = VaultTransitBackend()
        self.assertEqual(backend.key_version(), 1)


# ─── 2. Live-mode plumbing (urlopen mocked) ───────────────────────────────


class VaultLiveModeTests(SimpleTestCase):
    """Exercise the HTTP plumbing without a live Vault.

    We flip dry-run off and mock ``urllib.request.urlopen``.
    """

    def setUp(self):
        self._env_patcher = mock.patch.dict(
            os.environ,
            {
                "MIGRATION_CLOUD_VAULT_DRY_RUN": "0",
                "VAULT_ADDR": "https://vault.example.invalid:8200",
                "VAULT_TOKEN": _TEST_TOKEN,
                "MIGRATION_CLOUD_VAULT_TRANSIT_KEY_NAME": "migration-cloud-audit-root",
            },
            clear=False,
        )
        self._env_patcher.start()

    def tearDown(self):
        # Make sure no lingering namespace env carries between tests
        os.environ.pop("MIGRATION_CLOUD_VAULT_NAMESPACE", None)
        self._env_patcher.stop()

    def test_sign_posts_to_transit_hmac_endpoint(self):
        resp = _mock_http_response({
            "data": {"hmac": "vault:v3:" + base64.b64encode(b"X" * 64).decode("ascii")}
        })
        with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
            backend = VaultTransitBackend()
            sig = backend.sign(_PRE_IMAGE)
        # Inspect the request that was made
        args, _kwargs = urlopen.call_args
        req = args[0]
        self.assertIn("/v1/transit/hmac/migration-cloud-audit-root", req.full_url)
        self.assertEqual(req.get_method(), "POST")
        # The token must travel in the header
        self.assertEqual(req.headers.get("X-vault-token"), _TEST_TOKEN)
        # vault:v3: prefix must be stripped
        self.assertNotIn("vault:", sig)
        # Padded to 128 chars
        self.assertEqual(len(sig), 128)

    def test_sign_returns_bare_b64_when_response_has_no_prefix(self):
        # Vault always prefixes, but defensive: if it doesn't, we still
        # accept the raw string.
        raw_b64 = base64.b64encode(b"Y" * 64).decode("ascii")
        resp = _mock_http_response({"data": {"hmac": raw_b64}})
        with mock.patch("urllib.request.urlopen", return_value=resp):
            backend = VaultTransitBackend()
            sig = backend.sign(_PRE_IMAGE)
        self.assertEqual(len(sig), 128)

    def test_verify_posts_to_transit_verify_endpoint(self):
        # First call: key_version() (GET /v1/transit/keys/<key>)
        # Second call: verify (POST /v1/transit/verify/<key>/sha2-512)
        keys_resp = _mock_http_response({"data": {"latest_version": 5}})
        verify_resp = _mock_http_response({"data": {"valid": True}})
        with mock.patch(
            "urllib.request.urlopen", side_effect=[keys_resp, verify_resp]
        ) as urlopen:
            backend = VaultTransitBackend()
            result = backend.verify(_PRE_IMAGE, "AAAA" + ("=" * 124))
        self.assertTrue(result)
        # The verify URL must have been called
        verify_call = urlopen.call_args_list[-1]
        verify_req = verify_call.args[0]
        self.assertIn(
            "/v1/transit/verify/migration-cloud-audit-root/sha2-512",
            verify_req.full_url,
        )

    def test_verify_returns_false_when_vault_says_invalid(self):
        keys_resp = _mock_http_response({"data": {"latest_version": 1}})
        verify_resp = _mock_http_response({"data": {"valid": False}})
        with mock.patch(
            "urllib.request.urlopen", side_effect=[keys_resp, verify_resp]
        ):
            backend = VaultTransitBackend()
            result = backend.verify(_PRE_IMAGE, "AAAA" + ("=" * 124))
        self.assertFalse(result)

    def test_key_version_reads_latest_version(self):
        resp = _mock_http_response({"data": {"latest_version": 7}})
        with mock.patch("urllib.request.urlopen", return_value=resp):
            backend = VaultTransitBackend()
            self.assertEqual(backend.key_version(), 7)

    def test_namespace_header_set_when_configured(self):
        os.environ["MIGRATION_CLOUD_VAULT_NAMESPACE"] = "edu/runmycampus"
        try:
            resp = _mock_http_response({"data": {"hmac": "vault:v1:" + ("A" * 88)}})
            with mock.patch("urllib.request.urlopen", return_value=resp) as urlopen:
                backend = VaultTransitBackend()
                backend.sign(_PRE_IMAGE)
            req = urlopen.call_args.args[0]
            self.assertEqual(req.headers.get("X-vault-namespace"), "edu/runmycampus")
        finally:
            os.environ.pop("MIGRATION_CLOUD_VAULT_NAMESPACE", None)

    def test_missing_vault_addr_raises_typed_error(self):
        os.environ["VAULT_ADDR"] = ""
        backend = VaultTransitBackend()
        with self.assertRaises(VaultBackendError) as ctx:
            backend.sign(_PRE_IMAGE)
        self.assertIn("VAULT_ADDR", str(ctx.exception))

    def test_missing_vault_token_raises_typed_error(self):
        os.environ["VAULT_TOKEN"] = ""
        backend = VaultTransitBackend()
        with self.assertRaises(VaultBackendError) as ctx:
            backend.sign(_PRE_IMAGE)
        self.assertIn("VAULT_TOKEN", str(ctx.exception))

    def test_invalid_vault_addr_scheme_raises_typed_error(self):
        os.environ["VAULT_ADDR"] = "ftp://nope.invalid"
        backend = VaultTransitBackend()
        with self.assertRaises(VaultBackendError) as ctx:
            backend.sign(_PRE_IMAGE)
        self.assertIn("http", str(ctx.exception).lower())

    def test_http_error_surfaces_typed_vault_backend_error(self):
        import urllib.error

        def _raise(*_a, **_kw):
            raise urllib.error.HTTPError(
                "https://vault.example.invalid/v1/transit/hmac/x",
                500, "Internal Server Error", {}, io.BytesIO(b"oops"),
            )

        with mock.patch("urllib.request.urlopen", side_effect=_raise):
            backend = VaultTransitBackend()
            with self.assertRaises(VaultBackendError) as ctx:
                backend.sign(_PRE_IMAGE)
            self.assertIn("vault HTTP error", str(ctx.exception))

    def test_url_error_surfaces_typed_vault_backend_error(self):
        import urllib.error

        def _raise(*_a, **_kw):
            raise urllib.error.URLError("dns failure")

        with mock.patch("urllib.request.urlopen", side_effect=_raise):
            backend = VaultTransitBackend()
            with self.assertRaises(VaultBackendError):
                backend.sign(_PRE_IMAGE)

    def test_malformed_response_surfaces_typed_error(self):
        # Response missing data.hmac field
        resp = _mock_http_response({"data": {"unexpected": "shape"}})
        with mock.patch("urllib.request.urlopen", return_value=resp):
            backend = VaultTransitBackend()
            with self.assertRaises(VaultBackendError):
                backend.sign(_PRE_IMAGE)


# ─── 3. Integration with audit_root_signing.py ────────────────────────────


@override_settings(
    MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND=SIGNING_BACKEND_VAULT,
    DEBUG=True,  # dry-run now fails closed unless DEBUG (audit E-5)
)
class AuditRootSigningVaultDispatchTests(SimpleTestCase):
    """When the backend selector flips to hashicorp-vault, the service
    module must dispatch to the vault backend, NOT raise
    NotImplementedError.
    """

    def setUp(self):
        self._env_patcher = mock.patch.dict(
            os.environ,
            {"MIGRATION_CLOUD_VAULT_DRY_RUN": "1"},
            clear=False,
        )
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    def test_compute_root_signature_dispatches_to_vault(self):
        ev = _FakeEvent()
        sig = compute_root_signature(ev)
        self.assertIsNotNone(sig)
        self.assertEqual(len(sig), 128)

    def test_verify_root_signature_dispatches_to_vault(self):
        ev = _FakeEvent()
        ev.root_key_signature = compute_root_signature(ev)
        self.assertTrue(verify_root_signature(ev))

    def test_verify_root_signature_returns_false_on_tamper(self):
        ev = _FakeEvent()
        ev.root_key_signature = compute_root_signature(ev)
        # Tamper one char
        ev.root_key_signature = (
            ("0" if ev.root_key_signature[0] != "0" else "1")
            + ev.root_key_signature[1:]
        )
        self.assertFalse(verify_root_signature(ev))

    def test_verify_root_signature_none_when_no_stored_signature(self):
        ev = _FakeEvent(root_key_signature=None)
        self.assertIsNone(verify_root_signature(ev))


class AuditRootSigningOtherHSMBackendsTests(SimpleTestCase):
    """The other 3 cloud backends MUST still raise NotImplementedError."""

    def test_aws_kms_still_raises(self):
        with override_settings(MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND="aws-kms"):
            with self.assertRaises(NotImplementedError):
                compute_root_signature(_FakeEvent())

    def test_azure_keyvault_still_raises(self):
        with override_settings(MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND="azure-keyvault"):
            with self.assertRaises(NotImplementedError):
                compute_root_signature(_FakeEvent())

    def test_gcp_kms_still_raises(self):
        with override_settings(MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND="gcp-kms"):
            with self.assertRaises(NotImplementedError):
                compute_root_signature(_FakeEvent())

    def test_vault_is_in_implemented_set_not_reserved(self):
        self.assertIn(SIGNING_BACKEND_VAULT, IMPLEMENTED_HSM_BACKENDS)
        self.assertNotIn(SIGNING_BACKEND_VAULT, RESERVED_BACKENDS_HSM)


# ─── 4. Log hygiene ───────────────────────────────────────────────────────


class VaultLogHygieneTests(SimpleTestCase):
    """Confirm token / signature bytes / pre-image bytes never leak."""

    def setUp(self):
        self._env_patcher = mock.patch.dict(
            os.environ,
            {
                "MIGRATION_CLOUD_VAULT_DRY_RUN": "0",
                "VAULT_ADDR": "https://vault.example.invalid:8200",
                "VAULT_TOKEN": _TEST_TOKEN,
                "MIGRATION_CLOUD_VAULT_TRANSIT_KEY_NAME": "migration-cloud-audit-root",
            },
            clear=False,
        )
        self._env_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()

    def test_http_error_log_does_not_leak_token(self):
        import urllib.error

        def _raise(*_a, **_kw):
            raise urllib.error.HTTPError(
                "https://vault.example.invalid/v1/transit/hmac/x",
                500, "Internal Server Error", {}, io.BytesIO(b"oops"),
            )

        with mock.patch("urllib.request.urlopen", side_effect=_raise):
            with self.assertLogs(
                "apps.migration_cloud.services.hsm_vault", level="WARNING"
            ) as log_ctx:
                backend = VaultTransitBackend()
                with self.assertRaises(VaultBackendError):
                    backend.sign(_PRE_IMAGE)
        combined = "\n".join(log_ctx.output)
        self.assertNotIn(_TEST_TOKEN, combined)

    def test_sign_success_log_does_not_leak_token_or_signature(self):
        b64_payload = base64.b64encode(b"Z" * 64).decode("ascii")
        resp = _mock_http_response({
            "data": {"hmac": "vault:v1:" + b64_payload}
        })
        with mock.patch("urllib.request.urlopen", return_value=resp):
            with self.assertLogs(
                "apps.migration_cloud.services.hsm_vault", level="INFO"
            ) as log_ctx:
                backend = VaultTransitBackend()
                sig = backend.sign(_PRE_IMAGE)
        combined = "\n".join(log_ctx.output)
        # Token
        self.assertNotIn(_TEST_TOKEN, combined)
        # Signature bytes
        self.assertNotIn(b64_payload, combined)
        self.assertNotIn(sig, combined)
        # Pre-image bytes
        self.assertNotIn(_PRE_IMAGE.decode("utf-8"), combined)
        # SHA-256 prefix MAY appear (it's the diagnostic correlator).
        expected_prefix = hashlib.sha256(_PRE_IMAGE).hexdigest()[:12]
        self.assertIn(expected_prefix, combined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
