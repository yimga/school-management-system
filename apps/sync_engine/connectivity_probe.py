"""Edge box ↔ cloud connectivity diagnostics (operator URL, credential, HTTP hints)."""

from __future__ import annotations

import json
import os
from typing import Any
from apps.sync_engine.cloud_endpoints import cloud_endpoint


def operator_base() -> str:
    from django.conf import settings

    from apps.sync_engine.edge_binding import operator_base

    base = operator_base()
    if not base:
        base = (getattr(settings, "RMC_HUB_BASE_URL", "") or "").strip()
    return base.rstrip("/")


def credential_configured() -> bool:
    from apps.sync_engine.edge_binding import edge_credential

    return bool(edge_credential())


def extract_http_error_detail(body: Any) -> str:
    """Best-effort parse of an HTTP error body (bytes or dict)."""
    if body is None:
        return ""
    if isinstance(body, dict):
        for key in ("error", "detail", "message", "raw"):
            val = body.get(key)
            if val:
                return str(val)[:240]
        return ""
    if isinstance(body, (bytes, bytearray)):
        text = bytes(body).decode("utf-8", "replace").strip()
    else:
        text = str(body).strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return text[:240]
    if isinstance(parsed, dict):
        for key in ("error", "detail", "message", "raw"):
            val = parsed.get(key)
            if val:
                return str(val)[:240]
    return text[:240]


def format_http_rejection(phase: str, status: int, body: Any) -> str:
    """Human-readable rejection line stored on EdgeSyncRun.error."""
    detail = extract_http_error_detail(body)
    msg = f"{phase} rejected (HTTP {status})"
    if detail:
        msg += f": {detail}"
    if status == 502:
        msg += (
            " — cloud gateway error (502): the box reached a proxy but not a healthy "
            "Django response. Set RMC_EDGE_OPERATOR_BASE to the TENANT host "
            "(e.g. https://<your-tenant>.<your-domain>), confirm the cloud tenant is up, "
            "and do not point at manager/marketing hosts."
        )
    elif status in (401, 403):
        msg += (
            " — credential or tenant mismatch: mint RMC_EDGE_CREDENTIAL on the cloud "
            "with `python manage.py mint_edge_credential --slug <school> --user <admin>`."
        )
    elif status == 404:
        msg += (
            " — download/upload path not found: RMC_EDGE_OPERATOR_BASE is probably wrong "
            "or the cloud is on an older build without sync bundle APIs."
        )
    return msg


def connectivity_snapshot() -> dict[str, Any]:
    from django.conf import settings

    base = operator_base()
    return {
        "edge_sync_enabled": bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)),
        "deployment_profile": getattr(settings, "RMC_DEPLOYMENT_PROFILE", "") or "",
        "operator_base": base,
        "operator_base_configured": bool(base),
        "credential_configured": credential_configured(),
        "pull_endpoint": cloud_endpoint(base, "api:sync-bundle-download") if base else "",
        "upload_endpoint": cloud_endpoint(base, "api:sync-bundle-upload") if base else "",
        "school_slug_pin": (os.getenv("RMC_EDGE_SCHOOL_SLUG") or "").strip(),
    }


def probe_cloud_http(*, timeout: float = 20.0) -> dict[str, Any]:
    """Live HTTP probe of cloud pull + push endpoints (Sync Center / mgmt command)."""
    import urllib.error
    import urllib.request

    from apps.sync_engine.edge_outbox import BUNDLE_CONTENT_TYPE

    snap = connectivity_snapshot()
    problems: list[str] = []
    if not snap.get("edge_sync_enabled"):
        problems.append("RMC_EDGE_SYNC_ENABLED is off on this box.")
    if not snap.get("operator_base_configured"):
        problems.append(
            "Set RMC_EDGE_OPERATOR_BASE to the TENANT cloud host "
            "(e.g. https://<your-tenant>.<your-domain>) — not this LAN box, not manager/marketing."
        )
    if not snap.get("credential_configured"):
        problems.append(
            "Set RMC_EDGE_CREDENTIAL (mint on cloud: "
            "python manage.py mint_edge_credential --slug <your-tenant> --user <admin>)."
        )

    result: dict[str, Any] = {
        **snap,
        "ok": not problems,
        "problems": problems,
        "probes": {},
    }
    if not snap.get("operator_base_configured"):
        result["ok"] = False
        return result

    from apps.sync_engine.edge_binding import edge_credential

    token = edge_credential()
    base = operator_base()
    headers_base = {"Authorization": f"Bearer {token}"} if token else {}

    def _http_probe(phase: str, url: str, *, method: str = "GET", body: bytes | None = None):
        headers = dict(headers_base)
        if method == "GET":
            headers["Accept"] = BUNDLE_CONTENT_TYPE
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return {
                    "ok": True,
                    "status": resp.getcode(),
                    "detail": "cloud responded",
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            detail = format_http_rejection(phase, exc.code, raw)
            alive = exc.code not in (502, 503, 504)
            return {"ok": alive, "status": exc.code, "detail": detail}
        except (urllib.error.URLError, OSError) as exc:
            return {"ok": False, "status": 0, "detail": f"unreachable: {exc}"}

    pull = _http_probe("pull", cloud_endpoint(base, "api:sync-bundle-download"))
    push = _http_probe(
        "push",
        cloud_endpoint(base, "api:sync-bundle-upload"),
        method="POST",
        body=b"",
    )
    result["probes"] = {"pull": pull, "push": push}
    if not pull.get("ok"):
        problems.append(str(pull.get("detail") or "pull probe failed"))
    if not push.get("ok"):
        push_detail = str(push.get("detail") or "push probe failed")
        if push_detail not in problems:
            problems.append(push_detail)
    result["problems"] = problems
    result["ok"] = not problems
    return result
