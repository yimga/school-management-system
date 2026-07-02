"""Cross-rail sync health — collector, WAL reader, auto-incident, console.

Locks the 9.8 sync-observability wave (2026-07-02): before it, the WAL
dead-letter/conflict Redis streams had ZERO readers anywhere in the codebase,
SODP conflicts were visible only in the tenant portal, and nothing watched any
rail's backlog. These tests assert the collector counts every rail, the
first-ever WAL review-stream reader surfaces scrubbed samples, threshold
breaches open (and recovery resolves) a PlatformIncident through the
idempotent incident services, and the operator console is staff-gated.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.observability.models import PlatformIncident
from apps.observability.sync_health import (
    collect_sync_health,
    evaluate_backlog_incidents,
    peek_wal_review_streams,
)
from apps.platform_runtime.models import OfflineAction
from apps.portal.views_sync_health import sync_health_index
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import SyncConflict


class _FakeRedis:
    """Minimal stream-shaped stub: scan_iter / xlen / xrevrange."""

    def __init__(self, streams: dict[str, list[tuple[str, dict[str, str]]]]):
        self._streams = streams

    def scan_iter(self, match="*", count=200):
        prefix = match.rstrip("*")
        for key in self._streams:
            if key.startswith(prefix):
                yield key.encode()

    def xlen(self, key):
        key = key.decode() if isinstance(key, bytes) else key
        return len(self._streams[key])

    def xrevrange(self, key, count=3):
        key = key.decode() if isinstance(key, bytes) else key
        return list(reversed(self._streams[key]))[:count]


def _wal_fixture():
    return _FakeRedis({
        "rmc.wal.abc123": [("1-1", {"envelope": "{}"})],
        "rmc.wal.deadletter.abc123": [
            ("2-1", {"envelope": "<scrubbed>", "error": "boom " * 100}),
            ("2-2", {"envelope": "<scrubbed>", "error": "short"}),
        ],
        "rmc.wal.conflict.def456": [("3-1", {"domain": "attendance", "conflict": "{}"})],
        # Sidecar types the sweep must skip without aborting.
        "rmc.wal.dedupe.abc123": [],
        "rmc.wal.attempts.abc123": [],
    })


class SyncHealthCollectorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Sync School", slug="sync-school")
        self.user = User.objects.create_user(username="sync_user", password="Test1234!")

    def _offline_action(self, status):
        return OfflineAction.objects.create(
            user=self.user,
            school=self.school,
            action_type=OfflineAction.ActionType.ATTENDANCE,
            payload={},
            status=status,
        )

    def test_collector_counts_all_three_rails(self):
        self._offline_action(OfflineAction.Status.QUEUED)
        self._offline_action(OfflineAction.Status.CONFLICT)
        self._offline_action(OfflineAction.Status.CONFLICT)
        SyncConflict.objects.create(
            school=self.school, entity_type="student", entity_id=1
        )
        snapshot = collect_sync_health(redis_client=_wal_fixture())
        self.assertEqual(snapshot["sodp"]["queued"], 1)
        self.assertEqual(snapshot["sodp"]["conflict"], 2)
        self.assertIsNotNone(snapshot["sodp"]["oldest_queued_age_seconds"])
        self.assertEqual(snapshot["delta"]["pending"], 1)
        self.assertTrue(snapshot["wal"]["available"])
        self.assertEqual(snapshot["wal"]["backlog_depth"], 1)
        self.assertEqual(snapshot["wal"]["deadletter_depth"], 2)
        self.assertEqual(snapshot["wal"]["conflict_depth"], 1)

    def test_collector_degrades_without_redis(self):
        snapshot = collect_sync_health(redis_client=None)
        self.assertFalse(snapshot["wal"]["available"])
        self.assertEqual(snapshot["wal"]["deadletter_depth"], 0)

    def test_wal_review_reader_truncates_and_scopes_fields(self):
        streams = peek_wal_review_streams("deadletter", redis_client=_wal_fixture())
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["tenant_hash"], "abc123")
        self.assertEqual(streams[0]["depth"], 2)
        for sample in streams[0]["samples"]:
            # Only review-relevant fields, truncated — never full envelopes.
            self.assertNotIn("envelope", sample["fields"])
            if "error" in sample["fields"]:
                self.assertLessEqual(len(sample["fields"]["error"]), 200)

    def test_wal_review_reader_unknown_kind(self):
        with self.assertRaises(ValueError):
            peek_wal_review_streams("nope", redis_client=_wal_fixture())


class SyncBacklogIncidentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Sync School 2", slug="sync-school-2")
        self.user = User.objects.create_user(username="sync_user2", password="Test1234!")

    @override_settings(RMC_SYNC_WAL_DEADLETTER_MAX=1)
    def test_breach_opens_incident_and_recovery_resolves(self):
        outcome = evaluate_backlog_incidents(redis_client=_wal_fixture())
        self.assertIn("wal_deadletter", outcome["opened"])
        incident = PlatformIncident.objects.get(source_system="sync_health")
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)
        self.assertEqual(incident.details.get("incident_key"), "sync_backlog_wal_deadletter")

        # Same breach again → idempotent update, still exactly one incident.
        evaluate_backlog_incidents(redis_client=_wal_fixture())
        self.assertEqual(
            PlatformIncident.objects.filter(source_system="sync_health").count(), 1
        )

        # Recovery (empty streams) → auto-resolve.
        outcome = evaluate_backlog_incidents(redis_client=_FakeRedis({}))
        self.assertIn("wal_deadletter", outcome["resolved"])
        incident.refresh_from_db()
        self.assertEqual(incident.status, PlatformIncident.Status.RESOLVED)

    def test_below_threshold_opens_nothing(self):
        evaluate_backlog_incidents(redis_client=_FakeRedis({}))
        self.assertFalse(
            PlatformIncident.objects.filter(source_system="sync_health").exists()
        )


class SyncHealthConsoleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="sync_operator", password="Test1234!", is_staff=True
        )
        self.plain = User.objects.create_user(username="sync_plain", password="Test1234!")

    def test_console_json_shape_staff(self):
        request = RequestFactory().get("/portal/super/sync-health/", {"format": "json"})
        request.user = self.staff
        response = sync_health_index(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn("sodp", payload["snapshot"])
        self.assertIn("delta", payload["snapshot"])
        self.assertIn("wal", payload["snapshot"])
        self.assertIn("wal_deadletter_streams", payload)

    def test_console_denies_non_staff(self):
        request = RequestFactory().get("/portal/super/sync-health/")
        request.user = self.plain
        response = sync_health_index(request)
        self.assertEqual(response.status_code, 302)


class SyncBacklogJobRegistrationTests(TestCase):
    def test_periodic_job_registered(self):
        from apps.platform_runtime import periodic

        periodic.ensure_default_jobs()
        self.assertIn("observability.sync_backlog_monitor", periodic._REGISTRY)
        job = periodic._REGISTRY["observability.sync_backlog_monitor"]
        self.assertTrue(job.enabled)
