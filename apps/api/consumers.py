"""
WebSocket Consumers for Real-Time Sync
Provides real-time updates for students, teachers, and classrooms

Requires: pip install channels channels-redis
"""

import json

# Try to import channels, fallback gracefully if not installed
try:
    from channels.generic.websocket import AsyncWebsocketConsumer

    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False

    # Create dummy classes for when channels is not installed
    class AsyncWebsocketConsumer:
        pass


from django.contrib.auth import get_user_model

from apps.schools.channels_tenant_middleware import tenant_sync_room_name

User = get_user_model()


class _TenantScopedSyncConsumer(AsyncWebsocketConsumer):
    """Base consumer: requires host-bound tenant from TenantChannelsMiddleware."""

    room_prefix = "sync"

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not getattr(self.user, "is_authenticated", False):
            await self.close(code=4401)
            return

        self.room_group_name = tenant_sync_room_name(self.room_prefix, self.scope)
        if not self.room_group_name:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, "room_group_name", None):
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )


class StudentSyncConsumer(_TenantScopedSyncConsumer):
    """WebSocket consumer for student data synchronization"""

    room_prefix = "students_sync"

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        await self.send(text_data=json.dumps({"message": f"Received: {message}"}))

    async def student_update(self, event):
        message = event["message"]
        await self.send(
            text_data=json.dumps({"type": "student_update", "message": message})
        )


class TeacherSyncConsumer(_TenantScopedSyncConsumer):
    """WebSocket consumer for teacher data synchronization"""

    room_prefix = "teachers_sync"

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        await self.send(text_data=json.dumps({"message": f"Received: {message}"}))

    async def teacher_update(self, event):
        message = event["message"]
        await self.send(
            text_data=json.dumps({"type": "teacher_update", "message": message})
        )


class ClassroomSyncConsumer(_TenantScopedSyncConsumer):
    """WebSocket consumer for classroom data synchronization"""

    room_prefix = "classrooms_sync"

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        await self.send(text_data=json.dumps({"message": f"Received: {message}"}))

    async def classroom_update(self, event):
        message = event["message"]
        await self.send(
            text_data=json.dumps({"type": "classroom_update", "message": message})
        )


