"""
Tenant district hub: Clever/ClassLink native vendor credentials (ServiceIntegration.config)
and rate-limited outbound probes (no secrets logged).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

NATIVE_PROBE_HOURLY_LIMIT = 20

SUPER_NATIVE_ROSTER_POST_HOURLY_LIMIT = 30


def mask_token_preview(token: str | None) -> str:
    if not token:
        return ""
    t = str(token).strip()
    if len(t) <= 8:
        return "(set)" if t else ""
    return t[:6] + "…"


def native_probe_rate_allow(school_id: int) -> tuple[bool, str]:
    from django.core.cache import cache
    from django.utils import timezone

    key = f"dist_native_probe:{school_id}:{timezone.now().strftime('%Y%m%d%H')}"
    n = int(cache.get(key) or 0)
    if n >= NATIVE_PROBE_HOURLY_LIMIT:
        return False, "Hourly native vendor probe limit reached. Try again later."
    cache.set(key, n + 1, timeout=3700)
    return True, ""


def log_native_vendor_access(
    school,
    *,
    endpoint: str,
    client_ip: str = "",
    token_prefix: str = "",
) -> None:
    from apps.schools.models import TenantInteropAccessLog

    TenantInteropAccessLog.objects.create(
        school=school,
        service="native_vendor",
        endpoint=endpoint[:64],
        client_ip=(client_ip or "")[:64],
        token_prefix=(token_prefix or "")[:16],
    )


def summarize_api_result(obj: Any, *, max_len: int = 4000) -> str:
    try:
        s = json.dumps(obj, indent=2, default=str)
    except TypeError:
        s = str(obj)
    if len(s) > max_len:
        return s[: max_len - 20] + "\n…(truncated)"
    return s


def super_native_roster_post_allow(user_id: int) -> bool:
    from django.core.cache import cache
    from django.utils import timezone

    key = f"super_native_roster_post:{user_id}:{timezone.now().strftime('%Y%m%d%H')}"
    n = int(cache.get(key) or 0)
    if n >= SUPER_NATIVE_ROSTER_POST_HOURLY_LIMIT:
        return False
    cache.set(key, n + 1, timeout=3700)
    return True


def log_super_native_probe(
    *,
    user_id: int,
    had_clever: bool,
    had_classlink: bool,
    had_oauth: bool,
) -> None:
    try:
        from apps.platform_runtime.models import PlatformEventLog

        PlatformEventLog.objects.create(
            event_type="super_native_roster_probe",
            payload={
                "user_id": user_id,
                "had_clever": had_clever,
                "had_classlink": had_classlink,
                "had_oauth": had_oauth,
            },
            school_id="",
            tenant_id="",
        )
    except Exception:
        logger.exception("PlatformEventLog super_native_roster_probe failed")
