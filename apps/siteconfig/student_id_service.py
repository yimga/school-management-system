"""
Global Digital ID Engine (plan 3.17, 3.24).
StudentIDService: DesignTemplate (id_card) → 54×86mm PDF; QR = signed JWT; verify portal.
JWT short expiry (e.g. 5 min); rate-limit verify by IP.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ISO ID card size in mm
ID_CARD_WIDTH_MM = 54
ID_CARD_HEIGHT_MM = 86
JWT_EXPIRY_SECONDS = 300  # 5 min
VERIFY_RATE_LIMIT = "student_id_verify:%s"  # % (ip)
VERIFY_RATE_LIMIT_COUNT = 30
VERIFY_RATE_LIMIT_WINDOW = 60  # per minute


def _sign_jwt(payload: dict) -> str:
    """Sign a JWT with SECRET_KEY (HS256). No external dep."""
    import base64
    import hmac
    import hashlib

    header = {"alg": "HS256", "typ": "JWT"}
    payload["exp"] = int(time.time()) + JWT_EXPIRY_SECONDS
    payload["iat"] = int(time.time())
    b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode("ascii")
    msg = b64(json.dumps(header).encode()) + "." + b64(json.dumps(payload).encode())
    sig = hmac.new(
        settings.SECRET_KEY.encode()
        if isinstance(settings.SECRET_KEY, str)
        else settings.SECRET_KEY,
        msg=msg.encode(),
        digestmod=hashlib.sha256,
    ).digest()
    return msg + "." + b64(sig)


def _verify_jwt(token: str) -> Optional[dict]:
    """Verify and decode JWT; return payload or None if invalid/expired."""
    import base64
    import hmac
    import hashlib

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        msg = (parts[0] + "." + parts[1]).encode()
        sig_got = base64.urlsafe_b64decode(parts[2] + "==")
        sig_expected = hmac.new(
            settings.SECRET_KEY.encode()
            if isinstance(settings.SECRET_KEY, str)
            else settings.SECRET_KEY,
            msg=msg,
            digestmod=hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(sig_got, sig_expected):
            return None
        payload_b64 = parts[1] + "=="
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
        logger.debug("student_id JWT verify failed: %s", e)
        return None


def rate_limit_verify(ip: str) -> bool:
    """Return True if IP is over rate limit for verify endpoint."""
    key = VERIFY_RATE_LIMIT % ip
    count = cache.get(key, 0)
    if count >= VERIFY_RATE_LIMIT_COUNT:
        return True
    cache.set(key, count + 1, timeout=VERIFY_RATE_LIMIT_WINDOW)
    return False


def create_student_verify_token(
    school_id, student_id, student_name: str, photo_url: str = "", grade: str = ""
) -> str:
    """Create JWT for public verify page (name, photo, Active only; no PII)."""
    payload = {
        "school_id": str(school_id),
        "student_id": str(student_id),
        "name": (student_name or "")[:120],
        "photo": (photo_url or "")[:500],
        "grade": (grade or "")[:50],
        "status": "active",
    }
    return _sign_jwt(payload)


def verify_student_token(token: str) -> Optional[dict]:
    """Verify JWT and return payload (name, photo, status) for public display."""
    return _verify_jwt(token)


def get_id_card_template(school):
    """Get default id_card DesignTemplate for school."""
    from apps.siteconfig.models import DesignTemplate

    return (
        DesignTemplate.objects.filter(
            school=school,
            document_type=DesignTemplate.DocumentType.ID_CARD,
            is_default=True,
        ).first()
        or DesignTemplate.objects.filter(
            school=school,
            document_type=DesignTemplate.DocumentType.ID_CARD,
        ).first()
    )


def render_student_id_pdf(student_profile, school, template=None) -> Optional[bytes]:
    """
    Render 54×86mm ID card PDF for student using DesignTemplate.
    Uses design_studio.render_template_to_pdf with context from student_profile.
    """
    template = template or get_id_card_template(school)
    if not template:
        logger.warning("No id_card DesignTemplate for school %s", school.pk)
        return None
    from apps.siteconfig.design_studio import render_template_to_pdf

    name = f"{getattr(student_profile, 'first_name', '')} {getattr(student_profile, 'last_name', '')}".strip()
    photo_url = ""
    if (
        getattr(student_profile, "profile_photo", None)
        and student_profile.profile_photo
    ):
        photo_url = (
            student_profile.profile_photo.url
            if hasattr(student_profile.profile_photo, "url")
            else ""
        )
    grade = getattr(student_profile, "classroom", None)
    grade = grade.name if grade else getattr(student_profile, "section", "") or ""
    matricule = (
        getattr(student_profile, "admission_number", None)
        or getattr(student_profile, "student_code", "")
        or ""
    )
    context = {
        "student_name": name,
        "student_photo": photo_url,
        "grade_level": grade,
        "matricule": matricule,
        "school_name": getattr(school, "name", ""),
    }
    return render_template_to_pdf(template, context)
