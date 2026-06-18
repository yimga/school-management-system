"""Omnichannel communication routing wizard → tenant channel policy (OSS gateways)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _routing_blob(school: Any | None) -> dict[str, Any]:
    if school is None:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.objects.filter(pk=1).first()
        if rd is None:
            return {}
        return dict((rd.payload or {}).get("communication_routing") or {})
    return dict((getattr(school, "settings", None) or {}).get("communication_routing") or {})


def _save_routing(school: Any | None, blob: dict[str, Any]) -> None:
    blob["updated_at"] = _utc_now()
    if school is not None:
        settings = dict(getattr(school, "settings", None) or {})
        settings["communication_routing"] = blob
        school.settings = settings
        school.save(update_fields=["settings"])
        return
    from apps.platform_runtime.models import RuntimeDefaults

    rd, _ = RuntimeDefaults.objects.get_or_create(pk=1)
    payload = dict(rd.payload or {})
    payload["communication_routing"] = blob
    rd.payload = payload
    rd.save(update_fields=["payload", "updated_at"])


def apply_event_trigger(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    blob = _routing_blob(school)
    blob["event_trigger"] = payload.get("value") or payload.get("event_trigger")
    _save_routing(school, blob)
    return {"ok": True, "event_trigger": blob["event_trigger"]}


def apply_gateway_priority(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    ranked = payload.get("value") or payload.get("ranked") or payload.get("channels") or []
    if not isinstance(ranked, list):
        ranked = [ranked]
    blob = _routing_blob(school)
    blob["gateway_priority"] = ranked
    blob["gateways"] = "smtp-brevo-sms-whatsapp-push-oss"
    _save_routing(school, blob)
    return {"ok": True, "gateway_priority": ranked}


def apply_async_guards(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    blob = _routing_blob(school)
    blob["async_guards"] = {
        k: payload.get(k)
        for k in (
            "quiet_hours_start",
            "quiet_hours_end",
            "max_messages_per_recipient_per_day",
            "defer_until_business_hours",
        )
    }
    _save_routing(school, blob)
    return {"ok": True, "async_guards": blob["async_guards"]}


def apply_translation_locales(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    locales = payload.get("value") or payload.get("locales") or []
    if not isinstance(locales, list):
        locales = [locales]
    blob = _routing_blob(school)
    blob["translation_locales"] = locales
    _save_routing(school, blob)
    return {"ok": True, "translation_locales": locales}
