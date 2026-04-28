# -*- coding: utf-8 -*-
"""
School infrastructure / blueprint templates (AWS-style): registry JSON + platform pack catalog.

Reads pack manifests from disk without importing apps.marketplace (tenant-safe discovery).
Apply/rollback remains platform-governed; Studio exposes preview, validation, and honest capability flags.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_REQUIRED_PACK_KEYS = frozenset(
    {
        "pack_key",
        "school_type",
        "modules",
        "workflows",
        "dashboards",
        "policies",
        "theme",
        "required_apps",
        "version",
    }
)


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def blueprint_dir() -> Path:
    return _repo_root() / "blueprint"


def platform_pack_catalog_path() -> Path:
    return _repo_root() / "apps" / "marketplace" / "data" / "platform_pack_catalog.json"


@lru_cache(maxsize=1)
def load_registry_index() -> dict[str, Any]:
    path = blueprint_dir() / "registry.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if int(raw.get("schema_version") or 0) < 1:
        raise ValueError("blueprint/registry.json schema_version >= 1 required")
    return raw


def load_pack_catalog_from_disk() -> dict[str, Any]:
    """Same JSON as marketplace catalog; loaded via filesystem to avoid importing marketplace."""
    path = platform_pack_catalog_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if int(raw.get("schema_version") or 0) < 1:
        raise ValueError("platform_pack_catalog: schema_version >= 1 required")
    return raw


def validate_pack_catalog_entries(data: dict[str, Any] | None) -> list[str]:
    """Structural validation aligned with apps.marketplace.pack_registry.validate_platform_pack_catalog."""
    if not isinstance(data, dict):
        return ["catalog root must be an object"]
    w: list[str] = []
    wf = data.get("workflow_packs") or []
    db = data.get("dashboard_packs") or []
    tp = data.get("theme_packs") or []
    for entries, kind in (
        (wf, "workflow_packs"),
        (db, "dashboard_packs"),
        (tp, "theme_packs"),
    ):
        if not isinstance(entries, list):
            w.append(f"{kind} must be a list")
            continue
        for i, row in enumerate(entries):
            if not isinstance(row, dict):
                w.append(f"{kind}[{i}] is not an object")
                continue
            missing = sorted(_REQUIRED_PACK_KEYS - set(row.keys()))
            if missing:
                w.append(f"{kind}[{i}] missing keys: {', '.join(missing)}")
    return w


def _pack_maps(catalog: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    wf: dict[str, dict] = {}
    db: dict[str, dict] = {}
    tp: dict[str, dict] = {}
    for row in catalog.get("workflow_packs") or []:
        if isinstance(row, dict) and row.get("pack_key"):
            wf[row["pack_key"]] = row
    for row in catalog.get("dashboard_packs") or []:
        if isinstance(row, dict) and row.get("pack_key"):
            db[row["pack_key"]] = row
    for row in catalog.get("theme_packs") or []:
        if isinstance(row, dict) and row.get("pack_key"):
            tp[row["pack_key"]] = row
    return wf, db, tp


def load_school_template(template_key: str) -> dict[str, Any]:
    key = (template_key or "").strip()
    path = blueprint_dir() / "school_templates" / f"{key}.json"
    if not path.is_file():
        raise FileNotFoundError(f"school template not found: {key}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_school_template_keys() -> list[str]:
    idx = load_registry_index()
    keys = idx.get("school_templates")
    if isinstance(keys, list):
        return [str(k) for k in keys]
    return sorted(
        p.stem for p in (blueprint_dir() / "school_templates").glob("*.json")
    )


def list_school_template_summaries() -> list[dict[str, Any]]:
    out = []
    for key in list_school_template_keys():
        try:
            t = load_school_template(key)
            out.append(
                {
                    "template_key": t.get("template_key") or key,
                    "display_name": t.get("display_name") or key,
                    "school_type": t.get("school_type") or "",
                    "version": t.get("version") or "",
                    "description": (t.get("description") or "")[:280],
                }
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            logger.debug("school template summary skip %s: %s", key, e)
    return out


def _installed_package_hints(school) -> set[str]:
    """Lowercase hints from InstalledPackage.package_id for dependency surfacing."""
    if school is None:
        return set()
    try:
        from apps.packages.models import InstalledPackage

        hints: set[str] = set()
        for row in InstalledPackage.objects.filter(school=school, is_active=True).only(
            "package_id"
        ):
            pid = (row.package_id or "").lower()
            hints.add(pid)
            for token in pid.replace("-", "_").split("_"):
                if len(token) > 2:
                    hints.add(token)
        return hints
    except Exception:
        return set()


def _dependency_check(school, template: dict[str, Any]) -> dict[str, Any]:
    required = template.get("required_apps") or []
    if not isinstance(required, list):
        required = []
    hints = _installed_package_hints(school)
    missing: list[str] = []
    notes: list[str] = []
    for app in required:
        a = (app or "").strip().lower()
        if not a:
            continue
        if hints and any(a in h or h.startswith(a) for h in hints):
            continue
        missing.append(app)
    if missing:
        notes.append(
            "Some required modules have no matching installed package record for this tenant; "
            "confirm entitlements with your platform administrator."
        )
    return {
        "required_apps": required,
        "possibly_missing": missing,
        "notes": notes,
        "used_installed_hints": bool(hints),
    }


def _tenant_blueprint_snapshot(school) -> dict[str, Any] | None:
    if school is None:
        return None
    try:
        from apps.policies.models import TenantBlueprint

        tb = (
            TenantBlueprint.objects.filter(school=school)
            .select_related("applied_pack")
            .first()
        )
        if not tb or not tb.applied_pack:
            return None
        pack = tb.applied_pack
        snap = pack.policy_snapshot if isinstance(pack.policy_snapshot, dict) else {}
        return {
            "applied_pack_slug": pack.slug,
            "applied_pack_version": pack.version or "",
            "policy_snapshot_keys": sorted(snap.keys())[:40],
            "policy_snapshot_size": len(snap),
        }
    except Exception:
        return None


def compute_infrastructure_diff(
    current: dict[str, Any] | None, proposed: dict[str, Any]
) -> list[dict[str, Any]]:
    """Lightweight diff rows for preview (no DB mutation)."""
    rows: list[dict[str, Any]] = []
    cur_ver = (current or {}).get("applied_pack_version") or ""
    prop_ver = proposed.get("template_version") or ""
    if cur_ver != prop_ver:
        rows.append(
            {
                "aspect": "blueprint_version_reference",
                "before": cur_ver or "(none)",
                "after": prop_ver or "(template)",
            }
        )
    cur_keys = set((current or {}).get("policy_snapshot_keys") or [])
    prop_modules: set[str] = set()
    for section in ("resolved_workflow_packs", "resolved_dashboard_packs", "resolved_theme_packs"):
        for row in proposed.get(section) or []:
            if isinstance(row, dict):
                for m in row.get("modules") or []:
                    prop_modules.add(str(m))
    if prop_modules:
        rows.append(
            {
                "aspect": "catalog_modules_union",
                "before": f"{len(cur_keys)} policy keys" if current else "(no applied pack)",
                "after": ", ".join(sorted(prop_modules))[:500],
            }
        )
    caps = proposed.get("capabilities") or {}
    rows.append(
        {
            "aspect": "tenant_safe_apply",
            "before": "n/a",
            "after": "enabled"
            if caps.get("tenant_safe_apply")
            else "disabled (platform apply only)",
        }
    )
    rows.append(
        {
            "aspect": "rollback",
            "before": current.get("applied_pack_slug") if current else "",
            "after": "available"
            if caps.get("rollback_supported")
            else "disabled unless platform enables rollback",
        }
    )
    return rows


def build_infrastructure_preview(school, template_key: str) -> dict[str, Any]:
    """Full preview payload for API and Launch Studio."""
    catalog = load_pack_catalog_from_disk()
    catalog_warnings = validate_pack_catalog_entries(catalog)
    wf_map, db_map, tp_map = _pack_maps(catalog)

    template = load_school_template(template_key)
    w_keys = template.get("workflow_pack_keys") or []
    d_keys = template.get("dashboard_pack_keys") or []
    t_keys = template.get("theme_pack_keys") or []

    unresolved: list[str] = []
    resolved_wf: list[dict[str, Any]] = []
    resolved_db: list[dict[str, Any]] = []
    resolved_tp: list[dict[str, Any]] = []

    for k in w_keys:
        if k in wf_map:
            resolved_wf.append(wf_map[k])
        else:
            unresolved.append(f"workflow:{k}")
    for k in d_keys:
        if k in db_map:
            resolved_db.append(db_map[k])
        else:
            unresolved.append(f"dashboard:{k}")
    for k in t_keys:
        if k in tp_map:
            resolved_tp.append(tp_map[k])
        else:
            unresolved.append(f"theme:{k}")

    current = _tenant_blueprint_snapshot(school)
    proposed = {
        "template_key": template.get("template_key"),
        "template_version": template.get("version"),
        "resolved_workflow_packs": resolved_wf,
        "resolved_dashboard_packs": resolved_db,
        "resolved_theme_packs": resolved_tp,
        "capabilities": template.get("capabilities") or {},
    }
    diff_rows = compute_infrastructure_diff(current, proposed)

    dep = _dependency_check(school, template)

    prev_ref = template.get("previous_version_ref")

    install_preview = {
        "label": (template.get("display_name") or template_key) + " (install preview)",
        "resolved_workflow_keys": [r.get("pack_key") for r in resolved_wf if r.get("pack_key")],
        "resolved_dashboard_keys": [r.get("pack_key") for r in resolved_db if r.get("pack_key")],
        "resolved_theme_keys": [r.get("pack_key") for r in resolved_tp if r.get("pack_key")],
        "catalog_resolves_cleanly": len(unresolved) == 0 and not catalog_warnings,
        "required_apps": dep.get("required_apps") or [],
        "possibly_missing_modules": dep.get("possibly_missing") or [],
    }

    return {
        "ok": len(unresolved) == 0 and not catalog_warnings,
        "template_key": template_key,
        "template": template,
        "catalog_warnings": catalog_warnings,
        "unresolved_pack_keys": unresolved,
        "resolved_workflow_packs": resolved_wf,
        "resolved_dashboard_packs": resolved_db,
        "resolved_theme_packs": resolved_tp,
        "current_blueprint_reference": current,
        "previous_version_ref": prev_ref,
        "diff_rows": diff_rows,
        "install_preview": install_preview,
        "dependency_check": dep,
        "rollback_supported": bool((template.get("capabilities") or {}).get("rollback_supported")),
        "tenant_safe_apply": bool(
            (template.get("capabilities") or {}).get("tenant_safe_apply")
        ),
        "preview_diff_supported": bool(
            (template.get("capabilities") or {}).get("preview_diff_supported", True)
        ),
    }


def get_infrastructure_context_for_shell(request) -> dict[str, Any]:
    """Template picker + honesty flags for Launch Studio shell."""
    summaries = list_school_template_summaries()
    catalog_ok = len(validate_pack_catalog_entries(load_pack_catalog_from_disk())) == 0
    school = getattr(request, "school", None)
    current = _tenant_blueprint_snapshot(school)
    return {
        "school_template_summaries": summaries,
        "platform_catalog_valid": catalog_ok,
        "current_blueprint_reference": current,
    }


def get_automation_studio_environment(request) -> dict[str, Any]:
    """
    Staging vs production strip + workflow simulation / publish / rollback readiness hints.
    Rollback stays conservative: True only when session stores prior preview payload (no fake paths).
    """
    school = getattr(request, "school", None)
    staging_count = 0
    production_count = 0
    try:
        from apps.packages.models import InstalledPackage

        if school:
            for row in InstalledPackage.objects.filter(school=school, is_active=True).only(
                "apply_stage"
            ):
                if row.apply_stage == "production":
                    production_count += 1
                else:
                    staging_count += 1
    except Exception:
        pass

    simulation_ready = True
    try:
        from apps.runtime_blueprints.models import WorkflowPack

        simulation_ready = WorkflowPack.objects.filter(is_active=True).exists()
    except Exception:
        simulation_ready = False

    publish_ready = production_count > 0 or staging_count == 0
    rollback_available = bool(request.session.get("studio_workflow_preview_previous"))

    detail_staging = (
        f"{staging_count} installed package(s) not marked production; "
        f"{production_count} in production."
        if school
        else "Select a school to evaluate package stages."
    )

    return {
        "automation_environment": {
            "staging_package_count": staging_count,
            "production_package_count": production_count,
            "staging_vs_production_detail": detail_staging,
            "workflow_simulation_ready": simulation_ready,
            "publish_readiness": {
                "ready": publish_ready,
                "detail": "Production-stage packages present or no staged installs detected.",
            },
            "rollback_readiness": {
                "available": rollback_available,
                "detail": "Rollback requires a recorded workflow preview snapshot or governed rollback APIs.",
            },
        },
        "automation_simulation_summary": (
            "Simulation available from Workflow center when workflow packs exist."
            if simulation_ready
            else "No active workflow packs detected; simulation is limited."
        ),
    }


def catalog_pack_rows_for_blueprints_page(limit: int = 24) -> dict[str, Any]:
    """Flatten catalog into rows for SiteConfig blueprint discovery (read-only)."""
    catalog = load_pack_catalog_from_disk()
    warnings = validate_pack_catalog_entries(catalog)
    rows: list[dict[str, Any]] = []
    for key in ("workflow_packs", "dashboard_packs", "theme_packs"):
        for row in catalog.get(key) or []:
            if len(rows) >= limit:
                break
            if isinstance(row, dict):
                r = dict(row)
                r["_catalog_section"] = key
                rows.append(r)
        if len(rows) >= limit:
            break
    return {"rows": rows[:limit], "warnings": warnings, "catalog_ok": len(warnings) == 0}
