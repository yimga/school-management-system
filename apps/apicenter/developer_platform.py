"""
F6: Developer platform — API gateway, webhooks, SDKs, docs.
"""

from __future__ import annotations

# API schema at /api/schema/; webhooks in events/siteconfig; docs link to schema UI.
DEVELOPER_PLATFORM_LINKS = {
    "api_schema": "/api/schema/",
    "api_schema_ui": "/api/schema/ui/",
    "api_v2_manifest": "/api/v2/manifest.json",
    "api_v2_ping": "/api/v2/ping/",
    "oauth_token": "/api/v1/oauth/token/",
    "oauth_authorize": "/api/v1/oauth/authorize/",
    "developer_hub": "/developer/",
    "webhooks": "events.WebhookSubscription / siteconfig.WebhookSubscription",
}
