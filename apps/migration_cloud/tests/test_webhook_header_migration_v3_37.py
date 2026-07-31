"""v3.37.0 — webhook header dual-emit regression tests (Agent-2 fan-out).

Six tests asserting the v3.35 dual-emit policy survives across the
v3.37 fan-out closeout work. Sister test file
``test_webhook_dispatcher_headers_v3_35.py`` already covers
canonical-body parity + SDK round-trip; this file adds the
load-bearing invariants the v3.37 brief requires:

  (a) ``MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True`` emits BOTH families
      with byte-identical signature bytes.
  (b) ``MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False`` emits ONLY the new
      family.
  (c) Header VALUES are byte-identical across families (signature,
      timestamp, event, delivery-id, version).
  (d) No plaintext payload body appears in any log line (``assertLogs``)
      — defense against leaking customer data into operator logs.
  (e) The HMAC compute call is invoked EXACTLY ONCE per delivery (the
      same signature bytes power both header families — no double sign).
  (f) Timestamp + delivery-id are consistent (same value) across both
      header families on the same delivery.

The network layer is patched; no real URL is hit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sys
import unittest
from datetime import date
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
    """In-memory subscription mimicking ``MigrationCloudWebhookSubscription``."""

    def __init__(self, *, secret: bytes, url: str = "https://example.invalid/hook"):
        self.pk = 37
        self.url = url
        self.secret_ciphertext = secret
        self.last_delivery_status = ""

    def save(self, update_fields=None):  # pragma: no cover — no DB
        pass


class _StubDeliveryRow:
    """In-memory delivery row mimicking ``MigrationCloudWebhookDelivery``."""

    def __init__(self, *, subscription, event_type: str, payload: dict, signature: str):
        self.pk = 137
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


def _run_dispatcher_capture(
    *, secret: bytes, payload: dict,
    event: str = "migration.bundle.completed",
):
    """Drive ``_deliver_one`` with patched network. Returns captured req."""
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

    fake_requests = mock.MagicMock()
    fake_requests.post = _fake_post

    class _Status:
        DELIVERED = "delivered"
        EXHAUSTED = "exhausted"
        PENDING = "pending"

    fake_models = mock.MagicMock()
    fake_models.WebhookDeliveryStatus = _Status

    # Allow the delivery-time SSRF guard to pass for the hermetic test URL
    # (example.invalid fails DNS and would be blocked before header capture);
    # the SSRF guard is exercised by its own tests.
    with mock.patch.dict(sys.modules, {
        "requests": fake_requests,
        "apps.migration_cloud.models": fake_models,
    }), mock.patch(
        "apps.security.ssrf.is_safe_public_url", return_value=(True, "")
    ):
        webhook_dispatch._deliver_one(row)
    return captured, row


# ─── Tests ───────────────────────────────────────────────────────────────


class WebhookHeaderMigrationV37Tests(SimpleTestCase):
    """v3.37.0 — Agent-2 dual-emit regression suite."""

    SECRET = b"whsec_v3_37_agent2_test_secret_NEVER_USE_IN_PROD"
    PAYLOAD = {
        "event": "migration.bundle.completed",
        "bundle_id": 1337,
        "tenant_id": 42,
        "ts": "2026-05-19T00:00:00Z",
    }

    # (a) Flag True → both families emitted with identical signature bytes.
    def test_flag_true_emits_both_families_with_identical_signatures(self) -> None:
        with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True):
            cap, _row = _run_dispatcher_capture(
                secret=self.SECRET, payload=self.PAYLOAD,
            )
        headers = cap["headers"]
        expected = _expected_signature(self.SECRET, self.PAYLOAD)
        self.assertIn("X-RunMyCampus-Signature", headers)
        self.assertIn("X-Migration-Cloud-Signature", headers)
        # Constant-time compare per project rules — even though both
        # values live in our test process, we still use compare_digest
        # to model the verifier contract.
        self.assertTrue(
            hmac.compare_digest(
                headers["X-RunMyCampus-Signature"].encode("ascii"),
                expected.encode("ascii"),
            )
        )
        self.assertTrue(
            hmac.compare_digest(
                headers["X-Migration-Cloud-Signature"].encode("ascii"),
                headers["X-RunMyCampus-Signature"].encode("ascii"),
            )
        )

    # (b) Flag False → ONLY new family emitted; no legacy header leaks through.
    def test_flag_false_emits_only_new_family(self) -> None:
        with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False):
            cap, _row = _run_dispatcher_capture(
                secret=self.SECRET, payload=self.PAYLOAD,
            )
        headers = cap["headers"]
        self.assertIn("X-RunMyCampus-Signature", headers)
        for legacy_name in (
            "X-Migration-Cloud-Signature",
            "X-Migration-Cloud-Timestamp",
            "X-Migration-Cloud-Version",
            "X-Migration-Cloud-Event",
            "X-Migration-Cloud-Delivery",
        ):
            self.assertNotIn(
                legacy_name, headers,
                f"legacy header {legacy_name} must NOT be emitted when "
                "MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=False",
            )

    # (c) All five paired header VALUES are byte-identical across families.
    def test_header_values_byte_identical_across_families(self) -> None:
        with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True):
            cap, _row = _run_dispatcher_capture(
                secret=self.SECRET, payload=self.PAYLOAD,
            )
        h = cap["headers"]
        pairs = [
            ("X-RunMyCampus-Signature", "X-Migration-Cloud-Signature"),
            ("X-RunMyCampus-Timestamp", "X-Migration-Cloud-Timestamp"),
            ("X-RunMyCampus-Version",   "X-Migration-Cloud-Version"),
            ("X-RunMyCampus-Event",     "X-Migration-Cloud-Event"),
            ("X-RunMyCampus-Delivery",  "X-Migration-Cloud-Delivery"),
        ]
        for new_name, legacy_name in pairs:
            self.assertEqual(
                h[new_name], h[legacy_name],
                f"value drift between {new_name} and {legacy_name}",
            )

    # (d) Dispatcher must NEVER log the canonical payload body bytes.
    def test_no_plaintext_payload_body_in_any_log_line(self) -> None:
        with self.assertLogs(
            logger=webhook_dispatch.logger, level=logging.DEBUG,
        ) as cap_log:
            _run_dispatcher_capture(secret=self.SECRET, payload=self.PAYLOAD)
        joined = "\n".join(cap_log.output)
        body_str = _canonical_bytes(self.PAYLOAD).decode("utf-8")
        self.assertNotIn(body_str, joined)
        # Bundle_id is a payload-internal value; spot-check it never lands
        # in the log either (defense against ad-hoc f-string leaks).
        self.assertNotIn('"bundle_id":1337', joined)
        # Secret bytes also off-limits.
        self.assertNotIn(self.SECRET.decode("ascii"), joined)

    # (e) HMAC compute is invoked EXACTLY ONCE per delivery, not twice.
    def test_hmac_computed_exactly_once_per_delivery(self) -> None:
        """Both header families MUST share the same signature bytes — the
        dispatcher pre-computes the digest once at ``enqueue`` time and
        only stamps it into the header dict on each attempt.

        We assert this by mocking :func:`webhook_dispatch._sign` and
        confirming it is NOT called during ``_deliver_one`` (the call
        happens at enqueue, which the test stubs around). The stub
        ``_StubDeliveryRow.request_signature`` already holds the expected
        value, so a re-sign during dispatch would be a regression.
        """
        with mock.patch.object(
            webhook_dispatch, "_sign", wraps=webhook_dispatch._sign,
        ) as sign_spy:
            with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True):
                _run_dispatcher_capture(
                    secret=self.SECRET, payload=self.PAYLOAD,
                )
        # ``_deliver_one`` reads ``row.request_signature``; it MUST NOT
        # re-invoke ``_sign``. Two header families share one digest.
        self.assertEqual(
            sign_spy.call_count, 0,
            "dispatcher must NOT recompute HMAC during _deliver_one; "
            "both header families must reuse the precomputed signature "
            f"(saw {sign_spy.call_count} calls)",
        )

    # (f) Timestamp + delivery-id are identical across both families on the
    #     same delivery row.
    def test_timestamp_and_delivery_id_consistent_across_families(self) -> None:
        with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True):
            cap, row = _run_dispatcher_capture(
                secret=self.SECRET, payload=self.PAYLOAD,
            )
        h = cap["headers"]
        # Timestamp parity.
        self.assertEqual(h["X-RunMyCampus-Timestamp"], h["X-Migration-Cloud-Timestamp"])
        # Timestamp is unix-seconds — should parse as int.
        self.assertTrue(h["X-RunMyCampus-Timestamp"].isdigit())
        # Delivery-id parity AND value matches row.pk (str cast).
        self.assertEqual(h["X-RunMyCampus-Delivery"], h["X-Migration-Cloud-Delivery"])
        self.assertEqual(h["X-RunMyCampus-Delivery"], str(row.pk))

    def test_after_cutover_date_suppresses_legacy_even_when_flag_true(self) -> None:
        with mock.patch.object(
            webhook_dispatch.timezone,
            "localdate",
            return_value=date(2026, 8, 19),
        ):
            with override_settings(MIGRATION_CLOUD_EMIT_LEGACY_HEADERS=True):
                cap, _row = _run_dispatcher_capture(
                    secret=self.SECRET, payload=self.PAYLOAD,
                )
        headers = cap["headers"]
        self.assertIn("X-RunMyCampus-Signature", headers)
        self.assertNotIn("X-Migration-Cloud-Signature", headers)
        self.assertNotIn("X-RunMyCampus-Header-Deprecation", headers)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
