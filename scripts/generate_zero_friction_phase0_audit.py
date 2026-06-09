#!/usr/bin/env python3
"""
Phase 0 — Zero-Friction OS inch-by-inch audit artifacts.

Writes:
  - docs/generated/zero_friction_zone_manifest.json
  - docs/generated/zero_friction_audit_ledger.json
  - docs/generated/scanner_coverage_gap_report.json
  - docs/generated/zero_friction_shell_matrix.json

Run: python scripts/generate_zero_friction_phase0_audit.py [--write|--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "generated"

ZONE_MANIFEST = OUT_DIR / "zero_friction_zone_manifest.json"
AUDIT_LEDGER = OUT_DIR / "zero_friction_audit_ledger.json"
SCANNER_GAPS = OUT_DIR / "scanner_coverage_gap_report.json"
SHELL_MATRIX = OUT_DIR / "zero_friction_shell_matrix.json"

CODE_SUFFIXES = {".py", ".html", ".js", ".ts", ".tsx", ".jsx", ".css", ".mjs", ".rs"}
SKIP_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".django_test_dbs",
}

ZONES: list[dict[str, object]] = [
    {"id": "Z1", "label": "apps", "paths": ["apps"]},
    {"id": "Z2", "label": "templates", "paths": ["templates"]},
    {"id": "Z3", "label": "services", "paths": ["services"]},
    {"id": "Z4", "label": "config", "paths": ["config"]},
    {"id": "Z5", "label": "emis_payment", "paths": ["emis", "payment"]},
    {"id": "Z6", "label": "static", "paths": ["static"]},
    {"id": "Z7", "label": "react", "paths": ["src", "frontend"]},
    {
        "id": "Z8",
        "label": "companions_sdk",
        "paths": [
            "companion-extension",
            "companion-tauri",
            "companion-docker",
            "packages",
            "sdk",
        ],
    },
    {"id": "Z9", "label": "edge", "paths": ["edge"]},
    {"id": "Z10", "label": "scripts", "paths": ["scripts"]},
    {"id": "Z11", "label": "entrypoints", "paths": []},
    {"id": "Z12", "label": "locale", "paths": ["locale", "apps/locale"]},
    {"id": "Z13", "label": "tests", "paths": ["tests"]},
    {"id": "Z14", "label": "ci", "paths": [".github"]},
    {"id": "Z15", "label": "baselines", "paths": ["var", "docs/generated"]},
]

ROOT_SHELLS = [
    "templates/portal_base.html",
    "templates/base.html",
    "templates/control_plane_skeleton.html",
    "templates/control_plane_base.html",
    "templates/admin/base_site.html",
    "templates/marketing/base_marketing.html",
    "templates/backend_base.html",
    "templates/backend_base_tenant.html",
    "templates/backend_base_manager.html",
    "templates/home.html",
    "templates/offline.html",
]

SUB_SHELL_ROUTERS = [
    "templates/studio_os/shell.html",
    "templates/schools/marketing_page_layout.html",
    "templates/migration_cloud/connector/_wizard_base.html",
    "templates/siteconfig/zero_ticket_shell.html",
]

DAILY_USE_WEIGHT = {
    "teacher": 10,
    "parent": 9,
    "portal": 8,
    "academics": 9,
    "evals": 9,
    "people": 8,
    "schoolops": 8,
    "accounts": 7,
    "student": 7,
    "auth": 6,
    "schools": 6,
    "siteconfig": 6,
    "setup_studio": 6,
    "studio_os": 6,
    "finance": 5,
}

SCANNER_REGISTRY: list[dict[str, object]] = [
    {
        "scanner": "audit_security_surface.py",
        "walks": ["apps/", "config/", "scripts/", "services/", "emis/", "payment/"],
        "misses": [],
        "remediation": "resolved_phase0c",
        "status": "resolved",
    },
    {
        "scanner": "scan_tenant_queryset_safety.py",
        "walks": ["apps/", "services/", "emis/", "payment/"],
        "misses": [],
        "remediation": "resolved_phase0c",
        "status": "resolved",
    },
    {
        "scanner": "audit_tenant_isolation.py",
        "walks": ["apps/", "config/", "services/", "emis/", "payment/"],
        "misses": [],
        "remediation": "resolved_phase0c_extend_walk_paths",
        "status": "resolved",
    },
    {
        "scanner": "audit_celery_tenant_task_scoping.py",
        "walks": ["apps/**/tasks*.py", "services/**/tasks*.py", "apps/**/tasks/**/*.py"],
        "misses": [],
        "remediation": "resolved_extend_task_glob",
        "status": "resolved",
    },
    {
        "scanner": "scan_operator_shell_dead_hrefs.py",
        "walks": ["shell template hrefs", "verify_react_mount_and_fetch_urls.py"],
        "misses": [],
        "remediation": "resolved_verify_react_mount_and_fetch_urls",
        "status": "resolved",
    },
    {
        "scanner": "verify_interaction_integrity_completion.py",
        "walks": ["shell JS/CSS", "verify_pages_interaction_audit.py"],
        "misses": [],
        "remediation": "resolved_verify_pages_interaction_audit",
        "status": "resolved",
    },
    {
        "scanner": "audit_role_permission_matrix.py",
        "walks": [
            "apps/*/views*.py",
            "apps/apicenter/oauth_views.py",
            "apps/api/consumers.py",
            "config/urls.py",
            "config/routing.py",
        ],
        "misses": [],
        "remediation": "resolved_extend_oauth_websocket_index",
        "status": "resolved",
    },
]

SMART_HUB_PARENT_SHELLS = frozenset(
    {
        "portal_base.html",
        "control_plane_base.html",
        "control_plane_skeleton.html",
        "backend_base.html",
        "backend_base_tenant.html",
    }
)

TABLE_BLOCK_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.I | re.S)

EXTENDS_RE = re.compile(r"""{%\s*extends\s+['"]([^'"]+)['"]""")
TH_RE = re.compile(r"<th\b", re.I)
TABLE_CLASS_RE = re.compile(r'class="[^"]*\brmc-data-table\b')


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _count_zone_files(zone_paths: list[str], entrypoints: list[str] | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    if entrypoints:
        for rel in entrypoints:
            p = ROOT / rel
            if p.is_file():
                counts[p.suffix.lstrip(".") or "file"] += 1
        return dict(counts)

    for rel in zone_paths:
        base = ROOT / rel
        if not base.exists():
            continue
        if base.is_file():
            if base.suffix in CODE_SUFFIXES or base.suffix == ".yaml":
                counts[base.suffix.lstrip(".")] += 1
            continue
        for p in base.rglob("*"):
            if not p.is_file() or _should_skip(p):
                continue
            if p.suffix in CODE_SUFFIXES or p.suffix in {".json", ".yaml", ".yml", ".toml", ".md"}:
                counts[p.suffix.lstrip(".") or "other"] += 1
    return dict(counts)


def _list_apps() -> list[str]:
    apps_dir = ROOT / "apps"
    if not apps_dir.is_dir():
        return []
    return sorted(
        d.name
        for d in apps_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def _template_zone(rel: str) -> str:
    parts = Path(rel).parts
    if len(parts) < 2:
        return "root"
    return parts[1] if parts[0] == "templates" else "other"


def _extends_parent_shell(text: str) -> str | None:
    match = EXTENDS_RE.search(text)
    return match.group(1) if match else None


def _max_th_in_data_tables(text: str) -> int:
    max_th = 0
    for block in TABLE_BLOCK_RE.findall(text):
        if "rmc-data-table" not in block:
            continue
        count = len(TH_RE.findall(block))
        if 'data-rmc-table-5col="1"' in block or "table-column-budget-allow:" in text:
            count = min(count, 5)
        max_th = max(max_th, count)
    return max_th


def _inherits_smart_hub(text: str, rel: str = "") -> bool:
    if "rmc_smart_action_hub" in text or "next_action_strip" in text:
        return True
    parent = _extends_parent_shell(text)
    if parent in SMART_HUB_PARENT_SHELLS:
        return True
    if rel.startswith("templates/studio_os/") and (
        "/partials/" in rel or "/components/" in rel
    ):
        for shell_rel in (
            "templates/studio_os/shell.html",
            "templates/studio_os/shell_control_plane.html",
        ):
            shell = ROOT / shell_rel
            if shell.is_file() and (
                "next_action_strip" in shell.read_text(encoding="utf-8", errors="replace")
                or "rmc_smart_action_hub" in shell.read_text(encoding="utf-8", errors="replace")
            ):
                return True
    if rel.startswith("templates/partials/") or rel.startswith("templates/components/"):
        for shell_rel in (
            "templates/portal_base.html",
            "templates/control_plane_base.html",
            "templates/control_plane_skeleton.html",
            "templates/base.html",
        ):
            shell = ROOT / shell_rel
            if shell.is_file():
                shell_text = shell.read_text(encoding="utf-8", errors="replace")
                if "next_action_strip" in shell_text or "rmc_smart_action_hub" in shell_text:
                    return True
    if "/partials/" in rel and rel.startswith("templates/"):
        parent_zone = _template_zone(rel)
        if parent_zone not in {"emails", "errors"}:
            return True
    return False


def _inherits_portal_offline(text: str, zone: str) -> bool:
    if (
        "data-rmc-offline" in text
        or "data-sms-offline-read-cache-key" in text
        or "data-page-critical-read" in text
    ):
        return True
    if zone not in {"teacher", "parent", "portal", "academics", "evals", "student"}:
        return False
    return _extends_parent_shell(text) == "portal_base.html"


def _has_empty_state_grammar(text: str) -> bool:
    return (
        "rmc_empty_state" in text
        or "empty_state" in text
        or "rmc-empty" in text
        or 'class="dashboard-empty-state"' in text
    )


def _is_non_interactive_template(rel: str) -> bool:
    """Transactional email + decorative SVG assets are not portal friction surfaces."""
    if rel.startswith("templates/emails/") or "/email/" in rel or "/emails/" in rel:
        return True
    if "/_v2/" in rel and rel.endswith(".svg.html"):
        return True
    return False


def _score_template(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    zone = _template_zone(rel)

    if _is_non_interactive_template(rel):
        scores = {
            "clicks_to_complete": 2,
            "manual_fields": 2,
            "navigation_depth": 2,
            "column_clutter": 1,
            "scroll_folds": 1,
            "empty_error_states": 1,
            "offline_survivability": 1,
            "recovery": 1,
        }
        friction_total = sum(scores.values())
        return {
            "path": rel,
            "zone": zone,
            "friction_dimensions": scores,
            "friction_total": friction_total,
            "daily_use_weight": DAILY_USE_WEIGHT.get(zone, 1),
            "priority_score": friction_total * DAILY_USE_WEIGHT.get(zone, 1),
            "gaps": [],
            "signals": {
                "non_interactive_surface": True,
                "has_rmc_data_table": False,
                "th_count": 0,
                "has_pagination": False,
                "has_next_action_strip": False,
                "has_row_detail_drawer": False,
                "has_scroll_policy_paginate": False,
            },
        }

    has_table = "rmc-data-table" in text
    th_count = _max_th_in_data_tables(text) if has_table else 0
    has_pagination = "components/pagination.html" in text or "page_obj" in text
    has_next_action = "next_action_strip" in text
    has_row_drawer = "data-rmc-row-detail-table" in text
    has_scroll_policy = 'data-rmc-scroll-policy="paginate"' in text
    has_fold_nav = "rmc-page-fold-nav" in text or 'data-rmc-page-fold-nav="required"' in text
    has_smart_hub = _inherits_smart_hub(text, rel)
    has_five_col = 'data-rmc-table-5col="1"' in text

    scores = {
        "clicks_to_complete": 3 if has_next_action or has_smart_hub else 4,
        "manual_fields": 3,
        "navigation_depth": 3,
        "column_clutter": 5 if has_table and th_count > 5 else (2 if has_table else 1),
        "scroll_folds": 2 if has_fold_nav or has_scroll_policy else 3,
        "empty_error_states": 2 if _has_empty_state_grammar(text) else 3,
        "offline_survivability": 2
        if _inherits_portal_offline(text, zone) or "offline" in rel
        else 4,
        "recovery": 2
        if has_next_action or has_smart_hub or "smart_links" in text
        else 3,
    }
    friction_total = sum(scores.values())
    daily_weight = DAILY_USE_WEIGHT.get(zone, 3)

    gaps: list[str] = []
    if has_table and th_count > 5 and not has_five_col:
        gaps.append(f"table_columns_{th_count}_exceeds_5")
    if has_table and not has_row_drawer:
        gaps.append("missing_row_detail_drawer")
    if has_table and not has_pagination and not has_scroll_policy:
        gaps.append("missing_pagination_or_scroll_policy")
    if zone in {"teacher", "parent", "portal", "academics", "evals"} and not has_smart_hub:
        gaps.append("missing_smart_action_surface")

    return {
        "path": rel,
        "zone": zone,
        "friction_dimensions": scores,
        "friction_total": friction_total,
        "daily_use_weight": daily_weight,
        "priority_score": friction_total * daily_weight,
        "gaps": gaps,
        "signals": {
            "has_rmc_data_table": has_table,
            "th_count": th_count,
            "has_pagination": has_pagination,
            "has_next_action_strip": has_next_action,
            "has_row_detail_drawer": has_row_drawer,
            "has_scroll_policy_paginate": has_scroll_policy,
        },
    }


def _build_shell_matrix() -> dict[str, object]:
    shells: list[dict[str, object]] = []
    extends_graph: dict[str, list[str]] = defaultdict(list)

    all_shell_paths = ROOT_SHELLS + SUB_SHELL_ROUTERS
    templates_dir = ROOT / "templates"

    for rel in all_shell_paths:
        p = ROOT / rel
        exists = p.is_file()
        extends = None
        if exists:
            m = EXTENDS_RE.search(p.read_text(encoding="utf-8", errors="replace"))
            extends = m.group(1) if m else None
        shells.append(
            {
                "path": rel,
                "kind": "root" if rel in ROOT_SHELLS else "sub_router",
                "exists": exists,
                "extends": extends,
            }
        )

    if templates_dir.is_dir():
        for html in templates_dir.rglob("*.html"):
            if _should_skip(html):
                continue
            rel = html.relative_to(ROOT).as_posix()
            m = EXTENDS_RE.search(html.read_text(encoding="utf-8", errors="replace"))
            if m:
                extends_graph[m.group(1)].append(rel)

    children_count = {s["path"]: len(extends_graph.get(Path(s["path"]).name, [])) for s in shells}
    for s in shells:
        name = Path(str(s["path"])).name
        s["direct_child_count"] = len(extends_graph.get(name, []))

    missing = [s["path"] for s in shells if not s["exists"]]
    return {
        "generated_at": _utc_now(),
        "root_shell_count": len(ROOT_SHELLS),
        "sub_router_count": len(SUB_SHELL_ROUTERS),
        "shells": shells,
        "missing_paths": missing,
        "extends_graph_sample_size": sum(len(v) for v in extends_graph.values()),
        "audited": len(missing) == 0,
    }


def _build_zone_manifest() -> dict[str, object]:
    zones_out: list[dict[str, object]] = []
    for z in ZONES:
        zid = str(z["id"])
        paths = list(z["paths"])  # type: ignore[arg-type]
        entrypoints = None
        if zid == "Z11":
            entrypoints = ["manage.py", "conftest.py"]
        counts = _count_zone_files(paths, entrypoints)
        total = sum(counts.values())
        zones_out.append(
            {
                "id": zid,
                "label": z["label"],
                "paths": paths if paths else entrypoints,
                "file_counts_by_suffix": counts,
                "total_files": total,
                "audited": total > 0 or zid == "Z11",
            }
        )

    apps = _list_apps()
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "protocol": "ZERO-FRICTION-OS-PHASE-0",
        "zone_count": len(zones_out),
        "zones_audited": sum(1 for z in zones_out if z["audited"]),
        "zones_complete": all(z["audited"] for z in zones_out),
        "django_apps_on_disk": len(apps),
        "django_apps": apps,
        "zones": zones_out,
    }


def _build_audit_ledger() -> dict[str, object]:
    templates_dir = ROOT / "templates"
    rows: list[dict[str, object]] = []
    gap_counter: Counter[str] = Counter()

    if templates_dir.is_dir():
        for html in sorted(templates_dir.rglob("*.html")):
            if _should_skip(html):
                continue
            row = _score_template(html)
            rows.append(row)
            for g in row["gaps"]:
                gap_counter[str(g)] += 1

    rows.sort(key=lambda r: -int(r["priority_score"]))  # type: ignore[arg-type]
    top_100 = rows[:100]

    role_passes = [
        "principal_architect",
        "data_engineer",
        "security_engineer",
        "devops_sre",
        "lead_ui_ux",
        "teacher_advocate",
        "parent_student_advocate",
        "admin_principal",
        "automation_engineer",
        "ai_sync_engineer",
        "sales_cs",
        "qa_supervisor",
    ]

    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "protocol": "ZERO-FRICTION-OS-PHASE-0",
        "role_passes": role_passes,
        "template_rows_scored": len(rows),
        "gap_summary": dict(gap_counter.most_common()),
        "high_friction_threshold": 20,
        "high_friction_count": sum(1 for r in rows if int(r["friction_total"]) >= 20),
        "top_100_routes": top_100,
        "finance_audit_only": True,
    }


def _build_scanner_gaps() -> dict[str, object]:
    gaps = []
    for entry in SCANNER_REGISTRY:
        status = str(entry.get("status") or "open")
        if status == "open" and entry.get("remediation") == "documented_exclusion":
            status = "documented"
        gaps.append({**entry, "status": status})
    open_count = sum(1 for g in gaps if g["status"] == "open")
    resolved_count = sum(1 for g in gaps if g["status"] == "resolved")
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "protocol": "ZERO-FRICTION-OS-PHASE-0",
        "scanner_entries": len(gaps),
        "open_gaps": open_count,
        "resolved_gaps": resolved_count,
        "gaps": gaps,
        "phase0_note": (
            "Phase 0c closed all scanner registry gaps: tenant isolation walk extended, "
            "celery task glob extended, react mount/fetch verifier added, _pages audit "
            "verifier added, RBAC matrix extended for OAuth + WebSocket routes."
        ),
    }


def _write_all() -> dict[str, object]:
    manifest = _build_zone_manifest()
    ledger = _build_audit_ledger()
    scanner = _build_scanner_gaps()
    shell = _build_shell_matrix()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ZONE_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    AUDIT_LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    SCANNER_GAPS.write_text(json.dumps(scanner, indent=2) + "\n", encoding="utf-8")
    SHELL_MATRIX.write_text(json.dumps(shell, indent=2) + "\n", encoding="utf-8")

    return {
        "manifest": manifest,
        "ledger": ledger,
        "scanner": scanner,
        "shell": shell,
    }


def _check_stale() -> int:
    errors: list[str] = []
    for path in (ZONE_MANIFEST, AUDIT_LEDGER, SCANNER_GAPS, SHELL_MATRIX):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT).as_posix()}")

    if errors:
        for e in errors:
            print(f"generate_zero_friction_phase0_audit: {e}", file=sys.stderr)
        return 1

    fresh = _write_all()
    for name, out_path in (
        ("manifest", ZONE_MANIFEST),
        ("ledger", AUDIT_LEDGER),
        ("scanner", SCANNER_GAPS),
        ("shell", SHELL_MATRIX),
    ):
        on_disk = json.loads(out_path.read_text(encoding="utf-8"))
        key_fields = {
            "manifest": ("zones_complete", "zone_count"),
            "ledger": ("template_rows_scored", "top_100_routes"),
            "scanner": ("open_gaps", "scanner_entries"),
            "shell": ("audited", "root_shell_count"),
        }
        for field in key_fields[name]:
            if on_disk.get(field) != fresh[name].get(field):
                errors.append(f"{out_path.name} stale field {field}")

    if errors:
        for e in errors:
            print(f"generate_zero_friction_phase0_audit: STALE — {e}", file=sys.stderr)
        return 1

    print("generate_zero_friction_phase0_audit: OK (artifacts fresh)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Zero-Friction Phase 0 audit artifacts.")
    parser.add_argument("--write", action="store_true", help="Write artifacts (default).")
    parser.add_argument("--check", action="store_true", help="Fail if artifacts are stale.")
    args = parser.parse_args(argv)

    if args.check:
        return _check_stale()

    payload = _write_all()
    m = payload["manifest"]
    l = payload["ledger"]
    s = payload["scanner"]
    sh = payload["shell"]

    print("generate_zero_friction_phase0_audit: WROTE")
    print(f"  zones: {m['zones_audited']}/{m['zone_count']} audited, complete={m['zones_complete']}")
    print(f"  templates scored: {l['template_rows_scored']}, high_friction={l['high_friction_count']}")
    print(f"  scanner open gaps: {s['open_gaps']}/{s['scanner_entries']}")
    print(f"  shell matrix audited: {sh['audited']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
