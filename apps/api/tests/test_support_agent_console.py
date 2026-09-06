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
    load_customer_chat_history,
    load_support_ticket_for_agent,
    persist_support_agent_reply,
    set_support_ticket_status,
    support_chat_room_name,
)
from apps.schools.channels_tenant_middleware import tenant_sync_room_name
from apps.test_utils.seed_preserving import RestoresSeedCatalogMixin

User = get_user_model()


def _channels_ready() -> bool:
    return bool(getattr(consumers, "CHANNELS_AVAILABLE", False))


class SupportAgentConsoleTests(RestoresSeedCatalogMixin, TransactionTestCase):
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
        info = load_support_ticket_for_agent(self.operator, str(self.ticket.pk))
        bodies = [h["body"] for h in info["history"]]
        self.assertIn("help me", bodies)
        self.assertNotIn("secret note", bodies)
        customer_line = next(h for h in info["history"] if h["body"] == "help me")
        self.assertEqual(customer_line["sender_role"], "customer")
        self.assertEqual(info["school_id"], str(self.school.pk))
        self.assertEqual(info["user_id"], str(self.user.pk))

    def test_load_ticket_missing_returns_none(self):
        self.assertIsNone(load_support_ticket_for_agent(self.operator, str(uuid.uuid4())))

    # ── Wave 5: data-layer authorization (defense-in-depth) ─────────────────────
    def test_helpers_fail_closed_for_non_operator(self):
        """A non-operator identity (e.g. a tenant is_staff user, or a regression that
        bypassed the connect gate) gets None from every operator support helper —
        the authorization is enforced in the data layer, not only at connect."""
        from django.contrib.auth import get_user_model

        initial_status = self.ticket.status
        tenant_user = get_user_model()(
            username="tenant-admin-x", email="ta@example.com", is_staff=True
        )
        tenant_user.set_unusable_password()
        tenant_user.save()
        self.assertIsNone(
            load_support_ticket_for_agent(tenant_user, str(self.ticket.pk))
        )
        self.assertIsNone(
            persist_support_agent_reply(tenant_user, str(self.ticket.pk), "x")
        )
        self.assertIsNone(
            set_support_ticket_status(tenant_user, str(self.ticket.pk), "resolve")
        )
        # And the ticket was NOT mutated by the rejected calls.
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, initial_status)

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

    # ── completeness: customer history on connect ──────────────────────────────
    def test_customer_history_helper_scopes_and_excludes_internal(self):
        from apps.siteconfig.models_feature_controls import GlobalSupportTicketReply as R

        R.objects.create(
            ticket=self.ticket, author=self.user, body="my earlier line",
            visibility=R.Visibility.SUBMITTER_VISIBLE,
        )
        R.objects.create(
            ticket=self.ticket, author=self.operator, body="internal only",
            visibility=R.Visibility.INTERNAL,
        )
        history = load_customer_chat_history(self.user, self.school)
        bodies = [h["message"] for h in history]
        self.assertIn("my earlier line", bodies)
        self.assertNotIn("internal only", bodies)
        line = next(h for h in history if h["message"] == "my earlier line")
        self.assertEqual(line["sender_role"], "customer")

    def test_customer_history_empty_without_open_ticket(self):
        from apps.schools.models import School

        s = uuid4().hex[:8]
        lonely_school = School.objects.create(
            name="No Tickets", subdomain=f"nt-{s}", slug=f"nt-{s}", is_active=True,
        )
        self.assertEqual(load_customer_chat_history(self.user, lonely_school), [])

    async def test_customer_connect_sends_history(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from channels.layers import InMemoryChannelLayer
        from apps.siteconfig.models_feature_controls import GlobalSupportTicketReply as R

        await sync_to_async(R.objects.create)(
            ticket=self.ticket, author=self.user, body="earlier msg",
            visibility=R.Visibility.SUBMITTER_VISIBLE,
        )
        c = consumers.SupportChatConsumer()
        c.scope = {
            "user": self.user,
            "school": self.school,
            "school_id": str(self.school.pk),
            "school_access_denied": False,
        }
        c.channel_layer = InMemoryChannelLayer()
        c.channel_name = "cust.hist.chan"
        c.accept = AsyncMock()
        c.close = AsyncMock()
        c.send = AsyncMock()
        await c.connect()
        c.accept.assert_awaited()
        frames = [
            json.loads(call.kwargs["text_data"]) for call in c.send.await_args_list
        ]
        hist = [f for f in frames if f.get("type") == "history"]
        self.assertTrue(hist)
        self.assertTrue(any(m["message"] == "earlier msg" for m in hist[0]["messages"]))

    # ── completeness: live agent queue (presence group + activity) ─────────────
    async def test_customer_message_publishes_activity(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from channels.layers import InMemoryChannelLayer

        layer = InMemoryChannelLayer()
        await layer.group_add(consumers._SUPPORT_AGENTS_GROUP, "console.chan")
        c = consumers.SupportChatConsumer()
        c.scope = {
            "user": self.user,
            "school": self.school,
            "school_id": str(self.school.pk),
            "school_access_denied": False,
        }
        c.user = self.user
        c.channel_layer = layer
        c.room_group_name = support_chat_room_name(
            str(self.school.pk), str(self.user.pk)
        )
        c.send = AsyncMock()
        await c.receive(json.dumps({"message": "please help"}))
        evt = await layer.receive("console.chan")
        self.assertEqual(evt["type"], "support.activity")
        self.assertEqual(evt["preview"], "please help")
        self.assertEqual(evt["sender_role"], "customer")
        self.assertTrue(evt["ticket_id"])

    async def test_agent_joins_presence_and_forwards_activity(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from channels.layers import InMemoryChannelLayer

        layer = InMemoryChannelLayer()
        agent = consumers.SupportAgentConsumer()
        agent.scope = {"user": self.operator}
        agent.channel_layer = layer
        agent.channel_name = "agent.presence.chan"
        agent.accept = AsyncMock()
        agent.close = AsyncMock()
        agent.send = AsyncMock()
        await agent.connect()
        agent.accept.assert_awaited()
        # a customer-activity broadcast reaches this agent's channel...
        await layer.group_send(
            consumers._SUPPORT_AGENTS_GROUP,
            {
                "type": "support.activity",
                "ticket_id": "t-1",
                "school_name": "S",
                "user_display": "U",
                "preview": "hi",
                "sender_role": "customer",
            },
        )
        evt = await layer.receive("agent.presence.chan")
        self.assertEqual(evt["type"], "support.activity")
        # ...and the handler forwards it to the socket as an "activity" frame
        await agent.support_activity(evt)
        frame = self._last_frame(agent)
        self.assertEqual(frame["type"], "activity")
        self.assertEqual(frame["ticket_id"], "t-1")
        self.assertEqual(frame["preview"], "hi")

    # ── completeness: resolve / reopen from the console ─────────────────────────
    def test_set_status_resolve_then_reopen(self):
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        r = set_support_ticket_status(self.operator, str(self.ticket.pk), "resolve")
        self.assertEqual(r["status"], GlobalSupportTicket.Status.RESOLVED)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, GlobalSupportTicket.Status.RESOLVED)
        r2 = set_support_ticket_status(self.operator, str(self.ticket.pk), "reopen")
        self.assertEqual(r2["status"], GlobalSupportTicket.Status.OPEN)

    def test_set_status_invalid_transition_is_rejected(self):
        from apps.siteconfig.models_feature_controls import GlobalSupportTicket

        self.ticket.status = GlobalSupportTicket.Status.CLOSED
        self.ticket.save(update_fields=["status"])
        r = set_support_ticket_status(self.operator, str(self.ticket.pk), "resolve")
        self.assertEqual(r.get("error"), "invalid_transition")
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, GlobalSupportTicket.Status.CLOSED)

    async def test_agent_resolve_acks_and_notifies_customer_room(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from channels.layers import InMemoryChannelLayer

        layer = InMemoryChannelLayer()
        room = support_chat_room_name(str(self.school.pk), str(self.user.pk))
        await layer.group_add(room, "cust.sys.chan")
        agent = consumers.SupportAgentConsumer()
        agent.scope = {"user": self.operator}
        agent.user = self.operator
        agent.channel_layer = layer
        agent.channel_name = "agent.resolve.chan"
        agent.subscribed_room = None
        agent.subscribed_ticket_id = None
        agent.send = AsyncMock()
        await agent._handle_status(str(self.ticket.pk), "resolve")
        frame = self._last_frame(agent)
        self.assertEqual(frame["type"], "status")
        self.assertEqual(frame["status"], "RESOLVED")
        evt = await layer.receive("cust.sys.chan")
        self.assertEqual(evt["sender_role"], "system")
        self.assertEqual(evt["system"], "resolve")

    # ── gold-plating: typing indicators + read receipts (ephemeral presence) ────
    def _customer_ws(self, layer, room):
        c = consumers.SupportChatConsumer()
        c.scope = {
            "user": self.user,
            "school": self.school,
            "school_id": str(self.school.pk),
            "school_access_denied": False,
        }
        c.user = self.user
        c.channel_layer = layer
        c.room_group_name = room
        c.send = AsyncMock()
        return c

    async def test_customer_typing_relays_to_private_room(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from channels.layers import InMemoryChannelLayer

        layer = InMemoryChannelLayer()
        room = support_chat_room_name(str(self.school.pk), str(self.user.pk))
        await layer.group_add(room, "op.typing.chan")
        c = self._customer_ws(layer, room)
        await c.receive(json.dumps({"action": "typing"}))
        # ephemeral: nothing is echoed back to the sender
        c.send.assert_not_awaited()
        evt = await layer.receive("op.typing.chan")
        self.assertEqual(evt["type"], "presence.signal")
        self.assertEqual(evt["kind"], "typing")
        self.assertEqual(evt["sender_role"], "customer")

    async def test_customer_presence_writes_no_ticket_or_reply(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from asgiref.sync import sync_to_async
        from channels.layers import InMemoryChannelLayer
        from apps.siteconfig.models_feature_controls import (
            GlobalSupportTicket,
            GlobalSupportTicketReply,
        )

        before_t = await sync_to_async(GlobalSupportTicket.objects.count)()
        before_r = await sync_to_async(GlobalSupportTicketReply.objects.count)()
        layer = InMemoryChannelLayer()
        room = support_chat_room_name(str(self.school.pk), str(self.user.pk))
        c = self._customer_ws(layer, room)
        await c.receive(json.dumps({"action": "read"}))
        after_t = await sync_to_async(GlobalSupportTicket.objects.count)()
        after_r = await sync_to_async(GlobalSupportTicketReply.objects.count)()
        self.assertEqual((before_t, before_r), (after_t, after_r))

    async def test_agent_typing_relays_to_subscribed_room(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from channels.layers import InMemoryChannelLayer

        layer = InMemoryChannelLayer()
        room = support_chat_room_name(str(self.school.pk), str(self.user.pk))
        await layer.group_add(room, "cust.typing.chan")
        agent = self._agent_ws()
        agent.channel_layer = layer
        agent.subscribed_room = room
        agent.subscribed_ticket_id = str(self.ticket.pk)
        await agent.receive(
            json.dumps({"action": "typing", "ticket_id": str(self.ticket.pk)})
        )
        agent.send.assert_not_awaited()
        evt = await layer.receive("cust.typing.chan")
        self.assertEqual(evt["type"], "presence.signal")
        self.assertEqual(evt["kind"], "typing")
        self.assertEqual(evt["sender_role"], "agent")
        self.assertEqual(evt["ticket_id"], str(self.ticket.pk))

    async def test_agent_presence_without_subscription_is_noop(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        # No subscribed_room → the signal is dropped, no crash, no frame.
        c = self._agent_ws()
        await c.receive(
            json.dumps({"action": "read", "ticket_id": str(self.ticket.pk)})
        )
        c.send.assert_not_awaited()

    async def test_presence_signal_handler_forwards_on_both_sides(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        cust = consumers.SupportChatConsumer()
        cust.send = AsyncMock()
        await cust.presence_signal(
            {"kind": "read", "sender_role": "agent", "ticket_id": ""}
        )
        f1 = json.loads(cust.send.await_args.kwargs["text_data"])
        self.assertEqual(f1["type"], "read")
        self.assertEqual(f1["sender_role"], "agent")

        agent = consumers.SupportAgentConsumer()
        agent.send = AsyncMock()
        await agent.presence_signal(
            {"kind": "typing", "sender_role": "customer", "ticket_id": "t9"}
        )
        f2 = json.loads(agent.send.await_args.kwargs["text_data"])
        self.assertEqual(f2["type"], "typing")
        self.assertEqual(f2["sender_role"], "customer")
        self.assertEqual(f2["ticket_id"], "t9")

    async def test_customer_typing_reaches_operator_socket_end_to_end(self):
        if not _channels_ready():
            self.skipTest("channels not available")
        from channels.layers import InMemoryChannelLayer

        layer = InMemoryChannelLayer()
        room = support_chat_room_name(str(self.school.pk), str(self.user.pk))
        # an operator subscribed to this ticket's room
        await layer.group_add(room, "op.e2e.chan")
        cust = self._customer_ws(layer, room)
        await cust.receive(json.dumps({"action": "typing"}))
        evt = await layer.receive("op.e2e.chan")
        agent = consumers.SupportAgentConsumer()
        agent.send = AsyncMock()
        await agent.presence_signal(evt)
        frame = json.loads(agent.send.await_args.kwargs["text_data"])
        self.assertEqual(frame["type"], "typing")
        self.assertEqual(frame["sender_role"], "customer")
