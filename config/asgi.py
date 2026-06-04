"""
ASGI config for WebSocket support
Requires: pip install channels channels-redis
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import routing after Django is set up (only if channels is installed)
try:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.auth import AuthMiddlewareStack
    from apps.schools.channels_tenant_middleware import TenantChannelsMiddleware
    from config.routing import websocket_urlpatterns

    application = ProtocolTypeRouter(
        {
            "http": django_asgi_app,
            "websocket": AuthMiddlewareStack(
                TenantChannelsMiddleware(URLRouter(websocket_urlpatterns))
            ),
        }
    )
except ImportError:
    # Fallback if channels is not installed
    application = django_asgi_app
