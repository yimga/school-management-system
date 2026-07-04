"""Operator ("agent-side") live support console — consumer, helpers, and view.

Locks the /super/ half of the Wave 7.4 support live-chat loop:

  * the operator gate (``agent_console_access``) mirrors
    ``require_platform_scope(team.read)`` — superuser yes, plain user no, tenant
    staff no — so an operator surface never leaks to tenant staff;
  * the room the operator broadcasts into is byte-identical to the room the
    customer's ``SupportChatConsumer`` listens on (``support_chat_room_name`` ==
    ``tenant_sync_room_name``), and is derived server-side from the DB ticket,
    never from client input;
  * an operator reply persists as a submitter-visible reply authored by the
    operator and advances SLA / assignment / status via the FSM;
  * a full agent -> customer delivery through an in-memory channel layer;
  * the console view's gate + queue selection.

Follows the repo's consumer test pattern (TransactionTestCase + async methods
driving the consumer directly with a mocked ``send``).
"""

from __future__ import annotations

import json
import uuid
from unittest import mock
from unittest.mock import AsyncMock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.api import consumers
from apps.api.consumers import (
    agent_console_access,
    load_support_ticket_for_agent,
    persist_support_agent_reply,
    support_chat_room_name,
)
from apps.schools.channels_tenant_middleware import tenant_sync_room_name

User = get_user_model()


def _channels_ready() -> bool:
    return bool(getattr(consumers, "CHANNELS_AVAILABLE", False))


