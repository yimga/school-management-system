#!/usr/bin/env python3
"""Academic operations workflow discovery audit (metadata-only, PII-free).

Writes:
  docs/generated/academic_operations_workflow_audit.json
  docs/generated/academic_operations_workflow_audit.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "academic_operations_workflow_audit.json"
MD_OUT = ROOT / "docs" / "generated" / "academic_operations_workflow_audit.md"

TARGET_APPS = (
    "people",
    "academics",
    "evals",
    "school_events",
    "schoolops",
    "student360",
    "reports",
    "emis",
    "requests",
    "communication",
)

FOCUSED_TEST_MODULES = [
    "apps.academics.tests.test_academics_critical_paths",
    "apps.academics.tests.test_academic_operations_repo_scope",
    "apps.evals.tests.test_grade_approval_workflow",
    "apps.evals.tests.test_bulk_grade_tenant_context",
    "apps.reports.tests.test_publish_term",
    "apps.reports.tests.test_export_integrity",
    "emis.tests",
    "apps.communication.tests.test_tenant_school_scope",
    "apps.platform_runtime.tests.test_offline_first_closure_slice",
    "apps.automation.tests.test_workflow_trigger_catalog_depth",
]


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _module_exists(rel: str) -> bool:
    return (ROOT / rel.replace("/", os.sep)).is_file()


def _count_pattern(app_rel: str, pattern: str) -> int:
    base = ROOT / app_rel
    if not base.is_dir():
        return 0
    total = 0
    rx = re.compile(pattern)
    for path in base.rglob("*.py"):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(rx.findall(text))
    return total


def _scan_unsafe_grade_json_blobs() -> list[dict]:
    """Flag academics/evals storing normalized grades in JSON blobs (anti-pattern)."""
    findings: list[dict] = []
    suspicious = re.compile(
        r"JSONField\s*\([^)]*(?:grades_blob|compressed_grades|bulk_marks_json)",
        re.IGNORECASE,
    )
    for app in ("apps/academics", "apps/evals"):
        base = ROOT / app
        if not base.is_dir():
            continue
        for path in base.rglob("models*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in suspicious.finditer(text):
                findings.append(
                    {
                        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "snippet": match.group(0)[:120],
                    }
                )
    return findings


def _app_installed(app: str, installed: list[str]) -> bool:
    if app in installed:
        return True
    for entry in installed:
        if f".{app}" in entry or entry.endswith(f".{app}"):
            return True
    return False


def _app_has_routes(app: str) -> bool:
    if app == "emis":
        return _module_exists("emis/urls.py")
    base = ROOT / "apps" / app
    if _module_exists(f"apps/{app}/urls.py"):
        return True
    if not base.is_dir():
        return False
    return any(base.glob("views*.py"))


def _app_has_services(app: str) -> bool:
    if app == "emis":
        return _module_exists("emis/services.py")
    base = ROOT / "apps" / app
    if _module_exists(f"apps/{app}/services.py"):
        return True
    if not base.is_dir():
        return False
    return any(
        p.name
        for p in base.iterdir()
        if p.is_file() and p.suffix == ".py" and "service" in p.name.lower()
    )


def build_audit() -> dict:
    _bootstrap_django()
    from django.conf import settings

    installed = list(getattr(settings, "INSTALLED_APPS", []) or [])
    app_rows = []
    for app in TARGET_APPS:
        app_rows.append(
            {
                "app": app,
                "installed": _app_installed(app, installed),
                "routes_surface": _app_has_routes(app),
                "services_surface": _app_has_services(app),
            }
        )

    query_hotspots = {
        "emis_select_related": _count_pattern("emis", r"\.select_related\("),
        "reports_select_related": _count_pattern("apps/reports", r"\.select_related\("),
        "academics_select_related": _count_pattern("apps/academics", r"\.select_related\("),
        "evals_select_related": _count_pattern("apps/evals", r"\.select_related\("),
        "people_select_related": _count_pattern("apps/people", r"\.select_related\("),
    }

    workflow_loop = {
        "offline_action_conflict_in_catalog": _module_exists(
            "apps/automation/workflow_trigger_catalog.py"
        ),
        "domain_event_bridge_maps_conflict": False,
        "offline_queue_emits_conflict_event": _module_exists(
            "apps/platform_runtime/offline_queue.py"
        ),
        "playbook_offline_conflict": _module_exists(
            "apps/automation/workflow_playbook_templates.py"
        ),
    }
    bridge = ROOT / "apps/automation/domain_event_bridge.py"
    if bridge.is_file():
        text = bridge.read_text(encoding="utf-8", errors="replace")
        workflow_loop["domain_event_bridge_maps_conflict"] = (
            '"offline_action_conflict": "offline_action_conflict"' in text
        )

    unsafe_json = _scan_unsafe_grade_json_blobs()
    tests_present = {mod: _module_exists(mod.replace(".", "/") + ".py") for mod in FOCUSED_TEST_MODULES}

    emis_gates = {
        "emis_export_service": _module_exists("emis/services.py"),
        "emis_field_mapping_model": _module_exists("emis/models.py"),
        "emis_tests": _module_exists("emis/tests.py"),
    }

    ui_surfaces = {
        "teacher_syllabus_hub": _module_exists("templates/academics/teacher_syllabus_hub.html"),
        "student360_views": _module_exists("apps/student360/views.py"),
        "reports_publish_term_tests": tests_present.get(
            "apps.reports.tests.test_publish_term", False
        ),
        "grade_approval_workflow_tests": tests_present.get(
            "apps.evals.tests.test_grade_approval_workflow", False
        ),
    }

    ok = (
        all(r["installed"] for r in app_rows)
        and all(r["routes_surface"] for r in app_rows)
        and not unsafe_json
        and workflow_loop["domain_event_bridge_maps_conflict"]
        and workflow_loop["offline_action_conflict_in_catalog"]
        and all(emis_gates.values())
        and all(tests_present.values())
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata_only": True,
        "pii_free": True,
        "target_apps": list(TARGET_APPS),
        "app_inventory": app_rows,
        "query_hotspots": query_hotspots,
        "workflow_loop": workflow_loop,
        "emis": emis_gates,
        "ui_surfaces": ui_surfaces,
        "unsafe_grade_json_blob_findings": unsafe_json,
        "focused_test_modules": FOCUSED_TEST_MODULES,
        "focused_tests_present": tests_present,
        "ok": ok,
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Academic operations workflow audit",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**OK:** {data['ok']}",
        "",
        "## Apps",
        "",
    ]
    for row in data["app_inventory"]:
        lines.append(
            f"- {row['app']}: installed={row['installed']} "
            f"routes={row['routes_surface']} services={row['services_surface']}"
        )
    lines.extend(["", "## Query hotspots (select_related counts)", ""])
    for key, val in sorted(data["query_hotspots"].items()):
        lines.append(f"- {key}: {val}")
    lines.extend(["", "## Workflow loop (P4)", ""])
    for key, val in sorted(data["workflow_loop"].items()):
        lines.append(f"- {key}: {val}")
    lines.extend(["", "## EMIS", ""])
    for key, val in sorted(data["emis"].items()):
        lines.append(f"- {key}: {val}")
    if data["unsafe_grade_json_blob_findings"]:
        lines.extend(["", "## Unsafe JSON grade blobs", ""])
        for f in data["unsafe_grade_json_blob_findings"]:
            lines.append(f"- {f['file']}: {f['snippet']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        args.write = True

    data = build_audit()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MD_OUT.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    print(f"OK: {data['ok']}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
