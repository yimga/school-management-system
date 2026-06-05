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
    On message receive, calls services.ai_gateway.invoke("general_chat", ...) so all AI goes through the gateway.
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
            extra_md = {"country_code": extra_country} if extra_country else None
            outcome = invoke_with_request(
                task_type="general_chat",
                prompt=prompt,
                request=request,
                school=school,
                user_query=message,
                metadata=extra_md,
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
