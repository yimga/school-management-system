"""AI helpcenter wizard steps 2–4 → tenant helpcenter policy (beyond source registration)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cs_bucket(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    return dict((settings.get("customersuccess") or {}))


def _save_cs(school: Any | None, cs: dict[str, Any]) -> None:
    if school is None:
        return
    cs["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["customersuccess"] = cs
    school.settings = settings
    school.save(update_fields=["settings"])


def _normalize_multi(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("value") or payload.get("tags") or payload.get("audience_tags") or []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return [str(raw)] if raw else []


def apply_audience_tags(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    tags = _normalize_multi(payload)
    cs = _cs_bucket(school)
    cs["helpcenter_audience_tags"] = tags
    _save_cs(school, cs)
    return {"ok": True, "helpcenter_audience_tags": tags}


def apply_fallback_matrix(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    matrix = payload.get("pairs") or payload.get("value") or payload.get("matrix") or payload
    if not isinstance(matrix, dict):
        matrix = {"default": matrix}
    cs = _cs_bucket(school)
    cs["helpcenter_fallbacks"] = matrix
    _save_cs(school, cs)
    return {"ok": True, "helpcenter_fallbacks": matrix}


def apply_validation_probe(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    probe = (payload.get("value") or payload.get("probe_text") or "").strip()
    cs = _cs_bucket(school)
    cs["helpcenter_validation"] = {
        "probe_length": len(probe),
        "probe_sha256_prefix": hashlib.sha256(probe.encode("utf-8")).hexdigest()[:16] if probe else "",
        "validated_at": _utc_now(),
    }
    _save_cs(school, cs)
    return {"ok": True, "validated": bool(probe)}
