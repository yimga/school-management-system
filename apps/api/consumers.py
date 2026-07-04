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
                }
            )
        )