class AIChatConsumer(AsyncWebsocketConsumer):
    """
    World Engine B.3: Real-time AI chat over WebSocket.
    On message receive, calls services.ai_helpers.invoke_with_request (RBAC guard + gateway).
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not getattr(self.user, "is_authenticated", False):
            await self.close(code=4401)
            return
        if self.scope.get("school_access_denied") or not self.scope.get("school"):
            await self.close(code=4403)
            return
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data) if text_data else {}
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return
        message = (payload.get("message") or payload.get("text") or "").strip()
        if not message:
            await self.send(text_data=json.dumps({"error": "message required"}))
            return
        from asgiref.sync import sync_to_async
        from services.ai_helpers import invoke_with_request

        request = self.scope.get("request", None)
        school = self.scope.get("school") or getattr(request, "school", None)
        extra_country = payload.get("country_code")
        prompt = (
            "You are a helpful assistant for the school platform. Answer concisely.\n\nUser: "
            + message
        )

        def _gateway_infer():
            from services.ai_copilot_rbac import copilot_request_shim, guard_copilot_invoke

            rbac_request = request
            if self.user is not None and (
                rbac_request is None
                or getattr(rbac_request, "user", None) is None
            ):
                rbac_request = copilot_request_shim(
                    user=self.user,
                    school=school
                    or (
                        getattr(rbac_request, "school", None)
                        if rbac_request is not None
                        else None
                    ),
                    active_url=(
                        str(getattr(rbac_request, "path", "") or "")
                        if rbac_request is not None
                        else ""
                    ),
                    host_kind=(
                        getattr(rbac_request, "public_host_kind", None)
                        if rbac_request is not None
                        else None
                    ),
                )

            extra_md: dict = {"surface": "websocket_general_chat"}
            if extra_country:
                extra_md["country_code"] = extra_country
            guard = guard_copilot_invoke(
                request=rbac_request,
                task_type="general_chat",
                prompt=prompt,
                user_query=message,
                metadata=extra_md,
            )
            if not guard.allowed:
                return None, guard.metadata, guard.denial_reason or "permission_denied"
            outcome = invoke_with_request(
                task_type="general_chat",
                prompt=guard.prompt,
                request=rbac_request,
                school=school,
                user_query=message,
                metadata=guard.metadata,
                require_available=False,
            )
            if outcome is None:
                return None, {"provider": "none", "error": "unavailable"}, "unavailable"
            result, meta = outcome
            error = None
            if meta.get("prompt_injection_blocked"):
                error = "Request rejected by safety policy. Please rephrase as a normal school-operation question."
            elif meta.get("budget_exceeded"):
                error = "AI request budget exceeded for this tenant."
            elif meta.get("provider") == "none":
                error = (
                    result
                    if isinstance(result, str) and result.strip()
                    else meta.get("error", "unavailable")
                )
            text = (
                result
                if isinstance(result, str) and not error
                else (str(result) if result is not None and not error else None)
            )
            return text, meta, error

        try:
            text, meta, error = await sync_to_async(_gateway_infer)()
        except (TypeError, ValueError, RuntimeError, OSError):
            await self.send(
                text_data=json.dumps({"reply": "", "error": "unavailable"})
            )
            return
        if error:
            await self.send(
                text_data=json.dumps({"reply": "", "error": error})
            )
        elif text is None:
            await self.send(
                text_data=json.dumps({"reply": "", "error": meta.get("error", "unavailable")})
            )
        else:
            await self.send(text_data=json.dumps({"reply": text, "meta": meta}))


# ── Wave 7.4 follow-up: human support live-chat ──────────────────────────────
_SUPPORT_CHAT_MAX_CHARS = 4000  # magic-number-allow: support-chat-message-cap-chars


def persist_support_chat_message(user, school, body):
    """Record an inbound live-chat line as a submitter-visible reply on the user's
    open support ticket (creating one if none is open). Returns (ticket_id,
    reply_id) as strings. Pure ORM — safe under ``sync_to_async``. The ticket is
    the same ``GlobalSupportTicket`` the Owner Console Support section surfaces, so
    a chat and a raised ticket are one record, not two systems.
    """
    from apps.siteconfig.models_feature_controls import (
        GlobalSupportTicket,
        GlobalSupportTicketReply,
    )

    open_statuses = [
        GlobalSupportTicket.Status.OPEN,
        GlobalSupportTicket.Status.IN_PROGRESS,
        GlobalSupportTicket.Status.WAITING,
    ]
    ticket = (
        GlobalSupportTicket.objects.filter(
            school=school, user=user, status__in=open_statuses
        )
        .order_by("-created_at")
        .first()
    )
    if ticket is None:
        ticket = GlobalSupportTicket.objects.create(
            school=school,
            user=user,
            subject="Live chat",
            status=GlobalSupportTicket.Status.OPEN,
            metadata={"channel": "live_chat"},
        )
    reply = GlobalSupportTicketReply.objects.create(
        ticket=ticket,
        author=user,
        body=body,
        visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE,
    )
    return str(ticket.pk), str(reply.pk)


# Platform-wide presence group: every connected operator console joins it so a
# new customer message can surface live in their queue. Only SupportAgentConsumer
# (operator-gated) ever JOINS it; SupportChatConsumer only publishes to it, so a
# tenant user never receives another tenant's activity.
_SUPPORT_AGENTS_GROUP = "support_agents"
_SUPPORT_ACTIVITY_PREVIEW_CHARS = 120  # magic-number-allow: support-activity-queue-preview-cap
_SUPPORT_CHAT_HISTORY_LIMIT = 40  # magic-number-allow: support-chat-history-frame-cap


def _support_user_display(user):
    """Short human label for a support participant (name, else username)."""
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or (getattr(user, "get_username", lambda: "")() or "")


def load_customer_chat_history(user, school):
    """Recent submitter-visible lines on the customer's OWN open ticket, oldest
    first, for the widget to render on connect. Returns [] if no open ticket.
    Pure ORM — safe under ``sync_to_async``. Scoped by school AND user, so a
    customer only ever sees their own conversation.
    """
    from apps.siteconfig.models_feature_controls import (
        GlobalSupportTicket,
        GlobalSupportTicketReply,
    )

    open_statuses = [
        GlobalSupportTicket.Status.OPEN,
        GlobalSupportTicket.Status.IN_PROGRESS,
        GlobalSupportTicket.Status.WAITING,
    ]
    ticket = (
        GlobalSupportTicket.objects.filter(
            school=school, user=user, status__in=open_statuses
        )
        .order_by("-created_at")
        .first()
    )
    if ticket is None:
        return []
    recent = list(
        ticket.thread_replies.filter(
            visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
        ).order_by("-created_at")[:_SUPPORT_CHAT_HISTORY_LIMIT]
    )
    recent.reverse()
    return [
        {
            "message": r.body,
            "created_at": r.created_at.isoformat(),
            "sender_role": (
                "customer" if (r.author_id and r.author_id == user.pk) else "agent"
            ),
        }
        for r in recent
    ]


class SupportChatConsumer(_TenantScopedSyncConsumer):
    """Human support live-chat over WebSocket (the deferred Wave 7.4 slice).

    Extends the tenant-scoped base, so the channel group is ``support_chat`` keyed
    on ``(school, user)`` — one customer's chat is private and never reaches another
    tenant or another user. Each inbound line is persisted as a submitter-visible
    reply on the user's open support ticket, then best-effort broadcast to the
    private room so a connected agent console (a later slice) sees it live. It is
    auth-required + tenant-bound via ``TenantChannelsMiddleware`` (inherited) and
    fail-soft: a write error returns an error frame, never drops the socket.
    """

    room_prefix = "support_chat"

    async def connect(self):
        # Base binds the private (school, user) room and accepts (or closes).
        await super().connect()
        if not getattr(self, "room_group_name", None):
            return
        school = self.scope.get("school")
        if school is None:
            return
        from asgiref.sync import sync_to_async

        try:
            history = await sync_to_async(load_customer_chat_history)(self.user, school)
        except Exception:  # noqa: BLE001 — history is best-effort, never block the socket
            history = []
        if history:
            await self.send(
                text_data=json.dumps({"type": "history", "messages": history})
            )

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data) if text_data else {}
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return
        action = (
            (payload.get("action") or "").strip().lower()
            if isinstance(payload, dict)
            else ""
        )
        if action in ("typing", "read"):
            # Ephemeral presence signal — DB-free, room-scoped, no ack frame.
            await self._relay_presence(action)
            return
        message = (payload.get("message") or payload.get("text") or "").strip()
        if not message:
            await self.send(text_data=json.dumps({"error": "message required"}))
            return
        message = message[:_SUPPORT_CHAT_MAX_CHARS]

        school = self.scope.get("school")
        if school is None:
            await self.send(text_data=json.dumps({"error": "no_school"}))
            return

        from asgiref.sync import sync_to_async

        try:
            ticket_id, reply_id = await sync_to_async(persist_support_chat_message)(
                self.user, school, message
            )
        except Exception:  # noqa: BLE001 — never drop the socket on a write error
            await self.send(text_data=json.dumps({"error": "unavailable"}))
            return

        # Best-effort live fan-out to the private (school, user) room.
        if getattr(self, "channel_layer", None) and getattr(self, "room_group_name", None):
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.message",
                    "message": message,
                    "ticket_id": ticket_id,
                    "author_id": getattr(self.user, "pk", None),
                    "sender_role": "customer",
                },
            )
        # Surface the new activity to every connected operator console.
        if getattr(self, "channel_layer", None):
            await self.channel_layer.group_send(
                _SUPPORT_AGENTS_GROUP,
                {
                    "type": "support.activity",
                    "ticket_id": ticket_id,
                    "school_name": getattr(school, "name", "") or "",
                    "user_display": _support_user_display(self.user),
                    "preview": message[:_SUPPORT_ACTIVITY_PREVIEW_CHARS],
                    "sender_role": "customer",
                },
            )
        await self.send(
            text_data=json.dumps(
                {"type": "ack", "ticket_id": ticket_id, "reply_id": reply_id}
            )
        )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat_message",
                    "message": event.get("message", ""),
                    "ticket_id": event.get("ticket_id", ""),
                    "author_id": event.get("author_id"),
                    "sender_role": event.get("sender_role", ""),
                    "system": event.get("system", ""),
                }
            )
        )

    async def _relay_presence(self, kind):
        """Fan an ephemeral ``typing`` / ``read`` signal into this customer's
        private (school, user) room so a subscribed operator console sees it.
        DB-free and room-scoped — never published to the platform-wide operator
        group, so it can never reach another tenant. The customer's own echo is
        filtered client-side by ``sender_role``.
        """
        if not getattr(self, "channel_layer", None) or not getattr(
            self, "room_group_name", None
        ):
            return
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "presence.signal",
                "kind": kind,
                "sender_role": "customer",
                "ticket_id": "",
            },
        )

    async def presence_signal(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": event.get("kind", ""),
                    "sender_role": event.get("sender_role", ""),
                    "ticket_id": event.get("ticket_id", ""),
                }
            )
        )


# ── Wave 7.4 follow-up: operator ("agent-side") support live-chat ─────────────
# The operator half of the support live-chat loop. A platform support agent
# connects from the manager host, where TenantChannelsMiddleware leaves the scope
# with school_access_denied=True (no tenant bind) — so this consumer is NOT
# tenant-room bound like SupportChatConsumer. It is gated on the *operator
# identity* of the connecting user and joins the private (school, user) room
# derived from whichever ticket the agent subscribes to. That room name is
# computed server-side from the DB ticket, never from client input, so an
# operator can only ever reach a real ticket's room.
_SUPPORT_AGENT_HISTORY_LIMIT = 40  # magic-number-allow: agent-console-history-frame-cap


def support_chat_room_name(school_id, user_id):
    """The private support-chat channel group for one (school, user).

    Must stay byte-identical to ``tenant_sync_room_name("support_chat", scope)``
    (apps/schools/channels_tenant_middleware.py) so the operator's broadcast lands
    in the exact room the customer's ``SupportChatConsumer`` is listening on.
    Locked by ``test_support_agent_console.test_room_formula_matches_customer``.
    """
    return f"support_chat_{school_id}_{user_id}"


def agent_console_access(user) -> bool:
    """True iff ``user`` may operate the live support console.

    Mirrors ``require_platform_scope(PLATFORM_SCOPE_TEAM_READ)`` — control-plane
    access AND the team.read scope — so the WebSocket gate is exactly the HTTP
    view gate. Deliberately NOT Django ``is_staff``: tenant staff must never reach
    an operator surface. Superuser passes. Fail-closed on any import/attribute
    error (the underlying control-plane helpers already swallow DB errors).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        from apps.platform_runtime.operator_identity import (
            PLATFORM_SCOPE_TEAM_READ,
            user_has_platform_scope,
        )
        from apps.schools.control_plane import user_has_control_plane_access
    except ImportError:
        return False
    try:
        if not user_has_control_plane_access(user):
            return False
        return user_has_platform_scope(user, PLATFORM_SCOPE_TEAM_READ)
    except (AttributeError, TypeError, ValueError):
        return False


