"""Default Stripe subscription cancel adapter for tenant offboarding (O4)."""
from __future__ import annotations

import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.billing.processors import _parse_response_json
from apps.billing.stripe_checkout import (
    get_active_stripe_processor_config,
    stripe_api_base,
    stripe_secret_key,
)

logger = logging.getLogger(__name__)


def _stripe_delete(
    url: str, *, secret_key: str, timeout: int = 30
) -> tuple[int, dict]:
    request = Request(
        url,
        headers={"Authorization": f"Bearer {secret_key}"},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            return int(response.getcode() or 200), _parse_response_json(raw_text)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return int(exc.code or 500), _parse_response_json(detail)
    except URLError as exc:
        logger.warning("stripe remote cancel network error: %s", exc.reason)
        return 0, {}


def cancel_stripe_subscription(external_ref: str) -> bool:
    """Cancel a Stripe subscription by id (sub_*). Returns True when canceled."""
    ref = (external_ref or "").strip()
    if not ref.startswith("sub_"):
        return False
    config = get_active_stripe_processor_config()
    if config is None:
        return False
    secret = stripe_secret_key(config)
    if not secret:
        return False
    url = f"{stripe_api_base(config)}/v1/subscriptions/{ref}"
    status, body = _stripe_delete(url, secret_key=secret)
    if status not in (200, 204):
        logger.warning(
            "stripe remote cancel failed ref=%s status=%s", ref, status
        )
        return False
    stripe_status = str(body.get("status") or "").lower()
    return stripe_status in ("canceled", "cancelled") or status == 200
