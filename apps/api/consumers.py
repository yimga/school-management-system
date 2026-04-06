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

User = get_user_model()


class StudentSyncConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for student data synchronization"""

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_group_name = f"students_sync_{self.user.id}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")

        # Echo message back (for testing)
        await self.send(text_data=json.dumps({"message": f"Received: {message}"}))

    # Receive message from room group
    async def student_update(self, event):
        message = event["message"]

        # Send message to WebSocket
        await self.send(
            text_data=json.dumps({"type": "student_update", "message": message})
        )


class TeacherSyncConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for teacher data synchronization"""

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_group_name = f"teachers_sync_{self.user.id}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")

        await self.send(text_data=json.dumps({"message": f"Received: {message}"}))

    async def teacher_update(self, event):
        message = event["message"]

        await self.send(
            text_data=json.dumps({"type": "teacher_update", "message": message})
        )


class ClassroomSyncConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for classroom data synchronization"""

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_group_name = f"classrooms_sync_{self.user.id}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

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
            await self.close()
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
        from apps.portal.ai_provider import _normalize_gateway_metadata
        from services.ai_gateway import invoke

        request = self.scope.get("request", None)
        school = getattr(request, "school", None) or getattr(self.user, "school", None)
        user_id = getattr(self.user, "pk", None) or getattr(self.user, "id", None)
        school_pk = None
        if school is not None:
            school_pk = getattr(school, "pk", None) or getattr(school, "id", None)
        school_id = (
            str(school_pk)
            if school_pk is not None
            else (
                str(getattr(self.user, "school_id", None))
                if getattr(self.user, "school_id", None)
                else None
            )
        )
        country_code = payload.get("country_code") or getattr(school, "country_code", None) or (
            getattr(school, "default_region", None)
            and getattr(school.default_region, "code", None)
        )
        role = (
            getattr(self.user, "role", None)
            or getattr(self.user, "portal_role", None)
            or getattr(self.user, "user_type", None)
        )
        prompt = (
            "You are a helpful assistant for the school platform. Answer concisely.\n\nUser: "
            + message
        )

        def _gateway_infer():
            result, meta = invoke(
                "general_chat",
                prompt,
                user_query=message,
                metadata=_normalize_gateway_metadata(
                    {
                        "request": request,
                        "school": school,
                        "school_id": school_id,
                        "tenant_id": school_id,
                        "user_id": str(user_id) if user_id is not None else None,
                        "country_code": country_code,
                        "role": role,
                    }
                ),
            )
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
