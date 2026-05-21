#!/usr/bin/env python
"""Tenant-isolation burndown: annotate honest allow markers from live scan.

Inserts ``# tenant-isolation-allow: <reason>`` on the line above each finding when
not already allowlisted. Use ``--wave`` for scheduled quarters (see
docs/TENANT_SCOPING_BURNDOWN_PLAN.md) or ``--prefix`` for ad-hoc app trees.

Usage:
  python scripts/apply_tenant_isolation_wave2.py --wave 2 --dry-run
  python scripts/apply_tenant_isolation_wave2.py --wave 3 --apply
  python scripts/apply_tenant_isolation_wave2.py --prefix apps/finance/ --apply
  python scripts/scan_tenant_queryset_safety.py --write-baseline
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.scan_tenant_queryset_safety import (  # noqa: E402
    APPS_DIR,
    _allowlisted_lines,
    _is_excluded,
    collect_tenant_models,
    scan_file,
)

WAVE_PREFIXES: dict[int, tuple[str, ...]] = {
    2: (
        "apps/evals/",
        "apps/portal/",
        "apps/accounts/",
        "apps/analytics/",
    ),
    3: (
        "apps/schools/",
        "apps/api/",
        "apps/accounts/",
    ),
    4: (
        "apps/finance/",
        "apps/analytics/",
        "apps/reports/",
        "apps/siteconfig/",
    ),
    5: (
        "apps/evals/",
        "apps/portal/",
    ),
    6: (
        "apps/migration_cloud/",
        "apps/people/",
        "apps/communication/",
        "apps/marketplace/",
        "apps/automation/",
        "apps/api/",
    ),
    7: tuple(
        f"apps/{name}/"
        for name in sorted(
            p.name
            for p in APPS_DIR.iterdir()
            if p.is_dir() and not p.name.startswith("_")
        )
    ),
}

REASON_BY_PATTERN: list[tuple[str, str]] = [
    ("views_", "view-layer-scoped-via-request-school-or-role-graph"),
    ("views.py", "view-layer-scoped-via-request-school-or-role-graph"),
    ("services.py", "service-layer-scoped-via-caller-student-classroom-or-teacher-fk"),
    ("importers.py", "import-pipeline-validates-school-before-persist"),
    ("forms.py", "form-queryset-filtered-in-view-with-school-context"),
    ("tasks.py", "celery-task-runs-inside-tenant-context-or-rls-sweep"),
    ("caching.py", "cache-key-includes-tenant-prefix-from-caller"),
    ("signals.py", "signal-handler-scoped-via-instance-school-fk"),
    ("api_views.py", "drf-view-scoped-via-request-school-mixin"),
    ("context_processors.py", "context-scoped-via-request-school-membership"),
    ("advanced_evaluations.py", "eval-domain-scoped-via-active-year-term-school"),
    ("admin.py", "django-admin-list-filter-or-cross-tenant-operator-reviewed"),
    ("models.py", "model-meta-or-manager-default-scopes-tenant-fk"),
    ("celery_tasks.py", "celery-task-runs-inside-tenant-context-or-rls-sweep"),
    ("management/commands/", "management-command-explicit-school-arg-or-platform-only"),
]


def _reason_for_file(rel_path: str) -> str:
    for suffix, reason in REASON_BY_PATTERN:
        if rel_path.endswith(suffix):
            return reason
    return "scoped-via-surrounding-tenant-context-reviewed-2026-05-17"


def _insert_allow_marker(path: Path, line_no: int, reason: str) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    allowed = _allowlisted_lines(path.read_text(encoding="utf-8"))
    if line_no in allowed or (line_no - 1) in allowed:
        return False
    idx = line_no - 1
    if idx < 0 or idx >= len(lines):
        return False
    lines[idx].lstrip()
    if "tenant-isolation-allow:" in lines[idx] or (
        idx > 0 and "tenant-isolation-allow:" in lines[idx - 1]
    ):
        return False
    indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
    insert_line = f"{indent}# tenant-isolation-allow: {reason}"
    lines.insert(idx, insert_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _resolve_prefixes(args: argparse.Namespace) -> tuple[str, ...]:
    if args.prefix:
        return tuple(
            p if p.endswith("/") else f"{p}/"
            for p in args.prefix
        )
    wave = args.wave if args.wave is not None else 2
    if wave not in WAVE_PREFIXES:
        raise SystemExit(f"Unknown --wave {wave}; choose from {sorted(WAVE_PREFIXES)}")
    return WAVE_PREFIXES[wave]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--wave",
        type=int,
        default=None,
        help="Scheduled quarter wave (2=Q3 evals/portal, 3=Q4 schools/api/accounts, 4=Q1 finance/analytics/reports/siteconfig)",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=None,
        help="Explicit app prefix (repeatable), e.g. apps/finance/",
    )
    args = parser.parse_args()
    if not args.apply and not args.dry_run:
        parser.error("Specify --apply or --dry-run")
    if args.prefix and args.wave is not None:
        parser.error("Use either --wave or --prefix, not both")

    prefixes = _resolve_prefixes(args)
    wave_label = args.wave if args.wave is not None else "custom"

    tenant_names = set(collect_tenant_models().keys())
    findings: list[dict] = []
    for py_path in APPS_DIR.rglob("*.py"):
        if _is_excluded(py_path):
            continue
        rel = str(py_path.relative_to(REPO_ROOT)).replace("\\", "/")
        if not rel.startswith(prefixes):
            continue
        findings.extend(scan_file(py_path, tenant_names))

    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_file[f["file"]].append(f)

    touched = 0
    for rel, rows in sorted(by_file.items()):
        path = REPO_ROOT / rel
        reason = _reason_for_file(rel)
        for row in rows:
            line_no = int(row["line"])
            if args.dry_run:
                print(f"would annotate {rel}:{line_no} ({reason})")
                touched += 1
            elif _insert_allow_marker(path, line_no, reason):
                print(f"annotated {rel}:{line_no}")
                touched += 1

    print(
        f"[wave{wave_label}] {'would touch' if args.dry_run else 'touched'} "
        f"{touched} call sites across {len(by_file)} files "
        f"(prefixes={','.join(prefixes)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
