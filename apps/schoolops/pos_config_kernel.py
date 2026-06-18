"""Cashless campus POS wizard → meal-plan guardrails + terminal registry (OSS stack)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _dec(value: Any, default: str = "0.00") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def register_pos_terminals(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist terminal registry under ``school.settings['pos']['terminals']``."""
    if school is None:
        return {"ok": False}
    terminals = payload.get("pairs") or payload.get("terminals") or payload
    if isinstance(terminals, dict) and not payload.get("pairs"):
        terminals = [{"key": k, "value": v} for k, v in terminals.items()]
    record = {
        "terminals": terminals if isinstance(terminals, list) else [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    settings = dict(getattr(school, "settings", None) or {})
    pos = dict(settings.get("pos") or {})
    pos["terminals"] = record["terminals"]
    pos["terminals_updated_at"] = record["updated_at"]
    settings["pos"] = pos
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, **record}


def configure_pos_credentials(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    method = payload.get("value") or payload.get("credential_method") or "qr_id_card"
    settings = dict(getattr(school, "settings", None) or {})
    pos = dict(settings.get("pos") or {})
    pos["credential_method"] = str(method)
    settings["pos"] = pos
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "credential_method": method}


def configure_pos_guardrails(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply daily limits + low-balance threshold to school settings and wallet rows."""
    if school is None:
        return {"ok": False}
    from apps.schoolops.models import MealPlanBalance

    low = _dec(payload.get("low_balance_threshold"), "5.00")
    guardrails = {
        "parent_default_daily_limit_decimal": str(
            _dec(payload.get("parent_default_daily_limit_decimal"), "20.00")
        ),
        "top_up_minimum": str(_dec(payload.get("top_up_minimum"), "5.00")),
        "top_up_maximum": str(_dec(payload.get("top_up_maximum"), "200.00")),
        "low_balance_threshold": str(low),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    settings = dict(getattr(school, "settings", None) or {})
    pos = dict(settings.get("pos") or {})
    pos["guardrails"] = guardrails
    settings["pos"] = pos
    school.settings = settings
    school.save(update_fields=["settings"])

    updated = MealPlanBalance.objects.filter(school=school).update(low_balance_threshold=low)
    return {"ok": True, "guardrails": guardrails, "wallets_updated": updated}


def configure_pos_allergens(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Write allergen barrier flag — read by ``schoolops.pos_checkout``."""
    if school is None:
        return {"ok": False}
    enabled = payload.get("value")
    if enabled is None:
        enabled = payload.get("enabled", True)
    if isinstance(enabled, dict):
        enabled = enabled.get("enabled", True)
    blob = {"enabled": bool(enabled), "updated_at": datetime.now(timezone.utc).isoformat()}
    settings = dict(getattr(school, "settings", None) or {})
    settings["wizards.cashless_campus_pos.allergen_dietary_rules"] = blob
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "allergen_rules": blob}
