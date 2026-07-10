"""Real-time notification fan-out — producer + consumer + tenant isolation.

Locks the people-domain notification rail added on 2026-07-10:

  * the canonical write path (``finance.NotificationManager.notify_unread``)
    persists a row AND pushes it to the recipient's tenant-scoped Channels group;
  * the group name the producer sends to is byte-identical to the one
    ``NotificationSyncConsumer`` joins (``tenant_sync_room_name`` contract), so a
    send actually reaches the listening socket;
  * a notification for school A is fanned out ONLY to school A's room — a socket
    the same user opened on school B never receives it (tenant isolation);
  * the recipient's in-app preference is honored — a user who deselected the
    ``APP`` channel is not live-pushed (the row still persists);
  * the consumer handler delivers a group message to the client socket.

Follows the repo's consumer test pattern (TransactionTestCase; the sync producer
is exercised with a mocked channel layer to avoid ``async_to_sync`` inside a
running loop, and the consumer/group round-trip runs inside a single async loop
with a fresh ``InMemoryChannelLayer`` — mirrors ``test_support_agent_console``).
"""

from __future__ import annotations

import asyncio
import json
from unittest import mock
from unittest.mock import AsyncMock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.api import consumers
from apps.finance.models import Notification
from apps.finance.notification_realtime import (
    build_notification_payload,
    notification_room_name,
    push_notification_realtime,
    wants_realtime_notification,
)
from apps.schools.channels_tenant_middleware import tenant_sync_room_name

User = get_user_model()


def _channels_ready() -> bool:
    return bool(getattr(consumers, "CHANNELS_AVAILABLE", False))


