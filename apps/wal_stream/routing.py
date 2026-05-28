"""Channels routing for the WAL stream.

Wire into ``config/asgi.py`` ProtocolTypeRouter alongside the existing
``ws/ai/chat/`` routes.
"""

from __future__ import annotations

from django.urls import re_path

from apps.wal_stream.consumers import WalStreamConsumer

websocket_urlpatterns = [
    re_path(r"^ws/wal/$", WalStreamConsumer.as_asgi()),
]
