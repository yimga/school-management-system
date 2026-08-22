#!/usr/bin/env python
"""DRF view schema-coverage scanner.

Enforces OpenAPI documentation hygiene: every DRF view class
(``APIView`` / ``GenericAPIView`` / ``ViewSet`` / ``ModelViewSet``
subclass) declared inside ``apps/api/`` — the platform's public API
surface — must carry ``@extend_schema`` (or ``@extend_schema_view``,
or be class-decorated with one) so the generated OpenAPI spec stays
honest.

Why ``apps/api/`` specifically: DRF views elsewhere in ``apps/``
(internal admin endpoints, callback handlers, htmx fragments) are
not necessarily part of the documented public surface. The
``apps/api/`` namespace is where third-party integrators look, and
schema-undocumented endpoints there are a contract failure.

Allowlist: views that are intentionally NOT in the public spec can
be marked with ``# drf-spectacular-allow: <reason>`` on the class
declaration line. Use sparingly — every entry is a missed doc
opportunity.

Output mirrors the other boundary scanners.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "apps" / "api"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-drf-schema-coverage.json"

DRF_VIEW_BASES = frozenset(
    {
        "APIView",
        "GenericAPIView",
        "ViewSet",
        "GenericViewSet",
        "ModelViewSet",
        "ReadOnlyModelViewSet",
        "RetrieveAPIView",
        "ListAPIView",
        "CreateAPIView",
        "UpdateAPIView",
        "DestroyAPIView",
        "ListCreateAPIView",
        "RetrieveUpdateAPIView",
        "RetrieveDestroyAPIView",
        "RetrieveUpdateDestroyAPIView",
    }
)
SCHEMA_DECORATORS = frozenset({"extend_schema", "extend_schema_view"})

ALLOW_MARKER = "drf-spectacular-allow:"


def _iter_api_files():
    if not API_DIR.exists():
        return
    for path in sorted(API_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path


def _decorator_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _is_drf_view(class_def: ast.ClassDef) -> bool:
    for base in class_def.bases:
        name = _decorator_name(base)
        if name and name in DRF_VIEW_BASES:
            return True
    return False


HTTP_HANDLERS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def _has_http_handler(class_def: ast.ClassDef) -> bool:
    """True when the class actually serves a request.

    A shared base such as sync_files_api._EdgeFileView carries only helpers and is
    never routed; drf-spectacular generates nothing for it, so demanding a schema
    on it is a finding about a thing that has no endpoint to document.
    """
    for item in class_def.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name in HTTP_HANDLERS:
                return True
    return False


def _has_schema_decorator(class_def: ast.ClassDef) -> bool:
    """Accept the decorator on the CLASS or on any HTTP handler inside it.

    Decorating the method is the ordinary drf-spectacular way to document a single
    handler on an APIView, and spectacular emits the operation either way. Checking
    only class_def.decorator_list reported four correctly-documented views as
    undocumented -- pairing start/poll and the sync bundle receipt all carry
    @extend_schema on their handler.
    """
    for deco in class_def.decorator_list:
        name = _decorator_name(deco)
        if name and name in SCHEMA_DECORATORS:
            return True
    for item in class_def.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in item.decorator_list:
            name = _decorator_name(deco)
            if name and name in SCHEMA_DECORATORS:
                return True
    return False


def _is_allowlisted(source_lines: list[str], lineno: int) -> bool:
    # Check the class line and the line immediately above for the marker.
    for offset in (0, -1):
        idx = lineno - 1 + offset
        if 0 <= idx < len(source_lines) and ALLOW_MARKER in source_lines[idx]:
            return True
    return False


def _scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for path in _iter_api_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        source_lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_drf_view(node):
                continue
            if not _has_http_handler(node):
                continue
            if _has_schema_decorator(node):
                continue
            if _is_allowlisted(source_lines, node.lineno):
                continue
            findings.append(
                {
                    "path": rel,
                    "line": node.lineno,
                    "class": node.name,
                }
            )
    findings.sort(key=lambda item: (item["path"], item["line"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "DRF view classes in apps/api/ must carry @extend_schema or @extend_schema_view",
        "scan_dir": API_DIR.relative_to(REPO_ROOT).as_posix(),
        "drf_view_bases": sorted(DRF_VIEW_BASES),
        "schema_decorators": sorted(SCHEMA_DECORATORS),
        "allow_marker": ALLOW_MARKER,
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings: list[dict]) -> None:
    print(f"DRF schema coverage scan: {len(findings)} undocumented view(s)")
    for finding in findings:
        print(f"  {finding['path']}:{finding['line']}  class {finding['class']}")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_set = {
        (item["path"], item["class"]) for item in baseline.get("findings", [])
    }
    current_set = {(item["path"], item["class"]) for item in findings}
    new = current_set - baseline_set
    removed = baseline_set - current_set
    _print_summary(findings)
    if new:
        print("\nNEW undocumented DRF views introduced:")
        for path, cls in sorted(new):
            print(f"  {path}  class {cls}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for path, cls in sorted(removed):
            print(f"  {path}  class {cls}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
