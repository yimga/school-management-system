"""Field trip wizard → consent pipeline + medical checklist config."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_field_trip_logistics(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    trip = {
        "trip_name": (payload.get("trip_name") or "").strip(),
        "destination": (payload.get("destination") or "").strip(),
        "departure_datetime": payload.get("departure_datetime"),
        "return_datetime": payload.get("return_datetime"),
        "transport_type": payload.get("transport_type"),
        "cost_per_student_decimal": str(payload.get("cost_per_student_decimal") or "0.00"),
        "updated_at": _utc_now(),
    }
    settings = dict(getattr(school, "settings", None) or {})
    ft = dict(settings.get("field_trip") or {})
    ft["logistics"] = trip
    settings["field_trip"] = ft
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "logistics": trip}


def setup_field_trip_authorization(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    settings = dict(getattr(school, "settings", None) or {})
    ft = dict(settings.get("field_trip") or {})
    auth = {
        "parent_signature_required": bool(payload.get("parent_signature_required", True)),
        "payment_required": bool(payload.get("payment_required", False)),
        "medical_release_required": bool(payload.get("medical_release_required", True)),
        "photo_consent_required": bool(payload.get("photo_consent_required", False)),
        "updated_at": _utc_now(),
    }
    ft["authorization"] = auth
    settings["field_trip"] = ft
    school.settings = settings
    school.save(update_fields=["settings"])

    consent_id = None
    if auth["parent_signature_required"]:
        from apps.schoolops.field_trip import create_field_trip_consent

        logistics = ft.get("logistics") or {}
        title = logistics.get("trip_name") or "Field trip"
        req = create_field_trip_consent(
            school_id=school.pk,
            title=title,
            description=logistics.get("destination") or "",
        )
        consent_id = getattr(req, "pk", None)
    return {"ok": True, "authorization": auth, "consent_request_id": consent_id}


def enable_field_trip_roster(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    enabled = payload.get("value")
    if enabled is None:
        enabled = payload.get("enabled", True)
    settings = dict(getattr(school, "settings", None) or {})
    ft = dict(settings.get("field_trip") or {})
    ft["real_time_roster"] = {
        "enabled": bool(enabled),
        "checklist_engine": "schoolops.field_trip.build_medical_checklist",
        "updated_at": _utc_now(),
    }
    settings["field_trip"] = ft
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "real_time_roster": ft["real_time_roster"]}
