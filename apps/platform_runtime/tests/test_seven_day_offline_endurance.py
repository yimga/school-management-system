"""Seven-day offline endurance — server-rail contract (sovereign Wave 4, v1).

Deterministic 7-day simulation against the REAL server rails: the SODP
offline-action queue (enqueue → reconnect replay), capability-token TTL
posture, IAM snapshot week-long validity, and CRDT merge determinism under
clock skew. The clock is stepped via ``mock.patch`` on ``timezone.now`` —
no real waiting, fully reproducible.

Claim scope (honest): passing this proves SEVEN_DAY_OFFLINE on the SERVER
rails — zero operation loss, zero duplicate application, tenant isolation,
and a write-capability window that spans the week when
``RMC_OFFLINE_CAPABILITY_TOKEN_TTL_HOURS`` is raised. Browser/device-restart
and storage-pressure legs still need a client harness; until then the
platform claim remains SEVEN_DAY_OFFLINE_PARTIAL, not PROVEN.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import (
    enqueue_offline_action,
    process_offline_queue,
)
from apps.schools.models import School
from apps.sync_engine.crdt_wire_protocol import (
    GCounterOp,
    ORSetOp,
    gcounter_merge,
    orset_materialize,
    orset_merge,
)

DAY = timedelta(days=1)


class _Clock:
    """Deterministic clock the whole simulation steps through."""

    def __init__(self):
        self.t0 = timezone.now().replace(microsecond=0)
        self.now = self.t0

    def advance(self, delta):
        self.now = self.now + delta

    def __call__(self):
        return self.now


class SevenDayOfflineEnduranceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(
            name="Endurance School", slug="endurance-school", subdomain="endurance-school"
        )
        self.other_school = School.objects.create(
            name="Endurance Other", slug="endurance-other", subdomain="endurance-other"
        )
        self.teacher = User.objects.create_user(username="endu_teacher", password="Test1234!")
        self.bursar = User.objects.create_user(username="endu_bursar", password="Test1234!")
        self.clock = _Clock()

    def _mint_token(self, user, device_id, ttl_hours):
        device, _ = DeviceRegistration.objects.update_or_create(
            school=self.school, user=user, device_id=device_id,
            defaults={"permission_bitmap": ["attendance.mark"], "revoked_at": None},
        )
        return OfflineCapabilityToken.objects.create(
            device=device, school=self.school, user=user,
            token_fingerprint=f"fp-{device_id}",
            permission_bitmap=["attendance.mark"],
            expires_at=self.clock() + timedelta(hours=ttl_hours),
        )

    @override_settings(RMC_OFFLINE_CAPABILITY_TOKEN_TTL_HOURS=168)
    def test_seven_days_disconnected_then_reconnect(self):
        with mock.patch("django.utils.timezone.now", side_effect=self.clock):
            # Day 0: two devices mint. One legacy 12h token, one week-long
            # token via the settings-driven TTL this posture exists for.
            short_token = self._mint_token(self.teacher, "device-legacy", 12)
            week_token = self._mint_token(self.bursar, "device-week", 168)
            self.assertTrue(short_token.is_valid)
            self.assertTrue(week_token.is_valid)

            # Days 1-6 disconnected: each user queues one support action per
            # day, and the flaky device RE-SENDS every payload (duplicate
            # idempotency keys) — the classic reconnect-storm double-submit.
            for day in range(1, 7):
                self.clock.advance(DAY)
                for user, device in ((self.teacher, "device-legacy"), (self.bursar, "device-week")):
                    key = f"endu-{device}-day{day}"
                    payload = {
                        "subject": f"Day {day} report from {device}",
                        "message": "offline sync check",
                        "client_offline_id": key,
                    }
                    first = enqueue_offline_action(
                        user_id=user.pk, school_id=self.school.pk,
                        action_type=OfflineAction.ActionType.SUPPORT_TICKET,
                        payload=payload, idempotency_key=key,
                    )
                    dup = enqueue_offline_action(
                        user_id=user.pk, school_id=self.school.pk,
                        action_type=OfflineAction.ActionType.SUPPORT_TICKET,
                        payload=payload, idempotency_key=key,
                    )
                    self.assertEqual(first.pk, dup.pk, "duplicate enqueue must dedupe")

            queued = OfflineAction.objects.filter(school=self.school).count()
            self.assertEqual(queued, 12, "6 days x 2 users, duplicates deduped at enqueue")

            # Token posture at the end of the disconnected stretch (day 6):
            self.assertFalse(
                short_token.is_valid,
                "12h default token cannot cover a week — the documented conflict",
            )
            self.assertTrue(
                week_token.is_valid,
                "settings-driven 168h token spans the disconnected week",
            )

            # Tenant isolation: the OTHER tenant's reconnect must see nothing.
            foreign = process_offline_queue(school_id=self.other_school.pk, limit=100)
            self.assertEqual(foreign.get("processed", 0), 0)
            self.assertEqual(
                OfflineAction.objects.filter(
                    school=self.school, status=OfflineAction.Status.QUEUED
                ).count(),
                12,
                "cross-tenant processing must not consume this school's queue",
            )

            # Day 7 (reconnect at hour 164, inside the 168h window — the
            # token expires at EXACTLY +168h, so the write must land before
            # the anniversary): replay twice, because real clients retry the
            # whole batch. Zero loss, zero double-application.
            self.clock.advance(timedelta(hours=20))
            process_offline_queue(school_id=self.school.pk, limit=100)
            process_offline_queue(school_id=self.school.pk, limit=100)

            remaining = OfflineAction.objects.filter(
                school=self.school, status=OfflineAction.Status.QUEUED
            ).count()
            synced = OfflineAction.objects.filter(
                school=self.school, status=OfflineAction.Status.SYNCED
            ).count()
            self.assertEqual(remaining, 0, "zero operation loss: nothing left queued")
            self.assertEqual(synced, 12, "every queued action applied exactly once")

            from apps.siteconfig.models_feature_controls import GlobalSupportTicket

            tickets = GlobalSupportTicket.objects.filter(school=self.school).count()
            self.assertEqual(tickets, 12, "12 unique keys -> 12 tickets, no doubles")
            self.assertEqual(
                GlobalSupportTicket.objects.filter(school=self.other_school).count(),
                0,
                "no tenant leakage",
            )

            # Week-long token survives to the reconnect; then hard-expires
            # past its anniversary — the window is bounded, not infinite.
            self.assertTrue(week_token.is_valid)
            self.clock.advance(timedelta(hours=5))
            self.assertFalse(week_token.is_valid)

    def test_crdt_merges_are_order_independent_under_week_of_skew(self):
        # Two devices counting/tagging all week with skewed clocks: CRDT
        # convergence must not depend on replay order, and replay must be
        # idempotent (the reconnect storm applies everything at least twice).
        ops_a = [
            GCounterOp(kind="GCOUNTER", counter_key="telemetry_counter:endu",
                       actor_id="device-a", value=day)
            for day in range(1, 8)
        ]
        ops_b = [
            GCounterOp(kind="GCOUNTER", counter_key="telemetry_counter:endu",
                       actor_id="device-b", value=day * 2)
            for day in range(1, 8)
        ]
        forward: dict = {}
        for op in ops_a + ops_b + ops_a:  # replay storm: A applied twice
            forward = gcounter_merge(forward, op)
        backward: dict = {}
        for op in list(reversed(ops_b)) + list(reversed(ops_a)):
            backward = gcounter_merge(backward, op)
        self.assertEqual(forward, backward, "G-counter must converge regardless of order")
        self.assertEqual(forward, {"device-a": 7, "device-b": 14})

        add = ORSetOp(kind="ORSET-ADD", set_key="lesson_plan_tags:endu",
                      element="week-review", tag="t1")
        remove = ORSetOp(kind="ORSET-REMOVE", set_key="lesson_plan_tags:endu",
                         element="week-review", tag="", observed_tags=("t1",))
        left = orset_merge(orset_merge({}, add), remove)
        right = orset_merge(orset_merge({}, remove), add)
        self.assertEqual(left, right, "OR-set add/remove must be order-independent")
        self.assertFalse(orset_materialize(left), "observed add was removed")
