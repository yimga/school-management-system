"""v3.40.0 Agent 14 — tests for the per-tenant audit-event rate-limit.

Verifies that ``AuditEventManager.record()`` rate-limits per
(tenant_id_hash, event_type) on a sliding 1h window, emits exactly one
meta-event per tenant per hour on limit-hit, raises a typed
``AuditEventRateLimitExceeded`` to the caller, and honors both the
``MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR`` ceiling and the
``MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED`` emergency kill-switch.
"""
from __future__ import annotations

import logging
from unittest import mock

from django.test import TestCase, override_settings

from apps.migration_cloud import models_audit as _audit_mod
from apps.migration_cloud.models_audit import (
    AuditEventRateLimitExceeded,
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
    _AUDIT_RATE_LIMIT_META_TYPE,
    _hash_tenant_slug,
    _rate_limit_reset_for_tests,
)


class _ClockProvider:
    """Monotonic-clock stand-in we can advance from the test."""

    def __init__(self, start: float = 1000.0):
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


class _Base(TestCase):
    """Shared setUp: fresh counter state + injectable clock."""

    def setUp(self) -> None:
        super().setUp()
        _rate_limit_reset_for_tests()
        self.clock = _ClockProvider()
        # Patch the module-level _rate_limit_clock for the test.
        self._clock_patch = mock.patch.object(
            _audit_mod, "_rate_limit_clock", self.clock,
        )
        self._clock_patch.start()

    def tearDown(self) -> None:
        self._clock_patch.stop()
        _rate_limit_reset_for_tests()
        super().tearDown()


