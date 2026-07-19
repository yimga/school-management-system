"""Real-time substitute-market fan-out — producer + consumer + tenant isolation.

Closes the dangling-producer latent on the people/real-time metric: the
substitute-shift market (``apps/schoolops/substitute_market.py``) already
``group_send``-ed cover-shift open/claim events to the per-school Channels group
``school-{school_id}-substitute-market``, but NO consumer joined that group, so
the live broadcast was a no-op. ``apps.api.consumers.SubstituteMarketConsumer``
+ the ``ws/substitute-market/`` route now apply that producer.

This locks:

  * the group name the producer sends to is byte-identical to the one the
    consumer joins (``substitute_market_room_name`` is the single source), so a
    send actually reaches the listening socket;
  * the room is PER-SCHOOL (a broadcast) and is derived ONLY from the socket's
    tenant-bound ``scope["school_id"]`` — a socket can never join another
    tenant's market group, and school A's shift event never reaches school B;
  * the producer is fail-soft — a broken channel layer never breaks the cover
    DB write;
  * the consumer handler delivers a group message to the client socket.

Mirrors ``test_notification_realtime_fanout`` (TransactionTestCase; the sync
producer is exercised with a mocked channel layer to avoid ``async_to_sync``
inside a running loop, and the consumer/group round-trip runs inside a single
async loop with a fresh ``InMemoryChannelLayer``).
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from unittest import mock
from unittest.mock import AsyncMock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase

from apps.api import consumers
from apps.schoolops.substitute_market import (
    claim_shift,
    open_shift,
    substitute_market_room_name,
)
from apps.schools.channels_tenant_middleware import tenant_sync_room_name

User = get_user_model()


def _channels_ready() -> bool:
    return bool(getattr(consumers, "CHANNELS_AVAILABLE", False))


class SubstituteMarketRealtimeFanoutTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        from apps.academics.models import Department
        from apps.people.models import TeacherProfile
        from apps.schools.models import School

        s = uuid4().hex[:8]
        self.school = School.objects.create(
            name="Sub Market High", subdomain=f"smh-{s}", slug=f"smh-{s}", is_active=True,
        )
        self.other_school = School.objects.create(
            name="Other High", subdomain=f"oth-{s}", slug=f"oth-{s}", is_active=True,
        )
        self.absent = User.objects.create_user(
            username=f"absent-{s}", email=f"absent-{s}@t.test", password="test-pass-123",
            role=User.Role.TEACHER,
        )
        self.sub = User.objects.create_user(
            username=f"sub-{s}", email=f"sub-{s}@t.test", password="test-pass-123",
            role=User.Role.TEACHER,
        )
        dept = Department.objects.create(school=self.school, name="STEM", code=f"ST{s[:4]}")
        TeacherProfile.objects.create(
            school=self.school, user=self.absent, department=dept, is_active=True,
            phone="+237600000001",
        )
        TeacherProfile.objects.create(
            school=self.school, user=self.sub, department=dept, is_active=True,
            phone="+237600000002",
        )
        self.work_date = date(2026, 9, 14)

    # ── room-name contract (producer <-> consumer) ─────────────────────────────
    def test_room_formula_matches_consumer(self):
        # The producer's group name must equal the one the consumer resolves from
        # a tenant-bound socket scope, and both must equal the literal formula.
        scope = {
            "school_access_denied": False,
            "school_id": str(self.school.pk),
            "user": self.absent,
        }
        consumer = consumers.SubstituteMarketConsumer()
        consumer.scope = scope
        self.assertEqual(
            substitute_market_room_name(self.school.pk),
            consumer.resolve_room_group_name(),
        )
        self.assertEqual(
            substitute_market_room_name(self.school.pk),
            f"school-{self.school.pk}-substitute-market",
        )

    # ── producer: _publish_substitute_event fans out to the school room ─────────
    def test_producer_fans_out_to_school_room(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from apps.schoolops import substitute_market as sm

        fake_layer = mock.Mock()
        fake_layer.group_send = AsyncMock()
        with mock.patch("channels.layers.get_channel_layer", return_value=fake_layer):
            sm._publish_substitute_event(
                room_school_id=str(self.school.pk),
                payload={"event": "shift.open", "shift_id": "abc"},
            )
        fake_layer.group_send.assert_awaited_once()
        room, event = fake_layer.group_send.await_args.args
        self.assertEqual(room, substitute_market_room_name(self.school.pk))
        self.assertEqual(event["type"], "substitute.shift.event")
        self.assertEqual(event["payload"]["event"], "shift.open")

    # ── producer end-to-end: open_shift triggers the fan-out to the school room ─
    def test_open_shift_triggers_realtime_fanout(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        fake_layer = mock.Mock()
        fake_layer.group_send = AsyncMock()
        with mock.patch("channels.layers.get_channel_layer", return_value=fake_layer):
            open_shift(
                school=self.school,
                absent_teacher_id=self.absent.pk,
                work_date=self.work_date,
                period_label="Period 2",
            )
        fake_layer.group_send.assert_awaited_once()
        room, event = fake_layer.group_send.await_args.args
        self.assertEqual(room, substitute_market_room_name(self.school.pk))
        self.assertEqual(event["type"], "substitute.shift.event")

    # ── tenant isolation: the two schools' rooms differ ─────────────────────────
    def test_fanout_is_school_scoped_not_cross_tenant(self):
        self.assertNotEqual(
            substitute_market_room_name(self.school.pk),
            substitute_market_room_name(self.other_school.pk),
        )

    # ── tenant isolation: a socket can only join its OWN school's room ──────────
    def test_cross_tenant_subscription_impossible(self):
        # A user bound to school A resolves ONLY school A's room, never B's.
        scope_a = {
            "school_access_denied": False,
            "school_id": str(self.school.pk),
            "user": self.absent,
        }
        consumer = consumers.SubstituteMarketConsumer()
        consumer.scope = scope_a
        self.assertEqual(
            consumer.resolve_room_group_name(),
            substitute_market_room_name(self.school.pk),
        )
        self.assertNotEqual(
            consumer.resolve_room_group_name(),
            substitute_market_room_name(self.other_school.pk),
        )
        # A denied / unbound scope resolves to None → connect() closes 4403 and
        # NEVER joins a group (there is no client-supplied school-id path in).
        denied = {
            "school_access_denied": True,
            "school_id": str(self.other_school.pk),
            "user": self.absent,
        }
        consumer.scope = denied
        self.assertIsNone(consumer.resolve_room_group_name())
        no_school = {
            "school_access_denied": False,
            "school_id": None,
            "user": self.absent,
        }
        consumer.scope = no_school
        self.assertIsNone(consumer.resolve_room_group_name())

    # ── consumer: a group message is delivered to the client socket ────────────
    def test_group_message_reaches_consumer_socket(self):
        if not _channels_ready():
            self.skipTest("channels not available")

        async def _run():
            from channels.layers import InMemoryChannelLayer

            layer = InMemoryChannelLayer()
            room = substitute_market_room_name(self.school.pk)
            await layer.group_add(room, "sub.market.chan")
            # A DIFFERENT school's room — must receive nothing.
            other_room = substitute_market_room_name(self.other_school.pk)
            await layer.group_add(other_room, "sub.other.chan")

            payload = {"schema_version": "substitute_shift.v1", "event": "shift.open"}
            await layer.group_send(
                room, {"type": "substitute.shift.event", "payload": payload}
            )

            evt = await layer.receive("sub.market.chan")
            self.assertEqual(evt["type"], "substitute.shift.event")

            # Tenant isolation: the other tenant's channel got nothing.
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(layer.receive("sub.other.chan"), timeout=0.1)

            # The consumer handler delivers the event to the client socket.
            consumer = consumers.SubstituteMarketConsumer()
            consumer.send = AsyncMock()
            await consumer.substitute_shift_event(evt)
            frame = json.loads(consumer.send.await_args.kwargs["text_data"])
            self.assertEqual(frame["type"], "substitute_shift")
            self.assertEqual(frame["payload"]["event"], "shift.open")

        asyncio.run(_run())

    # ── fail-soft: a broken channel layer never breaks the cover DB write ───────
    def test_claim_shift_persists_even_if_channel_layer_errors(self):
        from apps.schoolops.models import SubstituteCover

        shift = open_shift(
            school=self.school,
            absent_teacher_id=self.absent.pk,
            work_date=self.work_date,
            period_label="Period 3",
            publish_fn=lambda _payload: None,
        )

        def _boom(*_args, **_kwargs):
            raise RuntimeError("channel layer down")

        with mock.patch("channels.layers.get_channel_layer", side_effect=_boom):
            cover_id = claim_shift(
                school=self.school,
                shift_id=shift.shift_id,
                substitute_teacher_id=self.sub.pk,
            )
        self.assertGreater(cover_id, 0)
        cover = SubstituteCover.objects.get(pk=cover_id)
        self.assertEqual(cover.covering_teacher_id, self.sub.pk)

    # ── regression: the base extract-method refactor preserves the per-user room
    def test_default_tenant_scoped_room_unchanged_by_refactor(self):
        # A per-(school, user) consumer still resolves the exact
        # tenant_sync_room_name it did before the base gained the override hook.
        scope = {
            "school_access_denied": False,
            "school_id": str(self.school.pk),
            "user": self.absent,
        }
        consumer = consumers.NotificationSyncConsumer()
        consumer.scope = scope
        self.assertEqual(
            consumer.resolve_room_group_name(),
            tenant_sync_room_name("notifications_sync", scope),
        )


class SubstituteMarketBrowserClientWiringTests(TransactionTestCase):
    """Metric 12 residual — browser client must bind the live WS path.

    Producer + consumer were already proven; without a page-scoped JS client the
    ops hub still only refreshed on full navigation. These checks lock the asset
    + template contract (path-scoped, no Django render required).
    """

    def test_browser_client_targets_substitute_market_ws_path(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        js = (root / "static" / "js" / "rmc-substitute-market.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('/ws/substitute-market/', js)
        self.assertIn("substitute_shift", js)
        self.assertIn("shift.open", js)
        self.assertIn("shift.claimed", js)
        self.assertIn("data-rmc-substitute-market", js)

    def test_ops_substitutes_template_loads_browser_client(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        tpl = (
            root / "templates" / "schoolops" / "ops_substitutes.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-rmc-substitute-market", tpl)
        self.assertIn("rmc-substitute-market.js", tpl)
