"""
WebSocket URL Routing for Django Channels
Requires: pip install channels channels-redis
"""

try:
    from django.urls import re_path
    from apps.api import consumers

    if consumers.CHANNELS_AVAILABLE:
        websocket_urlpatterns = [
            re_path(r"ws/students/$", consumers.StudentSyncConsumer.as_asgi()),
            re_path(r"ws/teachers/$", consumers.TeacherSyncConsumer.as_asgi()),
            re_path(r"ws/classrooms/$", consumers.ClassroomSyncConsumer.as_asgi()),
            re_path(r"ws/notifications/$", consumers.NotificationSyncConsumer.as_asgi()),
            re_path(r"ws/substitute-market/$", consumers.SubstituteMarketConsumer.as_asgi()),
            re_path(r"ws/workflow-progress/$", consumers.WorkflowTelemetryConsumer.as_asgi()),
            re_path(r"ws/ai/chat/$", consumers.AIChatConsumer.as_asgi()),
            re_path(r"ws/support/chat/$", consumers.SupportChatConsumer.as_asgi()),
            re_path(r"ws/support/agent/$", consumers.SupportAgentConsumer.as_asgi()),
        ]
    else:
        websocket_urlpatterns = []
except ImportError:
    websocket_urlpatterns = []

# v4.00.0: WAL outbox stream WebSocket — independent of the legacy consumers
# so Channels routing works even when those are unavailable in this build.
try:
    from apps.wal_stream.routing import websocket_urlpatterns as _wal_routes
    websocket_urlpatterns = list(websocket_urlpatterns) + list(_wal_routes)
except ImportError:
    pass