def persist_support_agent_reply(agent_user, ticket_id, body):
    """Record an operator's live-chat line as a submitter-visible reply on the
    customer's ticket, advance SLA / assignment / status, and return the routing
    fields needed to fan the message out to the customer's private room.

    Returns ``{reply_id, ticket_id, school_id, user_id}`` (strings; ``user_id`` is
    None for a userless ticket) or None if the ticket no longer exists. Pure ORM —
    safe under ``sync_to_async``. Does NOT run ``run_support_ticket_reply_hooks``:
    a live chat line is delivered over the socket, and firing per-line
    email/webhook notifications would spam the customer. The persisted reply still
    surfaces on the ticket for offline recall.
    """
    from django.utils import timezone

    from apps.siteconfig import support_fsm
    from apps.siteconfig.models_feature_controls import (
        GlobalSupportTicket,
        GlobalSupportTicketReply,
    )

    ticket = (
        GlobalSupportTicket.objects.select_related("school", "user")
        .filter(pk=ticket_id)
        .first()
    )
    if ticket is None:
        return None
    reply = GlobalSupportTicketReply.objects.create(
        ticket=ticket,
        author=agent_user,
        body=body,
        visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE,
    )
    changed = []
    if ticket.first_response_at is None:
        ticket.first_response_at = timezone.now()
        changed.append("first_response_at")
    if ticket.assigned_to_id is None:
        ticket.assigned_to = agent_user
        changed.append("assigned_to")
    if ticket.status == GlobalSupportTicket.Status.OPEN and support_fsm.can_transition(
        ticket.status, GlobalSupportTicket.Status.IN_PROGRESS
    ):
        ticket.status = GlobalSupportTicket.Status.IN_PROGRESS
        changed.append("status")
    if changed:
        changed.append("updated_at")
        ticket.save(update_fields=changed)
    return {
        "reply_id": str(reply.pk),
        "ticket_id": str(ticket.pk),
        "school_id": str(ticket.school_id),
        "user_id": str(ticket.user_id) if ticket.user_id else None,
    }


