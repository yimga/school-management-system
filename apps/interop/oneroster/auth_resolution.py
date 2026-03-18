"""Resolve OneRoster Bearer to integration; scopes, IP allowlist, export profile."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from django.db.models import Q

from apps.api.rate_limit import throttle_ip_request
from apps.integrations_marketplace.models import ServiceIntegration
from apps.interop.oneroster.constants import ONEROSTER_DISTRICT_API_SERVICE_NAME

# Endpoint key -> any of these scope strings grants access (plus "*" always)
ENDPOINT_REQUIRED_SCOPES: dict[str, tuple[str, ...]] = {
    "manifest": ("*", "roster", "roster.manifest"),
    "academicSessions": ("*", "roster", "roster.sessions", "roster.academicSessions"),
    "classes": ("*", "roster", "roster.classes"),
    "students": ("*", "roster", "roster.students"),
    "teachers": ("*", "roster", "roster.teachers"),
    "enrollments": ("*", "roster", "roster.enrollments"),
    "orgs": ("*", "roster", "roster.orgs"),
    "courses": ("*", "roster", "roster.courses"),
    "users": ("*", "roster", "roster.users"),
}


def _integration_candidates(school) -> list[ServiceIntegration]:
    return list(
        ServiceIntegration.objects.filter(school=school, is_active=True)
        .filter(
            Q(service_name__icontains="oneroster")
            | Q(service_name__icontains="1edtech")
            | Q(service_name__iexact=ONEROSTER_DISTRICT_API_SERVICE_NAME)
        )
        .order_by("-updated_at", "-id")
    )


def _token_for_integration(integ: ServiceIntegration) -> str:
    return str(
        (integ.config or {}).get("bearer_token") or integ.client_secret or ""
    ).strip()


def match_integration_for_token(school, provided: str) -> ServiceIntegration | None:
    if not provided:
        return None
    for integ in _integration_candidates(school):
        t = _token_for_integration(integ)
        if t and len(t) == len(provided) and secrets.compare_digest(t, provided):
            return integ
    return None


def _parse_scopes(cfg: dict[str, Any]) -> set[str]:
    raw = cfg.get("oneroster_scopes") or cfg.get("scopes")
    if raw is None:
        return {"*"}
    if isinstance(raw, str):
        parts = [x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()]
        return set(parts) if parts else {"*"}
    if isinstance(raw, list):
        return {str(x).strip().lower() for x in raw if str(x).strip()} or {"*"}
    return {"*"}


def scope_allows(endpoint_key: str, scopes: set[str]) -> bool:
    if "*" in scopes or "roster" in scopes:
        return True
    allowed = ENDPOINT_REQUIRED_SCOPES.get(endpoint_key, ("*",))
    return any(s.lower() in scopes for s in allowed)


def ip_allowed(cfg: dict[str, Any], ip: str) -> bool:
    raw = cfg.get("allowed_ips") or cfg.get("oneroster_allowed_ips")
    if not raw:
        return True
    if isinstance(raw, list):
        allow = {str(x).strip() for x in raw if str(x).strip()}
    else:
        allow = {x.strip() for x in str(raw).replace(",", " ").split() if x.strip()}
    ip = (ip or "").strip() or "unknown"
    return ip in allow


def export_profile(cfg: dict[str, Any]) -> str:
    p = (
        str(
            cfg.get("oneroster_export_profile")
            or cfg.get("export_profile")
            or "standard"
        )
        .strip()
        .lower()
    )
    if p in ("minimal", "standard", "full"):
        return p
    return "standard"


def per_token_throttle(
    request,
    *,
    endpoint_key: str,
    token: str,
    max_count: int,
    window_seconds: int,
) -> tuple[bool, int]:
    th = hashlib.sha256(token.encode("utf-8")).hexdigest()[:20]
    return throttle_ip_request(
        request,
        scope=f"oneroster:tok:{endpoint_key}:{th}",
        max_count=max_count,
        window_seconds=window_seconds,
    )


def token_rate_limit_from_config(cfg: dict[str, Any], default: int = 600) -> int:
    try:
        v = int(
            cfg.get("oneroster_rate_limit_per_window")
            or cfg.get("rate_limit")
            or default
        )
        return max(30, min(v, 100_000))
    except (TypeError, ValueError):
        return default
