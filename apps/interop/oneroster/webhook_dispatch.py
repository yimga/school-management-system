"""Signed roster webhooks (HMAC-SHA256) for student/class/teacher changes."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _district_config(school) -> dict[str, Any]:
    try:
        from apps.integrations_marketplace.models import ServiceIntegration
        from apps.interop.oneroster.constants import ONEROSTER_DISTRICT_API_SERVICE_NAME

        row = (
            ServiceIntegration.objects.filter(
                school=school,
                is_active=True,
                service_name__iexact=ONEROSTER_DISTRICT_API_SERVICE_NAME,
            )
            .order_by("-updated_at")
            .first()
        )
        return dict((row.config or {})) if row else {}
    except Exception:
        return {}


def emit_roster_webhook(
    school,
    *,
    event: str,
    entity: str,
    sourced_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    cfg = _district_config(school)
    url = str(cfg.get("roster_webhook_url") or cfg.get("webhook_url") or "").strip()
    if not url:
        return
    secret = str(
        cfg.get("roster_webhook_secret") or cfg.get("webhook_secret") or ""
    ).strip()
    body = {
        "event": event,
        "entity": entity,
        "sourcedId": str(sourced_id),
        "school_slug": getattr(school, "slug", ""),
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": payload or {},
    }
    raw = json.dumps(body, separators=(",", ":"), default=str).encode("utf-8")

    def _send():
        try:
            import urllib.request

            req = urllib.request.Request(url, data=raw, method="POST")
            req.add_header("Content-Type", "application/json")
            if secret:
                sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
                req.add_header("X-RunMyCampus-Signature", f"sha256={sig}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "roster_webhook status=%s school=%s", resp.status, school.pk
                    )
        except Exception as e:
            logger.debug(
                "roster_webhook failed school=%s: %s", getattr(school, "pk", None), e
            )

    threading.Thread(target=_send, daemon=True).start()
