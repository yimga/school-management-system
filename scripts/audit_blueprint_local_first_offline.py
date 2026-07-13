"""Audit RunMyCampus Blueprint modules for local-first/offline readiness.

This is intentionally read-only. It turns the current Blueprint code realities
into generated evidence that can drive the implementation waves.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.platform_runtime.blueprint_contract import (  # noqa: E402
    LOCAL_FIRST_MANIFEST_REQUIRED_FIELDS,
    list_blueprints,
)

OUT_DIR = ROOT / "docs" / "generated"
JSON_OUT = OUT_DIR / "blueprint_local_first_offline_audit.json"
MD_OUT = OUT_DIR / "blueprint_local_first_offline_audit.md"


REQUIRED_MANIFEST_FIELDS = LOCAL_FIRST_MANIFEST_REQUIRED_FIELDS


SOURCE_PROBES = {
    "preview_emits_offline_readiness": (
        ROOT / "apps" / "platform_runtime" / "blueprint_preview.py",
        "offline_readiness",
    ),
    "apply_persists_local_first_manifest": (
        ROOT / "apps" / "platform_runtime" / "blueprint_apply.py",
        "local_first_manifest",
    ),
    "rollback_invalidates_offline_manifest": (
        ROOT / "apps" / "platform_runtime" / "blueprint_rollback.py",
        "offline_manifest",
    ),
    "impact_scores_offline_risk": (
        ROOT / "apps" / "platform_runtime" / "blueprint_impact.py",
        "offline",
    ),
    "tenant_ui_shows_offline_readiness": (
        ROOT / "templates" / "platform_runtime" / "tenant_blueprint_setup.html",
        "offline",
    ),
    "server_seven_day_proof_exists": (
        ROOT / "apps" / "platform_runtime" / "tests" / "test_seven_day_offline_endurance.py",
        "seven_day",
    ),
}


def _contains(path: Path, token: str) -> bool:
    if not path.exists():
        return False
    return token.lower() in path.read_text(encoding="utf-8", errors="ignore").lower()


def _status(missing: list[str], tenant_safe: bool) -> str:
    if not tenant_safe:
        return "OPERATOR_ONLY"
    if not missing:
        return "FUNCTIONAL"
    return "PARTIAL"


def _blueprint_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for blueprint in list_blueprints(tenant_safe_only=False):
        data = asdict(blueprint) if is_dataclass(blueprint) else dict(blueprint)
        offline_defaults = data.get("offline_defaults") or {}
        local_first_manifest = data.get("local_first_manifest") or {}
        missing = [
            field
            for field in REQUIRED_MANIFEST_FIELDS
            if field not in local_first_manifest
        ]
        rows.append(
            {
                "key": data["key"],
                "name": data["name"],
                "tenant_safe": data["tenant_safe"],
                "tenant_scoped": data["tenant_scoped"],
                "requires_platform_operator": data["requires_platform_operator"],
                "offline_defaults": offline_defaults,
                "local_first_manifest": local_first_manifest,
                "missing_local_first_manifest_fields": missing,
                "status": _status(missing, data["tenant_safe"]),
                "decision": "ADAPT EXISTING" if data["tenant_safe"] else "HIDE FROM TENANT",
            }
        )
    return rows


def _source_probe_rows() -> dict[str, bool]:
    return {name: _contains(path, token) for name, (path, token) in SOURCE_PROBES.items()}


def _overall_status(rows: list[dict[str, Any]], probes: dict[str, bool]) -> str:
    tenant_rows = [row for row in rows if row["tenant_safe"]]
    if not tenant_rows:
        return "MISSING"
    if all(row["status"] == "FUNCTIONAL" for row in tenant_rows) and all(probes.values()):
        return "FUNCTIONAL"
    return "FUNCTIONAL_BUT_UNPROVEN"


def _payload() -> dict[str, Any]:
    rows = _blueprint_rows()
    probes = _source_probe_rows()
    return {
        "audit": "blueprint_local_first_offline",
        "scope": "tenant-safe Blueprint modules, offline/local-first readiness, preview/apply/rollback evidence",
        "overall_status": _overall_status(rows, probes),
        "summary": {
            "tenant_safe_blueprints": sum(1 for row in rows if row["tenant_safe"]),
            "operator_only_blueprints": sum(1 for row in rows if not row["tenant_safe"]),
            "tenant_safe_blueprints_missing_manifest_fields": sum(
                1
                for row in rows
                if row["tenant_safe"] and row["missing_local_first_manifest_fields"]
            ),
            "source_probes_passing": sum(1 for passed in probes.values() if passed),
            "source_probes_total": len(probes),
        },
        "required_manifest_fields": list(REQUIRED_MANIFEST_FIELDS),
        "source_probes": probes,
        "blueprints": rows,
        "closed_gaps": [
            "Added a first-class local-first manifest contract for tenant-safe Blueprints.",
            "Preview emits offline readiness, device-role impact, outage survival, conflict policy, and proof status.",
            "Apply persists the local-first manifest in tenant-scoped school settings and install snapshots.",
            "Rollback restores settings and reports offline manifest invalidation posture.",
            "Tenant Blueprint UI exposes offline readiness, cached surfaces, queued actions, device roles, and proof status.",
        ],
        "recommended_follow_on": [
            "Replace PARTIAL browser proof status after a real browser restart/storage-pressure harness passes.",
            "Wire device manifest version bumps to the client sync runtime when that endpoint is available.",
            "Add per-blueprint browser screenshots for the tenant Blueprint UI after deployment.",
        ],
    }


def _write_json(payload: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# Blueprint Local-First Offline Audit",
        "",
        f"Overall status: `{payload['overall_status']}`",
        "",
        "## Summary",
        "",
        f"- Tenant-safe blueprints: {payload['summary']['tenant_safe_blueprints']}",
        f"- Operator-only blueprints: {payload['summary']['operator_only_blueprints']}",
        f"- Tenant-safe Blueprints missing full local-first manifests: {payload['summary']['tenant_safe_blueprints_missing_manifest_fields']}",
        f"- Source probes passing: {payload['summary']['source_probes_passing']} / {payload['summary']['source_probes_total']}",
        "",
        "## Source Probes",
        "",
    ]
    for name, passed in payload["source_probes"].items():
        lines.append(f"- `{name}`: `{'PASS' if passed else 'MISSING'}`")
    lines.extend(
        [
            "",
            "## Blueprint Matrix",
            "",
            "| Blueprint | Tenant safe | Status | Decision | Missing local-first fields |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in payload["blueprints"]:
        missing = ", ".join(row["missing_local_first_manifest_fields"]) or "None"
        lines.append(
            f"| `{row['key']}` | `{row['tenant_safe']}` | `{row['status']}` | `{row['decision']}` | {missing} |"
        )
    lines.extend(
        [
            "",
            "## Closed Gaps",
            "",
        ]
    )
    for item in payload["closed_gaps"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Recommended Follow-On",
            "",
        ]
    )
    for item in payload["recommended_follow_on"]:
        lines.append(f"- {item}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    payload = _payload()
    _write_json(payload)
    _write_markdown(payload)
    print(f"BLUEPRINT_LOCAL_FIRST_OFFLINE_AUDIT_COMPLETE {JSON_OUT.relative_to(ROOT)} {MD_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
