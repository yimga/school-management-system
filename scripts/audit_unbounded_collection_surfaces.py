#!/usr/bin/env python3
"""
Fleet-scale audit: unbounded collections on operator / cross-tenant HTML surfaces.

Tenant-scoped pages (single school from request) are out of scope — those lists
are naturally bounded by enrollment. This scanner targets surfaces that could
render 10k+ schools/tenants in one response.

Detects:
  - list(School.objects...) / list(qs) without [:limit] in operator view modules
  - Client-side row filtering on operator school registry patterns
  - Operator templates looping schools/tenants without pagination

Companion: audit_large_collection_surfaces.py (wide-table UX).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"
STATIC_JS = ROOT / "static" / "js"
TEMPLATES = ROOT / "templates"
REPORT = ROOT / "docs" / "generated" / "unbounded_collection_surface_audit.json"
BASELINE = ROOT / "var" / "security-audit-baseline-unbounded-collection.json"

OPERATOR_VIEW_MARKERS = (
    "super_views",
    "super_views_",
    "/manager_views",
    "views_webhook_admin",
    "views_token_admin",
    "views_audit_admin",
    "views_administration",
    "views_super",
    "manager_views",
    "platform_monitoring",
    "dashboard_surfaces",
    "command_center",
    "exports",
)

OPERATOR_TEMPLATE_PREFIXES = (
    "schools/super_",
    "migration_cloud/operator/",
    "migration_cloud/super/",
    "customersuccess/super_",
    "observability/",
    "orchestration/",
    "apicenter/super/",
    "integrations_marketplace/manager_",
    "platform_runtime/",
)

FLEET_MODEL_MARKERS = ("School.objects", "MigrationCloudWebhook", "MigrationCloudAudit")

CLIENT_FILTER_RE = re.compile(
    r"(?:classList\.toggle\([\"']is-hidden|row\.hidden\s*=|\.style\.display\s*=.*none)",
    re.IGNORECASE,
)
ROW_LOOP_RE = re.compile(
    r"querySelectorAll\([\"'][^\"']*(?:cp-school-row|data-search)",
    re.IGNORECASE,
)
ALLOW_JS_RE = re.compile(
    r"unbounded-collection-allow:\s*(\S+(?:-\S+){2,})",
    re.IGNORECASE,
)
ALLOW_PY_RE = re.compile(
    r"#\s*unbounded-collection-allow:\s*(\S+(?:-\S+){2,})",
    re.IGNORECASE,
)
ALLOW_HTML_RE = re.compile(
    r"<!--\s*unbounded-collection-allow:\s*([^-]+(?:-[^-]+)*)\s*-->",
    re.IGNORECASE,
)
LIST_SLICE_RE = re.compile(r"\[\s*:\s*\d+\s*\]")


@dataclass
class Finding:
    kind: str
    file: str
    line: int
    detail: str
    recommendation: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "detail": self.detail,
            "recommendation": self.recommendation,
        }


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_operator_view(path: Path) -> bool:
    rel = _rel(path)
    if "/tests/" in rel or "/migrations/" in rel:
        return False
    return any(marker in rel for marker in OPERATOR_VIEW_MARKERS) or rel.endswith(
        ("super_views.py", "super_views_dashboard_surfaces.py")
    )


def _is_operator_template(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in OPERATOR_TEMPLATE_PREFIXES)


def _allow_marker_before(text: str, index: int, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(text[max(0, index - 500) : index]))


class FleetListVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, source: str):
        self.path = path
        self.source = source
        self.lines = source.splitlines()
        self.findings: list[Finding] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("api_"):
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "list":
            arg = node.args[0] if node.args else None
            if arg is not None and self._is_fleet_unbounded(arg):
                if _allow_marker_before(
                    self.source, self._line_offset(node.lineno), ALLOW_PY_RE
                ):
                    return
                detail = f"list({ast.unparse(arg)[:140]})"
                self.findings.append(
                    Finding(
                        kind="python_fleet_list_materialization",
                        file=_rel(self.path),
                        line=node.lineno,
                        detail=detail,
                        recommendation="Paginate (Paginator + page_obj) or cap with [:N] and document.",
                    )
                )
        self.generic_visit(node)

    def _line_offset(self, line: int) -> int:
        return sum(len(self.lines[i]) + 1 for i in range(line - 1))

    def _is_fleet_unbounded(self, node: ast.AST) -> bool:
        src = ast.unparse(node) if hasattr(ast, "unparse") else ""
        if LIST_SLICE_RE.search(src):
            return False
        if not any(marker in src for marker in FLEET_MODEL_MARKERS):
            # Operator views materializing huge generic querysets
            if "School.objects" in src:
                pass
            elif ".objects.all()" not in src and ".objects.filter" not in src:
                return False
        if "school=" in src.replace(" ", "") or "school_id=" in src.replace(" ", ""):
            return False
        if "[: " in src or "[:" in src:
            return False
        return True


def scan_operator_python() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(APPS.rglob("*.py")):
        if not _is_operator_view(path):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        visitor = FleetListVisitor(path, source)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def scan_client_filters() -> list[Finding]:
    findings: list[Finding] = []
    targets = (
        STATIC_JS / "manager-control-plane.js",
    )
    for path in targets:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "paginate_registry" in text or "cp-registry-filter-form" in text:
            continue
        if not CLIENT_FILTER_RE.search(text) or not ROW_LOOP_RE.search(text):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if CLIENT_FILTER_RE.search(line):
                offset = sum(len(l) + 1 for l in text.splitlines()[: i - 1])
                if _allow_marker_before(text, offset, ALLOW_JS_RE):
                    continue
                findings.append(
                    Finding(
                        kind="client_side_fleet_row_filter",
                        file=_rel(path),
                        line=i,
                        detail="Client-only filter on school registry rows",
                        recommendation="Server GET filter + Paginator (see super_dashboard_registry).",
                    )
                )
                break
    return findings


def scan_operator_templates() -> list[Finding]:
    findings: list[Finding] = []
    for_re = re.compile(
        r"{%\s*for\s+\w+\s+in\s+(?P<coll>[\w.]+)\s*%}",
        re.IGNORECASE,
    )
    fleet_collections = {"schools", "tenants", "rows"}
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = _rel(path)
        if not _is_operator_template(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if ALLOW_HTML_RE.search(text[:800]) or "unbounded-collection-allow:" in text:
            continue
        has_pagination = (
            "components/pagination.html" in text
            or "page_obj" in text
            or "registry_page" in text
        )
        has_paginate_policy = 'data-rmc-scroll-policy="paginate"' in text
        for match in for_re.finditer(text):
            coll = match.group("coll").split(".")[-1]
            if coll not in fleet_collections:
                continue
            if has_pagination or has_paginate_policy:
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    kind="operator_template_without_pagination",
                    file=rel,
                    line=line,
                    detail=f"{{% for ... in {match.group('coll')} %}} on operator surface",
                    recommendation="Add page_obj + components/pagination.html + paginate scroll policy.",
                )
            )
            break
    return findings


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = (
        scan_operator_python()
        + scan_client_filters()
        + scan_operator_templates()
    )
    seen: set[tuple[str, str, int]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.kind, f.file, f.line)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    unique.sort(key=lambda f: (f.kind, f.file, f.line))

    payload = {
        "finding_count": len(unique),
        "findings": [f.to_dict() for f in unique],
        "by_kind": {},
    }
    for f in unique:
        payload["by_kind"][f.kind] = payload["by_kind"].get(f.kind, 0) + 1

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {"finding_count": len(unique), "findings": payload["findings"]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    baseline_count = None
    if BASELINE.is_file():
        try:
            baseline_count = json.loads(BASELINE.read_text(encoding="utf-8")).get(
                "finding_count"
            )
        except json.JSONDecodeError:
            pass

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Fleet unbounded collection findings: {len(unique)}")
        for kind, count in sorted(payload["by_kind"].items()):
            print(f"  {kind}: {count}")
        for f in unique:
            print(f"  {f.kind} {f.file}:{f.line} — {f.detail[:100]}")
        if len(unique) == 0:
            print("UNBOUNDED_COLLECTION_SURFACE_PASS")

    if args.strict and len(unique) > 0:
        return 1
    if baseline_count is not None and len(unique) > baseline_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