def load_support_ticket_for_agent(ticket_id):
    """Context for the operator console when it subscribes to a ticket.

    Returns ``{ticket_id, school_id, user_id, subject, status, school_name,
    history[]}`` or None if the ticket is gone. History is the last N
    submitter-visible lines — the shared customer/agent conversation, oldest
    first. Internal operator notes are excluded; they live on the ticket detail
    page, not the live pane. Pure ORM — safe under ``sync_to_async``.
    """
    from apps.siteconfig.models_feature_controls import (
        GlobalSupportTicket,
        GlobalSupportTicketReply,
    )

    ticket = (
        GlobalSupportTicket.objects.select_related("school", "user")
        .filter(pk=ticket_id)
        .first()
    )
    if ticket is None:
        return None
    recent = list(
        ticket.thread_replies.filter(
            visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
        ).order_by("-created_at")[:_SUPPORT_AGENT_HISTORY_LIMIT]
    )
    recent.reverse()
    history = [
        {
            "body": r.body,
            "author_id": r.author_id,
            "created_at": r.created_at.isoformat(),
            "sender_role": (
                "customer"
                if (r.author_id and r.author_id == ticket.user_id)
                else "agent"
            ),
        }
        for r in recent
    ]
    return {
        "ticket_id": str(ticket.pk),
        "school_id": str(ticket.school_id),
        "user_id": str(ticket.user_id) if ticket.user_id else None,
        "subject": ticket.subject,
        "status": ticket.status,
        "school_name": getattr(ticket.school, "name", "") or "",
        "history": history,
    }


