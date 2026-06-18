"""Localized marketplace wizard → tenant storefront / catalog / receipt policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _marketplace_blob(school: Any | None) -> dict[str, Any]:
    if school is None:
        return {}
    settings = getattr(school, "settings", None) or {}
    return dict((settings.get("marketplace") or {}))


def _save_marketplace(school: Any | None, blob: dict[str, Any]) -> None:
    if school is None:
        return
    blob["updated_at"] = _utc_now()
    settings = dict(getattr(school, "settings", None) or {})
    settings["marketplace"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])


def apply_storefront_blueprint(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    blueprint = {
        k: payload.get(k)
        for k in (
            "storefront_name",
            "default_currency",
            "default_tax_inclusive",
        )
        if k in payload
    }
    blob = _marketplace_blob(school)
    blob["storefront"] = blueprint
    _save_marketplace(school, blob)
    return {"ok": True, "storefront": blueprint}


def apply_catalog_seed(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("value")
    entry: dict[str, Any] = {}
    if isinstance(value, dict):
        entry = {
            "file_name": value.get("file_name"),
            "file_size": value.get("file_size"),
        }
    elif isinstance(value, str) and value.strip():
        entry = {"file_name": value.strip()}

    blob = _marketplace_blob(school)
    seeds = list(blob.get("catalog_seeds") or [])
    if entry:
        seeds.append({**entry, "registered_at": _utc_now()})
        if len(seeds) > 20:
            seeds = seeds[-20:]
    blob["catalog_seeds"] = seeds
    _save_marketplace(school, blob)
    return {"ok": True, "catalog_seeds_count": len(seeds)}


def apply_receipt_automation(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    receipts = {
        k: payload.get(k)
        for k in (
            "receipt_template",
            "delivery_channel",
            "include_qr_code",
            "value",
        )
        if k in payload
    }
    if payload.get("value") and "receipt_template" not in receipts:
        receipts["routing_choice"] = payload.get("value")
    blob = _marketplace_blob(school)
    blob["receipt_automation"] = receipts
    _save_marketplace(school, blob)
    return {"ok": True, "receipt_automation": receipts}
