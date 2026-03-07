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
            re_path(r"ws/ai/chat/$", consumers.AIChatConsumer.as_asgi()),
        ]
    else:
        websocket_urlpatterns = []
except ImportError:
    websocket_urlpatterns = []