def set_support_ticket_status(agent_user, ticket_id, action):
    """Resolve or reopen a ticket from the console via the support FSM.

    ``action`` is "resolve" (→ RESOLVED) or "reopen" (→ OPEN). Returns
    ``{ticket_id, status, school_id, user_id}`` on success, ``{"error":
    "invalid_transition", "status": <current>}`` if the FSM forbids the move, or
    None if the ticket is gone. Pure ORM — safe under ``sync_to_async``.
    """
    from apps.siteconfig import support_fsm
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    target = (
        GlobalSupportTicket.Status.RESOLVED
        if action == "resolve"
        else GlobalSupportTicket.Status.OPEN
    )
    ticket = (
        GlobalSupportTicket.objects.select_related("school", "user")
        .filter(pk=ticket_id)
        .first()
    )
    if ticket is None:
        return None
    if not support_fsm.can_transition(ticket.status, target):
        return {"error": "invalid_transition", "status": ticket.status}
    changed = ["status", "updated_at"]
    ticket.status = target
    if ticket.assigned_to_id is None:
        ticket.assigned_to = agent_user
        changed.append("assigned_to")
    ticket.save(update_fields=changed)
    # Audit parity with the ticket-detail status branch (best-effort).
    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "support_desk_ticket_updated",
            {
                "ticket_id": str(ticket.pk),
                "school_id": str(ticket.school_id),
                "actor_id": getattr(agent_user, "id", None),
                "changed_fields": changed,
                "source": "live_console",
            },
            school_id=ticket.school_id,
        )
    except (AttributeError, ImportError, LookupError, TypeError, ValueError):
        pass
    return {
        "ticket_id": str(ticket.pk),
        "status": ticket.status,
        "school_id": str(ticket.school_id),
        "user_id": str(ticket.user_id) if ticket.user_id else None,
    }


