"""
Portal shared constants and helpers used by parent, teacher, and student views (§6.14 role separation).
"""

from __future__ import annotations

import base64
from io import BytesIO

from django.urls import NoReverseMatch
from django.db import DatabaseError

from apps.platform_runtime.helpers import get_effective_feature_control_settings

# Exception types allowed in portal soft-fail paths (e.g. URL reverse, feature flags)
PORTAL_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    NoReverseMatch,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

# Portal feature metadata for navigation and UI
PORTAL_FEATURES_META = {
    "messaging": {
        "label": "Messaging",
        "description": "Send broadcasts or targeted notes to teachers, staff, and guardians.",
        "icon": "bi-chat-left-text",
    },
    "forums": {
        "label": "Community Forums",
        "description": "Create topic-driven discussions for parents, teachers, and leadership.",
        "icon": "bi-people",
    },
    "video": {
        "label": "Video Hub",
        "description": "Share announcements, tutorials, or recorded meetings school-wide.",
        "icon": "bi-camera-video",
    },
    "documents": {
        "label": "Document Library",
        "description": "Publish handbooks, timetables, and policy updates for anyone to download.",
        "icon": "bi-file-earmark-text",
    },
    "syllabus": {
        "label": "Class Syllabus",
        "description": "Download lesson plans, term agendas, and curriculum outlines for every specialty.",
        "icon": "bi-journal-text",
    },
}

# Per-feature RBAC: permission required to access each portal tool (sidebar + direct URL)
PORTAL_FEATURE_PERMISSIONS = {
    "forums": "portal.forums",
    "video": "portal.video",
    "documents": "portal.documents",
}


def _portal_features_status(request=None) -> list[dict]:
    """Return list of portal features with enabled status from runtime feature control."""
    feature_settings = get_effective_feature_control_settings(request=request)
    features = feature_settings.get("portal_features") or {}
    return [
        {
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "icon": meta.get("icon"),
            "enabled": bool(features.get(key)),
        }
        for key, meta in PORTAL_FEATURES_META.items()
    ]


def _qr_png_data_uri(value: str) -> str:
    """Generate an inline PNG data URI for QR rendering (shared by parent/teacher digital ID views)."""
    try:
        import qrcode
        import qrcode.image.pil
    except ImportError:
        return ""
    image = qrcode.make(value, image_factory=qrcode.image.pil.PilImage)
    stream = BytesIO()
    image.save(stream, "PNG")
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
