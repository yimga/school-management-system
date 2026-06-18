"""JIT operator compliance wizard → triggers, masking, non-repudiation ledger (OSS)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jit_blob(school: Any | None) -> dict[str, Any]:
    if school is not None:
        return dict((getattr(school, "settings", None) or {}).get("jit_compliance") or {})
    from apps.platform_runtime.models import RuntimeDefaults

    rd = RuntimeDefaults.objects.filter(pk=1).first()
    if rd is None:
        return {}
    return dict((rd.payload or {}).get("jit_compliance") or {})


def _save_jit(school: Any | None, blob: dict[str, Any]) -> None:
    blob["updated_at"] = _utc_now()
    if school is not None:
        settings = dict(getattr(school, "settings", None) or {})
        settings["jit_compliance"] = blob
        school.settings = settings
        school.save(update_fields=["settings"])
        return
    from apps.platform_runtime.models import RuntimeDefaults

    rd, _ = RuntimeDefaults.objects.get_or_create(pk=1)
    payload = dict(rd.payload or {})
    payload["jit_compliance"] = blob
    rd.payload = payload
    rd.save(update_fields=["payload", "updated_at"])


def apply_jit_triggers(*, school: Any | None, payload: dict[str, Any], actor_user_id: int | None = None) -> dict[str, Any]:
    triggers = payload.get("value") or payload.get("triggers") or []
    if not isinstance(triggers, list):
        triggers = [triggers]
    blob = _jit_blob(school)
    blob["triggers"] = triggers
    _save_jit(school, blob)
    _record_ledger(
        school=school,
        action="jit.triggers_configured",
        actor_user_id=actor_user_id,
        summary={"triggers": triggers},
    )
    return {"ok": True, "triggers": triggers}


def apply_compliance_guardrails(*, school: Any | None, payload: dict[str, Any], actor_user_id: int | None = None) -> dict[str, Any]:
    guardrails = {
        "geo_fence_radius_meters": payload.get("geo_fence_radius_meters"),
        "allowed_ip_ranges": payload.get("allowed_ip_ranges"),
        "require_2fa_within_window": bool(payload.get("require_2fa_within_window", False)),
    }
    blob = _jit_blob(school)
    blob["guardrails"] = guardrails
    _save_jit(school, blob)
    _record_ledger(
        school=school,
        action="jit.guardrails_configured",
        actor_user_id=actor_user_id,
        summary=guardrails,
    )
    return {"ok": True, "guardrails": guardrails}


def apply_pii_masking_fields(*, school: Any | None, payload: dict[str, Any], actor_user_id: int | None = None) -> dict[str, Any]:
    fields = payload.get("value") or payload.get("fields") or []
    if not isinstance(fields, list):
        fields = [fields]
    blob = _jit_blob(school)
    blob["pii_masking_fields"] = fields
    _save_jit(school, blob)
    _record_ledger(
        school=school,
        action="jit.pii_masking_configured",
        actor_user_id=actor_user_id,
        summary={"field_count": len(fields)},
    )
    return {"ok": True, "pii_masking_fields": fields}


def apply_ledger_anchor(*, school: Any | None, payload: dict[str, Any], actor_user_id: int | None = None) -> dict[str, Any]:
    anchor = payload.get("value") or payload.get("ledger_anchor") or "append_only_db"
    blob = _jit_blob(school)
    blob["ledger_anchor"] = str(anchor)
    blob["ledger_engine"] = "compliance.non_repudiation"
    _save_jit(school, blob)
    _record_ledger(
        school=school,
        action="jit.ledger_anchor_selected",
        actor_user_id=actor_user_id,
        summary={"anchor": anchor},
    )
    return {"ok": True, "ledger_anchor": anchor}


def _record_ledger(*, school: Any | None, action: str, actor_user_id: int | None, summary: dict) -> None:
    try:
        from apps.compliance.non_repudiation import record_action

        record_action(
            action=action,
            resource="jit_operator_compliance",
            actor_id=actor_user_id,
            school_id=getattr(school, "pk", None),
            payload_summary=summary,
        )
    except Exception:  # noqa: BLE001
        pass
