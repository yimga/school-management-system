#!/usr/bin/env python3
"""Workflow Progress Bus coverage gate — counts Celery tasks vs instrumentation."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIN_EXPLICIT_TRACKED = 8
MIN_REGISTRY_LIVE_KEYS = 9
MIN_MATRIX_PROMOTED_PATH_MATCHES = 38  # all promoted rows with entry_path must bind


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for base in (ROOT / "apps", ROOT / "services"):
        if not base.is_dir():
            continue
        out.extend(base.rglob("*.py"))
    return out


def _collect_shared_task_names() -> set[str]:
    names: set[str] = set()
    for path in _iter_py_files():
        if "migrations" in path.parts or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                    if dec.func.id != "shared_task":
                        continue
                elif isinstance(dec, ast.Name) and dec.id == "shared_task":
                    pass
                else:
                    continue
                name_kw = None
                for kw in getattr(dec, "keywords", []) or []:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        name_kw = str(kw.value.value)
                if name_kw:
                    names.add(name_kw)
                else:
                    names.add(node.name)
    return names


def main() -> int:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.platform_runtime.workflow_celery_bridge import (
        _EXPLICIT_CELERY_TASKS,
        _WORKFLOW_CELERY_DENYLIST,
        _should_track_celery_task,
    )
    from apps.platform_runtime.workflow_registry import WORKFLOWS

    live_keys = {
        k
        for k in WORKFLOWS
        if k.startswith(
            (
                "tenant_school_",
                "migration_bundle_",
                "evals_",
                "orchestration_",
            )
        )
    }

    all_tasks = _collect_shared_task_names()
    auto_tracked = {
        n
        for n in all_tasks
        if _should_track_celery_task(type("_T", (), {"name": n})(), name=n)
    }

    failures: list[str] = []
    if len(_EXPLICIT_CELERY_TASKS) < MIN_EXPLICIT_TRACKED:
        failures.append(
            f"explicit celery tasks {len(_EXPLICIT_CELERY_TASKS)} < {MIN_EXPLICIT_TRACKED}"
        )
    if len(live_keys) < MIN_REGISTRY_LIVE_KEYS:
        failures.append(f"registry live keys {len(live_keys)} < {MIN_REGISTRY_LIVE_KEYS}")

    required_explicit = {
        "schools.provision_school_task",
        "migration_cloud.apply_bundle",
        "migration_cloud.advance_bundle",
        "evals.process_bulk_grades",
    }
    missing = required_explicit - _EXPLICIT_CELERY_TASKS
    if missing:
        failures.append(f"missing explicit celery entries: {sorted(missing)}")

    from django.test import RequestFactory

    from apps.platform_runtime.workflow_guidance import (
        normalize_path_for_workflow_registry,
        resolve_workflow_for_entry_path,
        resolve_workflow_for_route,
    )

    rf = RequestFactory()
    matrix_paths = 0
    matrix_matched = 0
    matrix_unmatched: list[str] = []
    for key, defn in WORKFLOWS.items():
        if getattr(defn, "source", "") != "matrix-promoted":
            continue
        entry_path = getattr(defn, "entry_path", None) or ""
        if not entry_path:
            continue
        matrix_paths += 1
        req = rf.post(entry_path)
        resolved = resolve_workflow_for_route(req)
        if resolved is not None and resolved.key == key:
            matrix_matched += 1
            continue
        tenant_path = f"/t/demo-school{normalize_path_for_workflow_registry(entry_path)}"
        if tenant_path != entry_path:
            req_tenant = rf.post(tenant_path)
            resolved_tenant = resolve_workflow_for_route(req_tenant)
            if resolved_tenant is not None and resolved_tenant.key == key:
                matrix_matched += 1
                continue
        if resolve_workflow_for_entry_path(entry_path) is None:
            matrix_unmatched.append(key)

    if matrix_matched < MIN_MATRIX_PROMOTED_PATH_MATCHES:
        failures.append(
            f"matrix-promoted entry_path matches {matrix_matched}/{matrix_paths} "
            f"(min {MIN_MATRIX_PROMOTED_PATH_MATCHES}); unmatched sample: "
            f"{matrix_unmatched[:5]}"
        )

    if failures:
        print("WORKFLOW_PROGRESS_COVERAGE_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        print(f"  shared_task names discovered: {len(all_tasks)}")
        print(f"  auto-tracked by celery bridge: {len(auto_tracked)}")
        print(f"  denylisted: {len(_WORKFLOW_CELERY_DENYLIST)}")
        return 1

    print("WORKFLOW_PROGRESS_COVERAGE_PASS")
    print(f"  shared_task names: {len(all_tasks)}")
    print(f"  auto-tracked (generic celery.*): {len(auto_tracked)}")
    print(f"  explicit step-tracked: {len(_EXPLICIT_CELERY_TASKS)}")
    print(f"  registry live lifecycle keys: {len(live_keys)}")
    print(f"  matrix-promoted entry_path bound: {matrix_matched}/{matrix_paths}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
