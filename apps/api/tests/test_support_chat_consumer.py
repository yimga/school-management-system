"""Support live-chat WebSocket consumer (the deferred Wave 7.4 slice).

Locks: the per-(school, user) private room (isolation), that an inbound line
persists as a submitter-visible reply on the user's open ticket, that it reuses
an open ticket rather than spawning one per message, the validation error paths,
and that the route is registered. Follows the repo's AIChatConsumer test pattern:
TransactionTestCase + async test methods driving the consumer directly with a
mocked ``send`` (no channel layer needed for the receive path).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.test_utils.seed_preserving import RestoresSeedCatalogMixin

User = get_user_model()


class SupportChatConsumerTests(RestoresSeedCatalogMixin, TransactionTestCase):
    def setUp(self):
        from apps.schools.models import School

        s = uuid4().hex[:8]
        self.school = School.objects.create(
            name="Chat High", subdomain=f"scc-{s}", slug=f"scc-{s}", is_active=True,
        )
        self.user = User.objects.create_user(
            username=f"scc-{s}", email=f"scc-{s}@t.test", password="test-pass-123",
        )

    def _consumer(self):
        from apps.api import consumers

        c = consumers.SupportChatConsumer()
        c.scope = {
            "user": self.user,
            "school": self.school,
            "school_id": str(self.school.pk),
            "school_access_denied": False,
        }
        c.user = self.user
        c.send = AsyncMock()
        return c

    @staticmethod
    def _sent(consumer):
        raw = consumer.send.await_args.kwargs.get("text_data") or (
            consumer.send.await_args.args[0] if consumer.send.await_args.args else ""
        )
        return json.loads(raw)

    # ── isolation: the room is private per (school, user) ─────────────────────
    def test_room_is_private_per_user(self):
        from apps.api import consumers
        from apps.schools.channels_tenant_middleware import tenant_sync_room_name

        self.assertEqual(consumers.SupportChatConsumer.room_prefix, "support_chat")
        self.assertTrue(
            issubclass(consumers.SupportChatConsumer, consumers._TenantScopedSyncConsumer)
        )

        other = User.objects.create_user(username=f"o-{uuid4().hex[:6]}", password="x")
        scope_a = {"school_access_denied": False, "school_id": "5", "user": self.user}
        scope_b = {"school_access_denied": False, "school_id": "5", "user": other}
        scope_c = {"school_access_denied": False, "school_id": "6", "user": self.user}
        room_a = tenant_sync_room_name("support_chat", scope_a)
        self.assertTrue(room_a)
        self.assertNotEqual(room_a, tenant_sync_room_name("support_chat", scope_b))
        self.assertNotEqual(room_a, tenant_sync_room_name("support_chat", scope_c))
        # denied binding yields no room at all
        self.assertIsNone(
            tenant_sync_room_name("support_chat", {"school_access_denied": True})
        )

    # ── persistence helper (sync) ─────────────────────────────────────────────
    def test_persist_helper_creates_ticket_and_reply(self):
        from apps.api.consumers import persist_support_chat_message
        from apps.siteconfig.models_feature_controls import (
            GlobalSupportTicket,
            GlobalSupportTicketReply,
        )

        ticket_id, reply_id = persist_support_chat_message(self.user, self.school, "hello")
        ticket = GlobalSupportTicket.objects.get(pk=ticket_id)
        reply = GlobalSupportTicketReply.objects.get(pk=reply_id)
        self.assertEqual(ticket.school_id, self.school.pk)
        self.assertEqual(ticket.user_id, self.user.pk)
        self.assertEqual(reply.body, "hello")
        self.assertEqual(
            reply.visibility, GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
        )

    def test_persist_helper_reuses_open_ticket(self):
        from apps.api.consumers import persist_support_chat_message
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        t1, _ = persist_support_chat_message(self.user, self.school, "first")
        t2, _ = persist_support_chat_message(self.user, self.school, "second")
        self.assertEqual(t1, t2)
        self.assertEqual(
            GlobalSupportTicket.objects.filter(school=self.school, user=self.user).count(), 1
        )

    # ── receive: persists + acks ──────────────────────────────────────────────
    async def test_receive_persists_and_acks(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from apps.siteconfig.models_feature_controls import (
            GlobalSupportTicket,
            GlobalSupportTicketReply,
        )

        c = self._consumer()
        await c.receive(json.dumps({"message": "my printer is broken"}))

        reply = await sync_to_async(
            lambda: GlobalSupportTicketReply.objects.select_related("ticket").get(
                ticket__school=self.school, ticket__user=self.user
            )
        )()
        self.assertEqual(reply.body, "my printer is broken")
        payload = self._sent(c)
        self.assertEqual(payload.get("type"), "ack")
        self.assertTrue(payload.get("ticket_id"))
        ticket_count = await sync_to_async(
            GlobalSupportTicket.objects.filter(school=self.school, user=self.user).count
        )()
        self.assertEqual(ticket_count, 1)

    # ── receive: validation paths (no write) ──────────────────────────────────
    async def test_receive_empty_message_errors(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        c = self._consumer()
        await c.receive(json.dumps({"message": "   "}))
        self.assertIn("error", self._sent(c))
        created = await sync_to_async(
            GlobalSupportTicket.objects.filter(school=self.school, user=self.user).count
        )()
        self.assertEqual(created, 0)

    async def test_receive_invalid_json_errors(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")
        c = self._consumer()
        await c.receive("{not valid json")
        self.assertEqual(self._sent(c).get("error"), "Invalid JSON")

    # ── routing ───────────────────────────────────────────────────────────────
    def test_routing_registers_support_chat(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")
        import config.routing as routing

        patterns = [str(getattr(p, "pattern", "")) for p in routing.websocket_urlpatterns]
        self.assertTrue(any("support/chat" in p for p in patterns), patterns)