class SupportAgentConsumer(AsyncWebsocketConsumer):
    """Operator-side live support chat (the /super/ half of the loop).

    Not tenant-room bound (see the module note above): gated on operator identity,
    joins the private room derived from whichever ticket the agent subscribes to,
    and posts submitter-visible replies that fan out to the customer's
    ``SupportChatConsumer``. Auth + operator-gated on connect; fail-soft on every
    write; message capped at ``_SUPPORT_CHAT_MAX_CHARS``.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        self.subscribed_room = None
        self.subscribed_ticket_id = None
        if not self.user or not getattr(self.user, "is_authenticated", False):
            await self.close(code=4401)  # magic-number-allow: websocket-close-code-unauthorized
            return
        from asgiref.sync import sync_to_async

        try:
            allowed = await sync_to_async(agent_console_access)(self.user)
        except (AttributeError, TypeError, ValueError):
            allowed = False
        if not allowed:
            await self.close(code=4403)  # magic-number-allow: websocket-close-code-forbidden
            return
        await self.accept()
        # Join the platform-wide operator presence group so a new customer chat
        # surfaces live in the queue without a page reload.
        channel_layer = getattr(self, "channel_layer", None)
        if channel_layer is not None:
            await channel_layer.group_add(_SUPPORT_AGENTS_GROUP, self.channel_name)

    async def disconnect(self, close_code):
        channel_layer = getattr(self, "channel_layer", None)
        if channel_layer is None:
            return
        if getattr(self, "subscribed_room", None):
            await channel_layer.group_discard(self.subscribed_room, self.channel_name)
        await channel_layer.group_discard(_SUPPORT_AGENTS_GROUP, self.channel_name)

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data) if text_data else {}
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
            return
        if not isinstance(payload, dict):
            await self.send(text_data=json.dumps({"error": "bad_payload"}))
            return
        action = (payload.get("action") or "").strip().lower()
        ticket_id = (payload.get("ticket_id") or "").strip()
        if action == "subscribe":
            await self._handle_subscribe(ticket_id)
        elif action == "message":
            message = payload.get("message") or payload.get("text") or ""
            await self._handle_message(ticket_id, message)
        elif action in ("resolve", "reopen"):
            await self._handle_status(ticket_id, action)
        elif action in ("typing", "read"):
            # Ephemeral presence into the subscribed customer room — no ack.
            await self._relay_presence(action)
        else:
            await self.send(text_data=json.dumps({"error": "unknown_action"}))

    async def _handle_subscribe(self, ticket_id):
        if not ticket_id:
            await self.send(text_data=json.dumps({"error": "ticket_required"}))
            return
        from asgiref.sync import sync_to_async

        try:
            info = await sync_to_async(load_support_ticket_for_agent)(ticket_id)
        except Exception:  # noqa: BLE001 — never drop the socket on a read error
            await self.send(text_data=json.dumps({"error": "unavailable"}))
            return
        if info is None:
            await self.send(text_data=json.dumps({"error": "not_found"}))
            return
        # Re-key the subscription to this ticket's private room.
        channel_layer = getattr(self, "channel_layer", None)
        if channel_layer is not None and self.subscribed_room:
            await channel_layer.group_discard(self.subscribed_room, self.channel_name)
        self.subscribed_room = None
        self.subscribed_ticket_id = info["ticket_id"]
        if info["user_id"] and channel_layer is not None:
            room = support_chat_room_name(info["school_id"], info["user_id"])
            await channel_layer.group_add(room, self.channel_name)
            self.subscribed_room = room
        await self.send(
            text_data=json.dumps(
                {
                    "type": "subscribed",
                    "ticket_id": info["ticket_id"],
                    "subject": info["subject"],
                    "status": info["status"],
                    "school_name": info["school_name"],
                    "live": bool(self.subscribed_room),
                    "history": info["history"],
                }
            )
        )

    async def _handle_message(self, ticket_id, raw_message):
        message = (raw_message or "").strip()
        if not message:
            await self.send(text_data=json.dumps({"error": "message required"}))
            return
        if not ticket_id:
            await self.send(text_data=json.dumps({"error": "ticket_required"}))
            return
        message = message[:_SUPPORT_CHAT_MAX_CHARS]

        from asgiref.sync import sync_to_async

        try:
            result = await sync_to_async(persist_support_agent_reply)(
                self.user, ticket_id, message
            )
        except Exception:  # noqa: BLE001 — never drop the socket on a write error
            await self.send(text_data=json.dumps({"error": "unavailable"}))
            return
        if result is None:
            await self.send(text_data=json.dumps({"error": "not_found"}))
            return

        # Fan out to the customer's private (school, user) room so their
        # SupportChatConsumer delivers it live. Room derived from the DB ticket.
        channel_layer = getattr(self, "channel_layer", None)
        if result["user_id"] and channel_layer is not None:
            room = support_chat_room_name(result["school_id"], result["user_id"])
            await channel_layer.group_send(
                room,
                {
                    "type": "chat.message",
                    "message": message,
                    "ticket_id": result["ticket_id"],
                    "author_id": getattr(self.user, "pk", None),
                    "sender_role": "agent",
                },
            )
        await self.send(
            text_data=json.dumps(
                {
                    "type": "ack",
                    "ticket_id": result["ticket_id"],
                    "reply_id": result["reply_id"],
                }
            )
        )

    async def _handle_status(self, ticket_id, action):
        if not ticket_id:
            await self.send(text_data=json.dumps({"error": "ticket_required"}))
            return
        from asgiref.sync import sync_to_async

        try:
            result = await sync_to_async(set_support_ticket_status)(
                self.user, ticket_id, action
            )
        except Exception:  # noqa: BLE001 — never drop the socket on a write error
            await self.send(text_data=json.dumps({"error": "unavailable"}))
            return
        if result is None:
            await self.send(text_data=json.dumps({"error": "not_found"}))
            return
        if result.get("error"):
            await self.send(
                text_data=json.dumps(
                    {"error": result["error"], "status": result.get("status")}
                )
            )
            return
        # Let the customer see the state change as a system note in their room.
        channel_layer = getattr(self, "channel_layer", None)
        if result.get("user_id") and channel_layer is not None:
            await channel_layer.group_send(
                support_chat_room_name(result["school_id"], result["user_id"]),
                {
                    "type": "chat.message",
                    "message": "",
                    "ticket_id": result["ticket_id"],
                    "author_id": None,
                    "sender_role": "system",
                    "system": action,
                },
            )
        await self.send(
            text_data=json.dumps(
                {
                    "type": "status",
                    "ticket_id": result["ticket_id"],
                    "status": result["status"],
                }
            )
        )

    async def _relay_presence(self, kind):
        """Fan an ephemeral ``typing`` / ``read`` signal into the customer's
        currently-subscribed room. Uses the already-bound ``subscribed_room`` (no
        DB hit), so an operator can only signal into a ticket it has actively
        subscribed to — never an arbitrary tenant's room.
        """
        channel_layer = getattr(self, "channel_layer", None)
        room = getattr(self, "subscribed_room", None)
        if channel_layer is None or not room:
            return
        await channel_layer.group_send(
            room,
            {
                "type": "presence.signal",
                "kind": kind,
                "sender_role": "agent",
                "ticket_id": getattr(self, "subscribed_ticket_id", "") or "",
            },
        )

    async def support_activity(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "activity",
                    "ticket_id": event.get("ticket_id", ""),
                    "school_name": event.get("school_name", ""),
                    "user_display": event.get("user_display", ""),
                    "preview": event.get("preview", ""),
                    "sender_role": event.get("sender_role", ""),
                }
            )
        )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat_message",
                    "message": event.get("message", ""),
                    "ticket_id": event.get("ticket_id", ""),
                    "author_id": event.get("author_id"),
                    "sender_role": event.get("sender_role", ""),
                    "system": event.get("system", ""),
                }
            )
        )

    async def presence_signal(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": event.get("kind", ""),
                    "sender_role": event.get("sender_role", ""),
                    "ticket_id": event.get("ticket_id", ""),
                }
            )
        )
