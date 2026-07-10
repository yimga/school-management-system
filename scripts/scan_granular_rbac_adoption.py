#!/usr/bin/env python3
"""One-way ratchet on COARSE admin-tier gates in the tenant OPERATIONAL apps.

The RBAC-completion program (2026-07-05) gates every operational surface a school might
delegate to a NON-admin staff member (bursar / HR / registrar / HOD / DPO) on a GRANULAR
permission code via ``@require_permission("<domain>.<action>")`` — so an owner can grant a
custom role access without making them a full admin.

A COARSE gate — ``@tenant_admin_required`` or ``@permission_required("settings.manage" /
"settings.feature_control")`` — admits ONLY the admin tier (owner / ADMIN-like / superuser),
so a bursar granted ``finance.manage`` still can't reach it. This scanner counts every such
coarse gate on a view in the operational apps and FREEZES the number: it may only go DOWN
(migrate a coarse gate to ``@require_permission(...)``) — a new coarse gate on an operational
surface fails CI. It does NOT force the count to 0: some operational surfaces are legitimately
admin-only; mark those ``# rbac-coarse-allow: <reason>``.

Granular gates (``@require_permission``, in-body ``has_feature_permission`` /
``permission_access``) and operator gates (``require_control_plane_access`` /
``require_platform_scope``) are NOT counted. Tests + migrations are skipped.

Stdlib-only (ast + pathlib) so it runs in the deps-free architectural-boundaries job.

Usage:
    python scripts/scan_granular_rbac_adoption.py            # human report
    python scripts/scan_granular_rbac_adoption.py --json     # machine JSON
    python scripts/scan_granular_rbac_adoption.py --compare  # CI: exit 1 if count increased
    python scripts/scan_granular_rbac_adoption.py --update-baseline
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tenant operational apps: surfaces a school routinely delegates to non-admin staff.
_OPERATIONAL_APP_DIRS = (
    "apps/finance",
    "apps/payroll",
    "apps/evals",
    "apps/reports",
    "apps/analytics",
    "apps/compliance",
    "apps/athletics",
)

_BASELINE = os.path.join(
    REPO_ROOT, "var", "security-audit-baseline-granular-rbac-adoption.json"
)

_COARSE_SETTINGS_CODES = {"settings.manage", "settings.feature_control"}
_ALLOW_MARKER = "rbac-coarse-allow:"


def _iter_view_files():
    for app_dir in _OPERATIONAL_APP_DIRS:
        base = os.path.join(REPO_ROOT, app_dir.replace("/", os.sep))
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            parts = set(root.replace("\\", "/").split("/"))
            if {"tests", "migrations", "__pycache__"} & parts:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                if fn.startswith("test_") or fn in ("tests.py",):
                    continue
                yield os.path.join(root, fn)


def _rel(path: str) -> str:
    return os.path.relpath(path, REPO_ROOT).replace("\\", "/")


def _decorator_is_coarse(node) -> str | None:
    """Return the coarse-gate kind for a decorator node, or None.

    Handles ``@tenant_admin_required`` (bare or called), ``@permission_required("settings.*")``,
    and ``@method_decorator(tenant_admin_required, ...)`` / ``@method_decorator(
    permission_required("settings.manage"), ...)`` wrappers.
    """
    # method_decorator(inner, ...) — unwrap the first positional arg.
    if isinstance(node, ast.Call) and _callable_name(node.func) == "method_decorator":
        if node.args:
            return _decorator_is_coarse(node.args[0])
        return None

    name = _callable_name(node.func if isinstance(node, ast.Call) else node)
    if name == "tenant_admin_required":
        return "tenant_admin_required"
    if name == "permission_required":
        if isinstance(node, ast.Call):
            for a in node.args:
                if isinstance(a, ast.Constant) and a.value in _COARSE_SETTINGS_CODES:
                    return "permission_required:settings"
        # bare reference (unusual) — not counted; it needs the settings code to be coarse.
        return None
    return None


def _callable_name(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _callable_name(node.func)
    return None


def _line_or_above_has_marker(lines, lineno: int) -> bool:
    for probe in (lineno, lineno - 1):
        if 1 <= probe <= len(lines) and _ALLOW_MARKER in lines[probe - 1]:
            return True
    return False


def scan() -> list[dict]:
    findings: list[dict] = []
    for path in _iter_view_files():
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for dec in node.decorator_list:
                kind = _decorator_is_coarse(dec)
                if kind is None:
                    continue
                lineno = getattr(dec, "lineno", node.lineno)
                if _line_or_above_has_marker(lines, lineno):
                    continue
                findings.append(
                    {
                        "file": _rel(path),
                        "line": lineno,
                        "view": node.name,
                        "kind": kind,
                    }
                )
    findings.sort(key=lambda f: (f["file"], f["view"], f["kind"]))
    return findings


def _multiset(findings):
    return Counter((f["file"], f["view"], f["kind"]) for f in findings)


def _load_baseline():
    try:
        with open(_BASELINE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"finding_count": 0, "findings": []}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    findings = scan()
    count = len(findings)

    if args.update_baseline:
        payload = {
            "finding_count": count,
            "generated_at": "2026-07-05",
            "note": "Coarse admin-tier gates on operational-app views pending granular migration.",
            "findings": findings,
        }
        os.makedirs(os.path.dirname(_BASELINE), exist_ok=True)
        with open(_BASELINE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        print(f"baseline updated: {count} coarse operational gate(s)")
        return 0

    if args.compare:
        baseline = _load_baseline()
        base_ms = _multiset(baseline.get("findings", []))
        cur_ms = _multiset(findings)
        new = cur_ms - base_ms
        new_total = sum(new.values())
        if new_total:
            print(
                f"FAIL: {new_total} NEW coarse admin-tier gate(s) on operational surfaces "
                f"(baseline {baseline.get('finding_count', 0)} -> {count}). "
                f"Gate operational surfaces on a granular code via "
                f"@require_permission(\"<domain>.<action>\"), or mark an intentional "
                f"admin-only surface with '# rbac-coarse-allow: <reason>'."
            )
            for key, n in sorted(new.items()):
                f, v, k = key
                print(f"  + {f}::{v} [{k}] x{n}")
            return 1
        print(f"OK: no new coarse operational gates (count={count}, baseline={baseline.get('finding_count', 0)}).")
        return 0

    if args.json:
        print(json.dumps({"finding_count": count, "findings": findings}, indent=2))
        return 0

    print(f"{count} coarse admin-tier gate(s) on operational-app views:")
    for f in findings:
        print(f"  {f['file']}:{f['line']} {f['view']} [{f['kind']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