@override_settings(
    MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR=3,
    MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED=False,
)
class LimitEnforcementTests(_Base):

    def test_under_limit_writes_succeed(self):
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-under",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        # 3 stored.
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                tenant_id_hash=_hash_tenant_slug("tenant-rl-under"),
                event_type=MigrationCloudAuditEventType.TOKEN_MINT.value,
            ).count(),
            3,
        )

    def test_over_limit_raises_typed_exception(self):
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-over",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        with self.assertRaises(AuditEventRateLimitExceeded) as cm:
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-over",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        exc = cm.exception
        self.assertEqual(exc.event_type, MigrationCloudAuditEventType.TOKEN_MINT.value)
        self.assertEqual(exc.limit, 3)
        self.assertEqual(exc.count_in_window, 3)
        self.assertEqual(exc.tenant_id_hash, _hash_tenant_slug("tenant-rl-over"))

    def test_meta_event_written_once_per_hour(self):
        # Burn through and overflow twice — meta event should appear exactly
        # once.
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-meta",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        for _ in range(2):
            with self.assertRaises(AuditEventRateLimitExceeded):
                MigrationCloudAuditEvent.objects.record(
                    tenant_slug="tenant-rl-meta",
                    event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                    payload_summary={"n": 1},
                )
        meta_count = MigrationCloudAuditEvent.objects.filter(
            tenant_id_hash=_hash_tenant_slug("tenant-rl-meta"),
            event_type=_AUDIT_RATE_LIMIT_META_TYPE,
        ).count()
        self.assertEqual(meta_count, 1)

    def test_meta_event_payload_has_no_pii(self):
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-payload",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        with self.assertRaises(AuditEventRateLimitExceeded):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-payload",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        meta = MigrationCloudAuditEvent.objects.get(
            tenant_id_hash=_hash_tenant_slug("tenant-rl-payload"),
            event_type=_AUDIT_RATE_LIMIT_META_TYPE,
        )
        # Payload keys ONLY: tenant_sha256_prefix / event_type / count / limit.
        self.assertEqual(
            set(meta.payload_summary.keys()),
            {"tenant_sha256_prefix", "event_type", "count_in_window", "limit"},
        )
        # Slug never appears in payload.
        for v in meta.payload_summary.values():
            self.assertNotIn("tenant-rl-payload", str(v))

    def test_different_tenant_has_independent_counter(self):
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-A",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        # Tenant B still fresh.
        MigrationCloudAuditEvent.objects.record(
            tenant_slug="tenant-B",
            event_type=MigrationCloudAuditEventType.TOKEN_MINT,
            payload_summary={"n": 1},
        )
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                tenant_id_hash=_hash_tenant_slug("tenant-B"),
                event_type=MigrationCloudAuditEventType.TOKEN_MINT.value,
            ).count(),
            1,
        )

    def test_different_event_type_has_independent_counter(self):
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-etype",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        # Different event type — fresh.
        MigrationCloudAuditEvent.objects.record(
            tenant_slug="tenant-rl-etype",
            event_type=MigrationCloudAuditEventType.MAA_SIGN,
            payload_summary={"v": "v1.0"},
        )
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                tenant_id_hash=_hash_tenant_slug("tenant-rl-etype"),
                event_type=MigrationCloudAuditEventType.MAA_SIGN.value,
            ).count(),
            1,
        )

    def test_window_slides_after_one_hour(self):
        # Fill the bucket.
        for _ in range(3):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-slide",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        with self.assertRaises(AuditEventRateLimitExceeded):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-slide",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        # Advance 1h + 1s — all entries are now outside the window.
        self.clock.advance(3601.0)
        MigrationCloudAuditEvent.objects.record(
            tenant_slug="tenant-rl-slide",
            event_type=MigrationCloudAuditEventType.TOKEN_MINT,
            payload_summary={"n": 1},
        )
        # We accept it — count of TOKEN_MINT real events should be 4
        # (3 pre + 1 post). The middle rejected attempts never wrote.
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                tenant_id_hash=_hash_tenant_slug("tenant-rl-slide"),
                event_type=MigrationCloudAuditEventType.TOKEN_MINT.value,
            ).count(),
            4,
        )

    def test_assert_no_full_tenant_slug_in_logs(self):
        with self.assertLogs("apps.migration_cloud.models_audit", level="WARNING") as logs:
            for _ in range(3):
                MigrationCloudAuditEvent.objects.record(
                    tenant_slug="tenant-rl-log",
                    event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                    payload_summary={"n": 1},
                )
            with self.assertRaises(AuditEventRateLimitExceeded):
                MigrationCloudAuditEvent.objects.record(
                    tenant_slug="tenant-rl-log",
                    event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                    payload_summary={"n": 1},
                )
        combined = "\n".join(logs.output)
        self.assertNotIn("tenant-rl-log", combined)
        # Sha-256 prefix MUST appear.
        prefix = _hash_tenant_slug("tenant-rl-log")
        self.assertIn(prefix, combined)


@override_settings(
    MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR=3,
    MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED=True,
)
class DisabledKillSwitchTests(_Base):

    def test_kill_switch_disables_rate_limit(self):
        # 10 writes under a limit of 3 — all should succeed.
        for _ in range(10):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-kill",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                tenant_id_hash=_hash_tenant_slug("tenant-rl-kill"),
                event_type=MigrationCloudAuditEventType.TOKEN_MINT.value,
            ).count(),
            10,
        )
        # No meta event written.
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                event_type=_AUDIT_RATE_LIMIT_META_TYPE,
            ).count(),
            0,
        )


@override_settings(
    MIGRATION_CLOUD_AUDIT_MAX_EVENTS_PER_TENANT_PER_HOUR=2,
    MIGRATION_CLOUD_AUDIT_RATE_LIMIT_DISABLED=False,
)
class MetaEventNotItselfRateLimitedTests(_Base):

    def test_meta_event_emit_always_allowed(self):
        # Trip rate limit; meta event lands once even though normal
        # event_type counter is already at the cap.
        for _ in range(2):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-meta2",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        with self.assertRaises(AuditEventRateLimitExceeded):
            MigrationCloudAuditEvent.objects.record(
                tenant_slug="tenant-rl-meta2",
                event_type=MigrationCloudAuditEventType.TOKEN_MINT,
                payload_summary={"n": 1},
            )
        self.assertEqual(
            MigrationCloudAuditEvent.objects.filter(
                event_type=_AUDIT_RATE_LIMIT_META_TYPE,
            ).count(),
            1,
        )
