"""Pilot defect loop — durable ORM rows + sorting and resolution policy helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
STATUS_ORDER = {
    "reported": 0,
    "triaged": 1,
    "in_progress": 2,
    "fixed": 3,
    "verified": 4,
    "deferred": 5,
}


def registry_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "data"
        / "pilot_defects_registry.json"
    )


def _defect_model_to_dict(d) -> dict[str, Any]:
    return {
        "id": str(d.pk),
        "title": d.title,
        "source_school_slug": d.source_school_slug,
        "severity": d.severity,
        "module": d.module,
        "owner": d.owner,
        "status": d.status,
        "linked_test": d.linked_test,
        "sot_batch": d.sot_batch,
        "root_cause": d.root_cause,
        "regression_risk": d.regression_risk,
        "documented_exception": d.documented_exception,
    }


def load_defects() -> list[dict[str, Any]]:
    """Load defects from DB; legacy JSON file is ignored unless DB empty (import once)."""
    from apps.platform_runtime.models import PilotDefect

    qs = list(PilotDefect.objects.all().order_by("-created_at"))
    if qs:
        return [_defect_model_to_dict(d) for d in qs]
    raw = json.loads(registry_path().read_text(encoding="utf-8"))
    rows = [r for r in (raw.get("defects") or []) if isinstance(r, dict)]
    return rows


def fixed_defect_has_proof(d: dict[str, Any]) -> bool:
    if d.get("status") not in ("fixed", "verified"):
        return True
    lt = (d.get("linked_test") or "").strip()
    if lt:
        return True
    ex = (d.get("documented_exception") or "").strip()
    return bool(ex)


def sort_defects_for_dashboard(defects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]):
        sev = SEVERITY_ORDER.get((row.get("severity") or "low").lower(), 9)
        st = STATUS_ORDER.get((row.get("status") or "").lower(), 9)
        return (sev, st, row.get("id") or "")

    return sorted(defects, key=key)


def file_pilot_defect(
    *,
    title: str,
    source_school_slug: str,
    severity: str,
    module: str,
    description: str = "",
) -> dict[str, Any]:
    """Create a durable PilotDefect row (manager intake form)."""
    from apps.platform_runtime.models import PilotDefect

    defect = PilotDefect.objects.create(
        title=(title or "").strip()[:240],
        source_school_slug=(source_school_slug or "").strip()[:120],
        severity=(severity or PilotDefect.Severity.MEDIUM).lower(),
        module=(module or "general").strip()[:64],
        status=PilotDefect.Status.REPORTED,
        root_cause=(description or "").strip()[:2000],
    )
    return _defect_model_to_dict(defect)


def export_defect_backlog_json(school_slug: str) -> Path:
    """Write redacted defect backlog snapshot for GEOS evidence."""
    from apps.platform_runtime.models import PilotDefect

    out_dir = Path(__file__).resolve().parents[2] / "var" / "evidence" / "geos-99" / "pilot" / school_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "defect_backlog.json"
    rows = []
    for defect in PilotDefect.objects.filter(source_school_slug=school_slug).order_by("-created_at"):
        rows.append(
            {
                "id": str(defect.pk),
                "title": defect.title,
                "severity": defect.severity,
                "module": defect.module,
                "status": defect.status,
                "sot_batch": defect.sot_batch or "",
            }
        )
    from datetime import datetime, timezone

    payload = {
        "schema_version": 1,
        "school_slug": school_slug,
        "recorded_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "evidence_status": "repo_complete" if rows else "intake_ready",
        "defects": rows,
        "notes": "Redacted export from PilotDefect ORM; no PII.",
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def dashboard_bucket(defects: list[dict[str, Any]]) -> dict[str, Any]:
    open_crit = [
        d
        for d in defects
        if (d.get("severity") or "").lower() == "critical"
        and (d.get("status") or "").lower() not in ("verified", "deferred")
    ]
    by_mod: dict[str, list[dict[str, Any]]] = {}
    for d in defects:
        m = d.get("module") or "unknown"
        by_mod.setdefault(m, []).append(d)
    await_verify = [
        d for d in defects if (d.get("status") or "").lower() == "fixed"
    ]
    no_test = [d for d in defects if not fixed_defect_has_proof(d)]
    return {
        "open_critical": sort_defects_for_dashboard(open_crit),
        "by_module": by_mod,
        "awaiting_verification": await_verify,
        "fixes_without_proof": no_test,
    }