class NotificationRealtimeFanoutTests(TransactionTestCase):
    def setUp(self):
        from apps.schools.models import School

        s = uuid4().hex[:8]
        self.school = School.objects.create(
            name="Fanout High", subdomain=f"nrf-{s}", slug=f"nrf-{s}", is_active=True,
        )
        self.other_school = School.objects.create(
            name="Other High", subdomain=f"oth-{s}", slug=f"oth-{s}", is_active=True,
        )
        self.user = User.objects.create_user(
            username=f"rcp-{s}", email=f"rcp-{s}@t.test", password="test-pass-123",
        )

    # ── room-name contract (producer <-> consumer) ─────────────────────────────
    def test_room_formula_matches_consumer(self):
        # The producer's group name must equal the one the tenant-scoped consumer
        # base joins for prefix "notifications_sync".
        scope = {
            "school_access_denied": False,
            "school_id": str(self.school.pk),
            "user": self.user,
        }
        self.assertEqual(
            notification_room_name(self.school.pk, self.user.pk),
            tenant_sync_room_name("notifications_sync", scope),
        )
        self.assertEqual(
            consumers.NotificationSyncConsumer.room_prefix, "notifications_sync"
        )

    # ── producer: notify_unread persists AND fans out to the recipient room ─────
    def test_notify_unread_fans_out_to_recipient_room(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        fake_layer = mock.Mock()
        fake_layer.group_send = AsyncMock()
        with mock.patch(
            "channels.layers.get_channel_layer", return_value=fake_layer
        ):
            notif = Notification.objects.notify_unread(
                title="Late arrival",
                message="Ada was marked late for period 2.",
                severity=Notification.Severity.WARNING,
                recipient=self.user,
                school=self.school,
                created_by=self.user,
            )
        # Persisted.
        self.assertIsNotNone(notif.pk)
        self.assertEqual(notif.recipient_id, self.user.pk)
        # Fanned out to exactly the recipient's tenant-scoped room.
        fake_layer.group_send.assert_awaited_once()
        room, event = fake_layer.group_send.await_args.args
        self.assertEqual(room, notification_room_name(self.school.pk, self.user.pk))
        self.assertEqual(event["type"], "notification.message")
        self.assertEqual(event["notification"]["title"], "Late arrival")
        self.assertEqual(event["notification"]["severity"], "WARNING")
        self.assertEqual(event["notification"]["id"], notif.pk)

    # ── tenant isolation: never fans out to another school's room ──────────────
    def test_fanout_is_school_scoped_not_cross_tenant(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        fake_layer = mock.Mock()
        fake_layer.group_send = AsyncMock()
        with mock.patch(
            "channels.layers.get_channel_layer", return_value=fake_layer
        ):
            Notification.objects.notify_unread(
                title="Fee due",
                message="Term 2 balance is outstanding.",
                recipient=self.user,
                school=self.school,
            )
        room, _event = fake_layer.group_send.await_args.args
        self.assertEqual(room, notification_room_name(self.school.pk, self.user.pk))
        # The SAME recipient's room on a different tenant must not be the target.
        self.assertNotEqual(
            room, notification_room_name(self.other_school.pk, self.user.pk)
        )

    def test_no_fanout_when_notification_has_no_school(self):
        # A platform/global (null-school) row persists but is never broadcast, so
        # a live push can never cross a tenant boundary.
        self.assertFalse(
            push_notification_realtime(
                Notification.objects.notify_unread(
                    title="Platform notice", message="hello", recipient=self.user,
                )
            )
        )

    # ── preference: APP opt-out suppresses the live push ───────────────────────
    def test_app_optout_suppresses_push_but_persists(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from apps.siteconfig.models_tooling import UserPreference

        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": ["EMAIL", "SMS"]},
        )
        self.assertFalse(wants_realtime_notification(self.user.pk))

        fake_layer = mock.Mock()
        fake_layer.group_send = AsyncMock()
        with mock.patch(
            "channels.layers.get_channel_layer", return_value=fake_layer
        ):
            notif = Notification.objects.notify_unread(
                title="Discipline note",
                message="Detention scheduled.",
                recipient=self.user,
                school=self.school,
            )
        # Persisted for the inbox...
        self.assertIsNotNone(notif.pk)
        # ...but NOT live-pushed (opted out of the APP channel).
        fake_layer.group_send.assert_not_awaited()

    def test_app_channel_selected_is_delivered(self):
        from apps.siteconfig.models_tooling import UserPreference

        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": ["APP"]},
        )
        self.assertTrue(wants_realtime_notification(self.user.pk))

    def test_default_empty_channels_is_delivered(self):
        # Default state (no explicit channel selection) delivers live — opt-out,
        # not opt-in. Covers both a missing pref row and an empty channels list.
        from apps.siteconfig.models_tooling import UserPreference

        UserPreference.objects.filter(user=self.user).delete()
        self.assertTrue(wants_realtime_notification(self.user.pk))
        UserPreference.objects.update_or_create(
            user=self.user, defaults={"notification_channels": []},
        )
        self.assertTrue(wants_realtime_notification(self.user.pk))

    # ── consumer: a group message is delivered to the client socket ────────────
    def test_group_message_reaches_consumer_socket(self):
        if not _channels_ready():
            self.skipTest("channels not available")

        async def _run():
            from channels.layers import InMemoryChannelLayer

            layer = InMemoryChannelLayer()
            room = notification_room_name(self.school.pk, self.user.pk)
            await layer.group_add(room, "notif.recipient.chan")
            # A DIFFERENT school's room, same user — must receive nothing.
            other_room = notification_room_name(self.other_school.pk, self.user.pk)
            await layer.group_add(other_room, "notif.other.chan")

            payload = build_notification_payload(
                Notification(
                    title="Eval published",
                    message="Term report is ready.",
                    severity=Notification.Severity.INFO,
                )
            )
            await layer.group_send(
                room, {"type": "notification.message", "notification": payload}
            )

            evt = await layer.receive("notif.recipient.chan")
            self.assertEqual(evt["type"], "notification.message")

            # Tenant isolation: the other tenant's channel got nothing.
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(layer.receive("notif.other.chan"), timeout=0.1)

            # The consumer handler delivers the event to the client socket.
            consumer = consumers.NotificationSyncConsumer()
            consumer.send = AsyncMock()
            await consumer.notification_message(evt)
            frame = json.loads(consumer.send.await_args.kwargs["text_data"])
            self.assertEqual(frame["type"], "notification")
            self.assertEqual(frame["notification"]["title"], "Eval published")

        asyncio.run(_run())
