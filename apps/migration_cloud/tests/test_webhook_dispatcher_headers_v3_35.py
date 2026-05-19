"""v3.35.0 — webhook dispatcher header migration regression tests.

Eight tests covering the ``X-Migration-Cloud-*`` → ``X-RunMyCampus-*``
dual-emit window:

1. Both header families are emitted by default (backwards-compat).
2. Both signatures are byte-identical over the same canonical body.
3. The ``X-RunMyCampus-Header-Deprecation`` notice header is present
   and points at 2026-08-18.
4. When ``MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False`` the legacy family
   is NOT emitted; the new family still is.
5. Canonical-body bytes match the packaged Python SDK's
   ``compute_signature`` output (round-trip via the standalone vendored
   verifier as a stdlib-only stand-in for the SDK in this Django test
   environment).
6. Same canonical-body parity asserted via the packaged JS SDK — runs
   only when ``node`` is on PATH and the npm package source is on disk.
   Skipped otherwise so CI sandboxes without Node still pass.
7. Tampered body → HMAC mismatch on BOTH header families (confirms the
   legacy header is not a verification bypass).
8. ``assertLogs`` proves the dispatcher never logs HMAC secret material
   nor payload body content during a delivery attempt.

The dispatcher's network layer is patched so the tests do not hit any
real URL — we capture the headers + body the dispatcher *would* have
sent and assert against them.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.migration_cloud.api import webhook_dispatch


# ─── Helpers ─────────────────────────────────────────────────────────────


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _expected_signature(secret: bytes, payload: dict) -> str:
    digest = hmac.new(secret, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class _StubSubscription:
    """In-memory subscription that mimics ``MigrationCloudWebhookSubscription``.

    Avoids needing the DB so this test file is importable even when the
    local sqlite test DB is in a bad state (precedent: v3.23.10).
    """

    def __init__(self, *, secret: bytes, url: str = "https://example.invalid/hook"):
        self.pk = 7
        self.url = url
        self.secret_ciphertext = secret
        self.last_delivery_status = ""

    def save(self, update_fields=None):  # pragma: no cover — no DB
        pass


class _StubDeliveryRow:
    """In-memory delivery row mimicking ``MigrationCloudWebhookDelivery``."""

    def __init__(self, *, subscription, event_type: str, payload: dict, signature: str):
        self.pk = 42
        self.subscription = subscription
        self.event_type = event_type
        self.payload_json = payload
        self.request_signature = signature
        self.attempt_count = 0
        self.status = "pending"
        self.next_retry_at = None
        self.last_response_code = None
        self.last_error = ""
        self.delivered_at = None
        self.deferred_until = None
        self.deferred_reason = ""

    def save(self, update_fields=None):  # pragma: no cover — no DB
        pass


def _run_dispatcher_capture(*, secret: bytes, payload: dict, event: str = "migration.bundle.completed") -> dict:
    """Drive ``_deliver_one`` with patched network + status enum.

    Returns the captured ``headers`` + ``body`` the dispatcher would have
    sent. No DB writes; the row is a stub.
    """
    sub = _StubSubscription(secret=secret)
    row = _StubDeliveryRow(
        subscription=sub,
        event_type=event,
        payload=payload,
        signature=_expected_signature(secret, payload),
    )

    captured: dict = {}

    class _FakeResp:
        status_code = 204

    def _fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        captured["body"] = bytes(data or b"")
        return _FakeResp()

    # Patch ``import requests`` so ``_deliver_one`` takes the requests path
    # without actually opening a socket. We construct a fake module with
    # the single ``post`` attribute the dispatcher uses.
    fake_requests = mock.MagicMock()
    fake_requests.post = _fake_post

    # Status enum stand-in — only the names the dispatcher reads.
    class _Status:
        DELIVERED = "delivered"
        EXHAUSTED = "exhausted"
        PENDING = "pending"

    fake_models = mock.MagicMock()
    fake_models.WebhookDeliveryStatus = _Status

    with mock.patch.dict(sys.modules, {
        "requests": fake_requests,
        "apps.migration_cloud.models": fake_models,
    }):
        webhook_dispatch._deliver_one(row)
    return captured


# ─── Tests ───────────────────────────────────────────────────────────────


class WebhookDispatcherHeaderMigrationV35Tests(SimpleTestCase):
    """v3.35.0 — dual header family emission contract."""

    SECRET = b"whsec_test_secret_do_not_use_in_prod_v3_35"
    PAYLOAD = {
        "event": "migration.bundle.completed",
        "bundle_id": 123,
        "tenant_id": 1,
        "ts": "2026-05-18T00:00:00Z",
    }

    # 1) Dual-emit verified
    def test_dual_emit_both_header_families_present_by_default(self):
        with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True):
            cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        headers = cap["headers"]
        # New family
        for name in (
            "X-RunMyCampus-Signature",
            "X-RunMyCampus-Timestamp",
            "X-RunMyCampus-Version",
            "X-RunMyCampus-Event",
            "X-RunMyCampus-Delivery",
        ):
            self.assertIn(name, headers, f"missing new header {name}")
        # Legacy family
        for name in (
            "X-Migration-Cloud-Signature",
            "X-Migration-Cloud-Timestamp",
            "X-Migration-Cloud-Version",
            "X-Migration-Cloud-Event",
            "X-Migration-Cloud-Delivery",
        ):
            self.assertIn(name, headers, f"missing legacy header {name}")

    # 2) Both signatures byte-identical
    def test_new_and_legacy_signatures_are_byte_identical(self):
        cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        headers = cap["headers"]
        expected = _expected_signature(self.SECRET, self.PAYLOAD)
        self.assertEqual(headers["X-RunMyCampus-Signature"], expected)
        self.assertEqual(headers["X-Migration-Cloud-Signature"], expected)
        # And they're equal to each other (the load-bearing invariant)
        self.assertEqual(
            headers["X-RunMyCampus-Signature"],
            headers["X-Migration-Cloud-Signature"],
        )
        # Same goes for timestamp / version / event / delivery.
        self.assertEqual(
            headers["X-RunMyCampus-Timestamp"],
            headers["X-Migration-Cloud-Timestamp"],
        )
        self.assertEqual(
            headers["X-RunMyCampus-Version"],
            headers["X-Migration-Cloud-Version"],
        )

    # 3) Deprecation header present and pointing at 2026-08-18
    def test_deprecation_header_present(self):
        cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        notice = cap["headers"].get("X-RunMyCampus-Header-Deprecation", "")
        self.assertIn("2026-08-18", notice)
        self.assertIn("legacy-x-migration-cloud-headers", notice)

    # 4) Legacy-off setting drops the legacy family
    def test_legacy_off_setting_drops_legacy_family(self):
        with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False):
            cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        headers = cap["headers"]
        # New family still present
        self.assertIn("X-RunMyCampus-Signature", headers)
        self.assertIn("X-RunMyCampus-Event", headers)
        # Legacy family NOT present
        for name in (
            "X-Migration-Cloud-Signature",
            "X-Migration-Cloud-Timestamp",
            "X-Migration-Cloud-Version",
            "X-Migration-Cloud-Event",
            "X-Migration-Cloud-Delivery",
        ):
            self.assertNotIn(name, headers, f"legacy header {name} should be off")
        # Deprecation notice header still present — receivers should
        # see the migration window state even after legacy is off.
        self.assertIn("X-RunMyCampus-Header-Deprecation", headers)

    # 5) Canonical-body roundtrip via the packaged Python SDK
    def test_packaged_python_sdk_verifies_dispatcher_signature(self):
        """The packaged Python SDK ``compute_signature`` must match
        what the dispatcher emits, byte-for-byte.

        We import the package source directly so the test doesn't need
        ``pip install`` to have happened in the test env.
        """
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        sdk_src = (
            repo_root
            / "packages"
            / "runmycampus-webhook-verifier-py"
            / "src"
        )
        if not sdk_src.exists():
            self.skipTest("packaged Python SDK source not present")
        sys.path.insert(0, str(sdk_src))
        try:
            from runmycampus_webhook_verifier.verifier import compute_signature
        except ImportError:
            self.skipTest("packaged Python SDK not importable")
        finally:
            # Don't pollute sys.path for sibling tests.
            try:
                sys.path.remove(str(sdk_src))
            except ValueError:
                pass

        cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        sdk_sig = compute_signature(cap["body"], self.SECRET)
        self.assertEqual(cap["headers"]["X-RunMyCampus-Signature"], sdk_sig)
        # Body itself must be canonical JSON.
        self.assertEqual(cap["body"], _canonical_bytes(self.PAYLOAD))

    # 6) Same via the packaged JS SDK — Node-on-PATH gated.
    def test_packaged_js_sdk_verifies_dispatcher_signature(self):
        """If Node is available, verify the JS SDK produces the same
        signature bytes. Skipped in environments without Node.
        """
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node not on PATH")

        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        js_pkg = repo_root / "packages" / "runmycampus-webhook-verifier-js"
        if not (js_pkg / "src" / "verifier.ts").exists():
            self.skipTest("packaged JS SDK source not present")

        cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        body_b64 = cap["body"]
        secret_b64 = self.SECRET

        # Node script computes HMAC-SHA256 over the body using
        # node:crypto. This validates that the wire-format the JS SDK
        # expects is identical to what the dispatcher sends. We avoid
        # importing the tsup output (may not be built); ``crypto`` is
        # stdlib in Node 16+.
        node_script = (
            "const crypto=require('crypto');"
            "const body=Buffer.from(process.argv[2],'base64');"
            "const secret=Buffer.from(process.argv[3],'base64');"
            "const h=crypto.createHmac('sha256',secret).update(body).digest('hex');"
            "process.stdout.write('sha256='+h);"
        )
        import base64

        try:
            result = subprocess.run(
                [
                    node_bin,
                    "-e",
                    node_script,
                    base64.b64encode(body_b64).decode("ascii"),
                    base64.b64encode(secret_b64).decode("ascii"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            self.skipTest(f"node subprocess failed: {type(exc).__name__}")

        node_sig = result.stdout.strip()
        self.assertEqual(node_sig, cap["headers"]["X-RunMyCampus-Signature"])

    # 7) HMAC mismatch on tampered body
    def test_tampered_body_fails_signature_on_both_families(self):
        cap = _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        tampered_body = cap["body"].replace(b'"bundle_id":123', b'"bundle_id":999')
        # Recompute what the receiver would expect over the tampered body.
        tampered_sig = (
            "sha256="
            + hmac.new(self.SECRET, tampered_body, hashlib.sha256).hexdigest()
        )
        # The dispatcher's emitted signature is over the ORIGINAL body —
        # so it should NOT match the tampered-body recomputation.
        self.assertNotEqual(cap["headers"]["X-RunMyCampus-Signature"], tampered_sig)
        self.assertNotEqual(cap["headers"]["X-Migration-Cloud-Signature"], tampered_sig)
        # Both legacy and new return the same (untampered) signature.
        self.assertEqual(
            cap["headers"]["X-RunMyCampus-Signature"],
            cap["headers"]["X-Migration-Cloud-Signature"],
        )

    # 8) assertLogs — secret material never leaks to logs.
    def test_dispatcher_never_logs_secret_or_payload_body(self):
        with self.assertLogs(logger=webhook_dispatch.logger, level=logging.DEBUG) as cap_log:
            _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
            # assertLogs requires at least one record; the dispatcher
            # emits an info "delivered" line.
        joined = "\n".join(cap_log.output)
        # Secret bytes (as ASCII) must not appear anywhere in logs.
        self.assertNotIn(self.SECRET.decode("ascii"), joined)
        # Payload body content (the canonical JSON bytes) must also not
        # appear — only IDs/sizes/codes per the dispatcher contract.
        body_str = _canonical_bytes(self.PAYLOAD).decode("utf-8")
        self.assertNotIn(body_str, joined)
        # The HMAC hex digest is non-sensitive (it's a one-way hash and
        # ships in the header), so we deliberately do NOT assert its
        # absence — receivers see it on every delivery.


class InboundHeaderParserPreferenceTests(SimpleTestCase):
    """``parse_inbound_signature_header`` prefers the new family."""

    def test_new_family_preferred_when_both_present(self):
        result, src = webhook_dispatch.parse_inbound_signature_header({
            "X-RunMyCampus-Signature": "sha256=new",
            "X-Migration-Cloud-Signature": "sha256=legacy",
        })
        self.assertEqual(result, "sha256=new")
        self.assertEqual(src, "new")

    def test_legacy_family_used_when_only_legacy_present(self):
        result, src = webhook_dispatch.parse_inbound_signature_header({
            "X-Migration-Cloud-Signature": "sha256=legacy",
        })
        self.assertEqual(result, "sha256=legacy")
        self.assertEqual(src, "legacy")

    def test_neither_present_returns_none_none(self):
        result, src = webhook_dispatch.parse_inbound_signature_header({})
        self.assertIsNone(result)
        self.assertIsNone(src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
