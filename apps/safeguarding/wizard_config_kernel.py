"""Safeguarding incident wizard → tenant DSL config (school.settings bucket).

Mirrors ``concern_kernel`` / ``dsl_notify`` storage: no new migrations.
Operator wizard steps configure enabled categories, legal routing, stakeholder
pipeline order, and immutable audit anchor for the tenant safeguarding runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.safeguarding.concern_kernel import list_categories


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safeguarding_blob(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    return dict((getattr(school, "settings", None) or {}).get("safeguarding") or {})


def _save_safeguarding(school: Any | None, blob: dict[str, Any]) -> None:
    if school is None:
        return
    blob["wizard_config_updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["safeguarding"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def _normalize_multi(payload: dict[str, Any]) -> list[Any]:
    raw = payload.get("value") or payload.get("values") or payload.get("categories") or []
    if isinstance(raw, list):
        return raw
    if raw:
        return [raw]
    return []


def apply_enabled_categories(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    known = {c.key for c in list_categories()}
    selected = [str(v) for v in _normalize_multi(payload) if str(v) in known]
    blob = _safeguarding_blob(school)
    blob["enabled_categories"] = selected or list(known)
    _save_safeguarding(school, blob)
    return {"ok": True, "enabled_categories": blob["enabled_categories"]}


def apply_legal_routing(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    routing = payload.get("value") or payload.get("routing") or payload.get("protocol")
    blob = _safeguarding_blob(school)
    blob["legal_protocol_routing"] = routing
    if payload.get("country_code"):
        blob["routing_country_code"] = payload["country_code"]
    if payload.get("state_code"):
        blob["routing_state_code"] = payload["state_code"]
    _save_safeguarding(school, blob)
    return {"ok": True, "legal_protocol_routing": routing}


def apply_stakeholder_pipeline(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    ranked = payload.get("value") or payload.get("ranked") or payload.get("stakeholders") or []
    if not isinstance(ranked, list):
        ranked = [ranked] if ranked else []
    blob = _safeguarding_blob(school)
    blob["stakeholder_pipeline"] = ranked
    _save_safeguarding(school, blob)
    return {"ok": True, "stakeholder_pipeline": ranked}


def apply_audit_anchor(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    anchor = payload.get("value") or payload.get("anchor")
    allowed = {"append_only_db", "s3_object_lock", "hsm_anchored"}
    if anchor not in allowed:
        anchor = "append_only_db"
    blob = _safeguarding_blob(school)
    blob["audit_anchor"] = anchor
    _save_safeguarding(school, blob)
    return {"ok": True, "audit_anchor": anchor}
