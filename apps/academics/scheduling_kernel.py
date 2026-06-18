"""Multi-campus scheduling wizard → constraint store + OR-Tools solver queue (OSS)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _scheduling_settings(school: Any) -> dict[str, Any]:
    settings = dict(getattr(school, "settings", None) or {})
    return dict(settings.get("scheduling") or {})


def _save_scheduling(school: Any, scheduling: dict[str, Any]) -> None:
    settings = dict(getattr(school, "settings", None) or {})
    settings["scheduling"] = scheduling
    school.settings = settings
    school.save(update_fields=["settings"])


def apply_resource_constraints(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    pairs = payload.get("pairs") or payload
    if isinstance(pairs, dict) and "pairs" not in payload:
        pairs = [{"key": k, "value": v} for k, v in pairs.items()]
    scheduling = _scheduling_settings(school)
    scheduling["resource_constraints"] = pairs if isinstance(pairs, list) else []
    scheduling["constraints_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_scheduling(school, scheduling)
    return {"ok": True, "constraint_count": len(scheduling["resource_constraints"])}


def apply_curricula_pathways(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    pathways = payload.get("value") or payload.get("pathways") or []
    if not isinstance(pathways, list):
        pathways = [pathways]
    scheduling = _scheduling_settings(school)
    scheduling["pathways"] = pathways
    scheduling["pathways_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_scheduling(school, scheduling)
    return {"ok": True, "pathways": pathways}


def configure_solver(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    enabled = payload.get("value")
    if enabled is None:
        enabled = payload.get("ai_conflict_solver", payload.get("enabled", True))
    if isinstance(enabled, dict):
        enabled = enabled.get("enabled", True)
    scheduling = _scheduling_settings(school)
    scheduling["ai_conflict_solver"] = bool(enabled)
    scheduling["solver_engine"] = "ortools-cp-sat-or-greedy-fallback"
    scheduling["solver_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_scheduling(school, scheduling)

    if scheduling["ai_conflict_solver"]:
        try:
            from apps.academics.tasks_scheduling import run_scheduling_solver_task

            run_scheduling_solver_task.delay(int(school.pk))
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "ai_conflict_solver": scheduling["ai_conflict_solver"]}


def apply_rollout(*, school: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if school is None:
        return {"ok": False}
    mode = payload.get("value") or payload.get("rollout_mode") or "pilot_campus"
    scheduling = _scheduling_settings(school)
    scheduling["rollout_mode"] = str(mode)
    scheduling["rollout_updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_scheduling(school, scheduling)
    return {"ok": True, "rollout_mode": mode}