class SupportAgentConsoleTests(TransactionTestCase):
    def setUp(self):
        from apps.schools.models import School
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        s = uuid4().hex[:8]
        self.school = School.objects.create(
            name="Chat High", subdomain=f"sac-{s}", slug=f"sac-{s}", is_active=True,
        )
        self.user = User.objects.create_user(
            username=f"cust-{s}", email=f"cust-{s}@t.test", password="test-pass-123",
        )
        self.operator = User.objects.create_user(
            username=f"op-{s}", email=f"op-{s}@t.test", password="test-pass-123",
        )
        self.operator.is_superuser = True
        self.operator.save(update_fields=["is_superuser"])
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="Printer down",
            status=GlobalSupportTicket.Status.OPEN,
            metadata={"channel": "live_chat"},
        )

    # ── helpers ───────────────────────────────────────────────────────────────
    def _agent_ws(self):
        from channels.layers import InMemoryChannelLayer

        c = consumers.SupportAgentConsumer()
        c.scope = {"user": self.operator}
        c.user = self.operator
        c.send = AsyncMock()
        c.channel_layer = InMemoryChannelLayer()
        c.channel_name = "agent.test.chan"
        c.subscribed_room = None
        c.subscribed_ticket_id = None
        return c

    @staticmethod
    def _last_frame(consumer):
        return json.loads(consumer.send.await_args.kwargs["text_data"])

    # ── operator gate (isolation) ──────────────────────────────────────────────
    def test_agent_console_access_allows_superuser(self):
        self.assertTrue(agent_console_access(self.operator))

    def test_agent_console_access_denies_plain_user(self):
        self.assertFalse(agent_console_access(self.user))

    def test_agent_console_access_denies_tenant_staff(self):
        from apps.schools.models import SchoolMembership

        staff = User.objects.create_user(
            username=f"staff-{uuid4().hex[:6]}", password="x",
        )
        # A tenant membership (even ADMIN by default) must NOT unlock the operator
        # console — tenant staff never reach a control-plane surface.
        SchoolMembership.objects.create(user=staff, school=self.school)
        self.assertFalse(agent_console_access(staff))

    def test_agent_console_access_denies_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(agent_console_access(AnonymousUser()))

    # ── room formula parity (the whole loop hinges on this) ────────────────────
    def test_room_formula_matches_customer(self):
        scope = {
            "school_access_denied": False,
            "school_id": str(self.school.pk),
            "user": self.user,
        }
        self.assertEqual(
            tenant_sync_room_name("support_chat", scope),
            support_chat_room_name(str(self.school.pk), str(self.user.pk)),
        )

    # ── persistence helper ──────────────────────────────────────────────────────
    def test_persist_agent_reply_advances_ticket(self):
        from apps.siteconfig.models_feature_controls import (
            GlobalSupportTicket,
            GlobalSupportTicketReply,
        )

        result = persist_support_agent_reply(self.operator, str(self.ticket.pk), "on it")
        self.assertIsNotNone(result)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, GlobalSupportTicket.Status.IN_PROGRESS)
        self.assertEqual(self.ticket.assigned_to_id, self.operator.pk)
        self.assertIsNotNone(self.ticket.first_response_at)

        reply = GlobalSupportTicketReply.objects.get(pk=result["reply_id"])
        self.assertEqual(reply.author_id, self.operator.pk)
        self.assertEqual(reply.body, "on it")
        self.assertEqual(
            reply.visibility, GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
        )
        self.assertEqual(result["school_id"], str(self.school.pk))
        self.assertEqual(result["user_id"], str(self.user.pk))

    def test_persist_agent_reply_missing_ticket_returns_none(self):
        self.assertIsNone(
            persist_support_agent_reply(self.operator, str(uuid.uuid4()), "x")
        )

    # ── history load (live pane excludes internal notes) ───────────────────────
    def test_load_ticket_history_excludes_internal_notes(self):
        from apps.siteconfig.models_feature_controls import GlobalSupportTicketReply as R

        R.objects.create(
            ticket=self.ticket, author=self.user, body="help me",
            visibility=R.Visibility.SUBMITTER_VISIBLE,
        )
        R.objects.create(
            ticket=self.ticket, author=self.operator, body="secret note",
            visibility=R.Visibility.INTERNAL,
        )
        info = load_support_ticket_for_agent(str(self.ticket.pk))
        bodies = [h["body"] for h in info["history"]]
        self.assertIn("help me", bodies)
        self.assertNotIn("secret note", bodies)
        customer_line = next(h for h in info["history"] if h["body"] == "help me")
        self.assertEqual(customer_line["sender_role"], "customer")
        self.assertEqual(info["school_id"], str(self.school.pk))
        self.assertEqual(info["user_id"], str(self.user.pk))

    def test_load_ticket_missing_returns_none(self):
        self.assertIsNone(load_support_ticket_for_agent(str(uuid.uuid4())))

    # ── connect gate ────────────────────────────────────────────────────────────
    async def test_connect_accepts_operator(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        c = consumers.SupportAgentConsumer()
        c.scope = {"user": self.operator}
        c.accept = AsyncMock()
        c.close = AsyncMock()
        await c.connect()
        c.accept.assert_awaited()
        c.close.assert_not_awaited()

    async def test_connect_rejects_non_operator(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        c = consumers.SupportAgentConsumer()
        c.scope = {"user": self.user}
        c.accept = AsyncMock()
        c.close = AsyncMock()
        await c.connect()
        c.close.assert_awaited()
        c.accept.assert_not_awaited()

    # ── receive: subscribe / message / validation ──────────────────────────────
    async def test_subscribe_returns_history_and_live(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from apps.siteconfig.models_feature_controls import GlobalSupportTicketReply as R

        await sync_to_async(R.objects.create)(
            ticket=self.ticket, author=self.user, body="hi there",
            visibility=R.Visibility.SUBMITTER_VISIBLE,
        )
        c = self._agent_ws()
        await c.receive(
            json.dumps({"action": "subscribe", "ticket_id": str(self.ticket.pk)})
        )
        frame = self._last_frame(c)
        self.assertEqual(frame["type"], "subscribed")
        self.assertEqual(frame["ticket_id"], str(self.ticket.pk))
        self.assertTrue(frame["live"])  # ticket has a live user
        self.assertTrue(any(h["body"] == "hi there" for h in frame["history"]))

    async def test_subscribe_unknown_ticket_errors(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        c = self._agent_ws()
        await c.receive(
            json.dumps({"action": "subscribe", "ticket_id": str(uuid.uuid4())})
        )
        self.assertEqual(self._last_frame(c).get("error"), "not_found")

    async def test_message_empty_errors_and_writes_nothing(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from apps.siteconfig.models_feature_controls import GlobalSupportTicketReply

        c = self._agent_ws()
        await c.receive(
            json.dumps(
                {"action": "message", "ticket_id": str(self.ticket.pk), "message": "   "}
            )
        )
        self.assertIn("error", self._last_frame(c))
        count = await sync_to_async(
            GlobalSupportTicketReply.objects.filter(ticket=self.ticket).count
        )()
        self.assertEqual(count, 0)

    async def test_message_unknown_ticket_errors(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        c = self._agent_ws()
        await c.receive(
            json.dumps(
                {"action": "message", "ticket_id": str(uuid.uuid4()), "message": "hello"}
            )
        )
        self.assertEqual(self._last_frame(c).get("error"), "not_found")

    async def test_invalid_json_errors(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        c = self._agent_ws()
        await c.receive("{not json")
        self.assertEqual(self._last_frame(c).get("error"), "Invalid JSON")

    async def test_unknown_action_errors(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        c = self._agent_ws()
        await c.receive(json.dumps({"action": "frobnicate"}))
        self.assertEqual(self._last_frame(c).get("error"), "unknown_action")

    # ── the live loop: agent message reaches the customer's room ───────────────
    async def test_agent_message_reaches_customer_room(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from channels.layers import InMemoryChannelLayer
        from apps.siteconfig.models_feature_controls import GlobalSupportTicketReply

        layer = InMemoryChannelLayer()
        room = support_chat_room_name(str(self.school.pk), str(self.user.pk))
        await layer.group_add(room, "customer.chan")

        agent = consumers.SupportAgentConsumer()
        agent.scope = {"user": self.operator}
        agent.user = self.operator
        agent.send = AsyncMock()
        agent.channel_layer = layer
        agent.channel_name = "agent.chan"
        agent.subscribed_room = None
        agent.subscribed_ticket_id = str(self.ticket.pk)

        await agent._handle_message(str(self.ticket.pk), "hello from support")

        ack = self._last_frame(agent)
        self.assertEqual(ack["type"], "ack")
        self.assertTrue(ack["reply_id"])

        reply = await sync_to_async(
            lambda: GlobalSupportTicketReply.objects.filter(
                ticket=self.ticket, author=self.operator
            ).first()
        )()
        self.assertIsNotNone(reply)
        self.assertEqual(reply.body, "hello from support")
        self.assertEqual(
            reply.visibility, GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
        )

        evt = await layer.receive("customer.chan")
        self.assertEqual(evt["type"], "chat.message")
        self.assertEqual(evt["sender_role"], "agent")
        self.assertEqual(evt["message"], "hello from support")

        # and the customer consumer delivers that event to the customer socket
        cust = consumers.SupportChatConsumer()
        cust.send = AsyncMock()
        await cust.chat_message(evt)
        delivered = json.loads(cust.send.await_args.kwargs["text_data"])
        self.assertEqual(delivered["type"], "chat_message")
        self.assertEqual(delivered["sender_role"], "agent")
        self.assertEqual(delivered["message"], "hello from support")

    # ── console view: gate + queue selection ────────────────────────────────────
    def test_view_denies_non_operator(self):
        from django.test import RequestFactory
        from apps.schools.super_views_support_live import super_support_live_console

        req = RequestFactory().get("/super/support/live/")
        req.user = self.user
        resp = super_support_live_console(req)
        self.assertEqual(resp.status_code, 403)

    def test_view_allows_operator_and_scopes_queue(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from apps.schools import super_views_support_live as mod
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        closed = GlobalSupportTicket.objects.create(
            school=self.school, user=self.user, subject="already closed",
            status=GlobalSupportTicket.Status.CLOSED,
        )
        userless = GlobalSupportTicket.objects.create(
            school=self.school, user=None, subject="no user",
            status=GlobalSupportTicket.Status.OPEN,
        )
        req = RequestFactory().get("/super/support/live/")
        req.user = self.operator
        with mock.patch.object(mod, "render") as m:
            m.return_value = HttpResponse("ok")
            resp = mod.super_support_live_console(req)
        self.assertEqual(resp.status_code, 200)
        args, _ = m.call_args
        self.assertEqual(args[1], "schools/super_support_live_console.html")
        ids = [t["id"] for t in args[2]["live_tickets"]]
        self.assertIn(str(self.ticket.pk), ids)
        self.assertNotIn(str(closed.pk), ids)      # closed excluded
        self.assertNotIn(str(userless.pk), ids)    # no-live-user excluded

    # ── routing ─────────────────────────────────────────────────────────────────
    def test_routing_registers_support_agent(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        import config.routing as routing

        patterns = [str(getattr(p, "pattern", "")) for p in routing.websocket_urlpatterns]
        self.assertTrue(any("support/agent" in p for p in patterns), patterns)
