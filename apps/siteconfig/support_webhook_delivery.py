"""
HTTP POST delivery for global support ticket webhooks (signed JSON).
Used synchronously by tests and asynchronously by Celery with retries.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def post_support_ticket_webhook(url: str, secret: str, payload: dict[str, Any]) -> None:
    """
    POST JSON to url. Raises on transport failure or HTTP >=500 (for Celery retry).
    HTTP 4xx: logs and returns without raising (no point retrying).
    """
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        headers["X-RunMyCampus-Signature"] = f"sha256={sig}"
    req = Request(url, data=raw, method="POST", headers=headers)
    try:
        with urlopen(req, timeout=15) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if status >= 400:
                logger.warning(
                    "support_ticket webhook HTTP %s for %s", status, url[:80]
                )
                if status >= 500:
                    raise OSError(f"webhook HTTP {status}")
    except HTTPError as e:
        code = int(getattr(e, "code", 0) or 0)
        logger.warning("support_ticket webhook HTTPError %s for %s", code, url[:80])
        if code >= 500:
            raise OSError(f"webhook HTTP {code}") from e
    except (URLError, OSError, TimeoutError):
        raise
