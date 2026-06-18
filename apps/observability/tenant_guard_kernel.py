"""Self-healing observability guard — tenant + platform SLO overrides (OSS backends).

Metrics: Prometheus client or structured-log via ``OBSERVABILITY_METRICS_BACKEND``.
Support tunnel: SSH reverse tunnel / WireGuard — not Cloudflare Access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _persist_guard_blob(*, school: Any | None, blob: dict[str, Any]) -> None:
    if school is not None:
        settings = dict(getattr(school, "settings", None) or {})
        settings["observability_guard"] = blob
        school.settings = settings
        school.save(update_fields=["settings"])
        return
    from apps.platform_runtime.models import RuntimeDefaults

    rd, _ = RuntimeDefaults.objects.get_or_create(pk=1)
    payload = dict(rd.payload or {})
    payload["observability_guard"] = blob
    rd.payload = payload
    rd.save(update_fields=["payload", "updated_at"])


def _merge_platform_slo_defaults(thresholds: dict[str, Any]) -> dict[str, Any]:
    from apps.observability.slo import SLOS

    merged = {
        slo.key: {
            "target": float(slo.target),
            "kind": slo.kind,
            "threshold_ms": getattr(slo, "threshold_ms", None),
        }
        for slo in SLOS
    }
    for key, val in thresholds.items():
        try:
            fval = float(val)
        except (TypeError, ValueError):
            fval = None
        if key in merged and fval is not None:
            merged[key]["tenant_override"] = fval
        elif fval is not None:
            merged[key] = {"tenant_override": fval}
    return merged


def apply_tenant_slo_thresholds(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    thresholds = {
        k: v
        for k, v in payload.items()
        if k.endswith("_threshold_pct") or k.endswith("_threshold_ms") or k.endswith("_target_pct")
    }
    blob = {
        "thresholds": thresholds,
        "slo_merge": _merge_platform_slo_defaults(thresholds),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "metrics_backend": "prometheus-client-or-structured-log",
    }
    _persist_guard_blob(school=school, blob=blob)
    return {"ok": True, "threshold_count": len(thresholds)}


def apply_recovery_actions(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    actions = payload.get("value") or payload.get("actions") or []
    if not isinstance(actions, list):
        actions = [actions]
    blob_fragment = {
        "recovery_actions": actions,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = _read_guard_blob(school)
    existing.update(blob_fragment)
    _persist_guard_blob(school=school, blob=existing)

    try:
        from apps.observability.metrics import emit_counter

        emit_counter(
            "observability.guard.recovery_actions_configured",
            labels={"count": str(len(actions))},
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "actions": actions}


def configure_support_tunnel(*, school: Any | None, payload: dict[str, Any]) -> dict[str, Any]:
    """OSS support tunnel policy — SSH/WireGuard; no paid remote-access vendor required."""
    tunnel = {
        "max_session_duration_minutes": int(payload.get("max_session_duration_minutes") or 60),
        "require_screen_recording": bool(payload.get("require_screen_recording", False)),
        "notify_tenant_admin_on_open": bool(payload.get("notify_tenant_admin_on_open", True)),
        "transport": "ssh-reverse-or-wireguard",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    existing = _read_guard_blob(school)
    existing["support_tunnel"] = tunnel
    _persist_guard_blob(school=school, blob=existing)
    return {"ok": True, "support_tunnel": tunnel}


def _read_guard_blob(school: Any | None) -> dict[str, Any]:
    if school is not None:
        return dict((getattr(school, "settings", None) or {}).get("observability_guard") or {})
    from apps.platform_runtime.models import RuntimeDefaults

    rd = RuntimeDefaults.objects.filter(pk=1).first()
    if rd is None:
        return {}
    return dict((rd.payload or {}).get("observability_guard") or {})
