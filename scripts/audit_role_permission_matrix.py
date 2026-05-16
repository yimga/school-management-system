#!/usr/bin/env python
"""Role / permission matrix audit.

AST-walks every `apps/*/views*.py` to extract per-view decorators
(`@login_required`, `@role_required(...)`, `@permission_required(...)`,
DRF `permission_classes = [...]`, etc.) and joins them to URL patterns
discovered in `apps/*/urls.py` so each route lands in one row of a
matrix:

    URL pattern  | view name  | view file  | decorators / perms  | role-gated? | login-gated?

Outputs:
    docs/generated/role_permission_matrix.json     (canonical)
    docs/generated/role_permission_matrix.csv      (spreadsheet-friendly)
    docs/ROLE_PERMISSION_MATRIX_<DATE>.md          (top-of-matrix human-readable summary,
                                                    written separately by the caller — this
                                                    script only writes the data)

Honest caveats:
- View name lookup is by symbol name within the same app. Cross-app `from .views import x as y`
  aliasing is best-effort.
- Does not unwrap functional wrapping like `view = login_required(role_required("ADMIN")(view))`
  applied imperatively in a urlpatterns line.
- DRF `permission_classes` are detected as class-body assignments only.
- "Unprotected" means no decorator detected. Some views protect through middleware (RLS,
  TenantContextMiddleware) — the matrix flags candidates, not bugs.
"""
from __future__ import annotations

import ast
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"
OUT_JSON = ROOT / "docs" / "generated" / "role_permission_matrix.json"
OUT_CSV = ROOT / "docs" / "generated" / "role_permission_matrix.csv"

KNOWN_AUTH_DECORATORS = {
    "login_required",
    "role_required",
    "permission_required",
    "object_permission_required",
    "invoice_access_required",
    "student_detail_access_required",
    "portal_toggle_required",
    "staff_member_required",
    "user_passes_test",
    "require_POST",
    "require_GET",
    "require_http_methods",
    "control_plane_only",
    "superadmin_required",
    "school_admin_required",
}


def _decorator_summary(dec: ast.expr) -> dict:
    """Reduce a decorator expression to {name, args}."""
    if isinstance(dec, ast.Call):
        if isinstance(dec.func, ast.Name):
            name = dec.func.id
        elif isinstance(dec.func, ast.Attribute):
            name = dec.func.attr
        else:
            name = ast.unparse(dec.func)
        args: list[str] = []
        for a in dec.args:
            if isinstance(a, ast.Constant):
                args.append(repr(a.value))
            else:
                try:
                    args.append(ast.unparse(a))
                except Exception:
                    args.append("<expr>")
        return {"name": name, "args": args}
    if isinstance(dec, ast.Name):
        return {"name": dec.id, "args": []}
    if isinstance(dec, ast.Attribute):
        return {"name": dec.attr, "args": []}
    return {"name": ast.unparse(dec), "args": []}


def _drf_permission_classes(class_node: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for stmt in class_node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "permission_classes" for t in stmt.targets):
            continue
        if isinstance(stmt.value, (ast.List, ast.Tuple)):
            for el in stmt.value.elts:
                if isinstance(el, ast.Name):
                    out.append(el.id)
                elif isinstance(el, ast.Attribute):
                    out.append(el.attr)
                else:
                    try:
                        out.append(ast.unparse(el))
                    except Exception:
                        out.append("<expr>")
    return out


def scan_views_file(path: Path) -> dict[str, dict]:
    """Return mapping view_name -> {decorators, file, kind, drf_permission_classes}."""
    out: dict[str, dict] = {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return out
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = {
                "kind": "func",
                "file": rel,
                "decorators": [_decorator_summary(d) for d in node.decorator_list],
                "drf_permission_classes": [],
            }
        elif isinstance(node, ast.ClassDef):
            out[node.name] = {
                "kind": "class",
                "file": rel,
                "decorators": [_decorator_summary(d) for d in node.decorator_list],
                "drf_permission_classes": _drf_permission_classes(node),
            }
    return out


URL_PATH_RE = re.compile(
    r"""path\(\s*r?["']([^"']*)["']\s*,\s*([A-Za-z_][A-Za-z0-9_.]*)\s*[,)]""",
    re.DOTALL,
)


def scan_urls_file(path: Path) -> list[tuple[str, str, str]]:
    """Return list of (url_pattern, view_symbol_referenced, urls_file)."""
    out: list[tuple[str, str, str]] = []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for m in URL_PATH_RE.finditer(text):
        pattern, view_sym = m.group(1), m.group(2)
        out.append((pattern, view_sym, rel))
    return out


def _classify(row: dict) -> dict:
    decs = [d["name"] for d in row["decorators"]]
    drf = row["drf_permission_classes"]
    login_gated = any(
        n in decs for n in ("login_required", "permission_required", "role_required", "staff_member_required")
    ) or any(p in drf for p in ("IsAuthenticated", "IsAdminUser"))
    role_gated = any(n == "role_required" for n in decs) or any(
        cls in drf for cls in (
            "IsTeacherOrAdmin", "IsTeacher", "IsParent", "IsStudent",
            "IsStudentOrParent", "IsBursar", "IsAdminLike", "RoleBasedPermission",
        )
    )
    permission_gated = any(n == "permission_required" for n in decs)
    anonymous_ok = not login_gated and not drf
    return {
        "login_gated": login_gated,
        "role_gated": role_gated,
        "permission_gated": permission_gated,
        "candidate_anonymous": anonymous_ok,
    }


def _role_args(row: dict) -> list[str]:
    out: list[str] = []
    for d in row["decorators"]:
        if d["name"] == "role_required":
            out.extend([a.strip("'\"") for a in d["args"]])
    return sorted(set(out))


def main() -> int:
    view_index: dict[str, dict] = {}
    for views_path in APPS.rglob("views*.py"):
        if "/tests/" in str(views_path).replace("\\", "/"):
            continue
        scanned = scan_views_file(views_path)
        for name, payload in scanned.items():
            existing = view_index.get(name)
            if existing is None or len(payload["decorators"]) > len(existing["decorators"]):
                view_index[name] = payload

    rows: list[dict] = []
    for urls_path in APPS.rglob("urls*.py"):
        if "/tests/" in str(urls_path).replace("\\", "/"):
            continue
        for pattern, view_sym, urls_file in scan_urls_file(urls_path):
            # Handle dotted references like `views_syllabus.teacher_syllabus_hub`
            # by indexing on the trailing symbol name.
            lookup_name = view_sym.rsplit(".", 1)[-1]
            view_payload = view_index.get(lookup_name)
            unresolved = view_payload is None
            row: dict = {
                "url_pattern": pattern,
                "view_symbol": view_sym,
                "urls_file": urls_file,
                "view_file": view_payload["file"] if view_payload else None,
                "kind": view_payload["kind"] if view_payload else None,
                "decorators": [
                    f"{d['name']}({', '.join(d['args'])})" if d["args"] else d["name"]
                    for d in (view_payload["decorators"] if view_payload else [])
                ],
                "drf_permission_classes": view_payload["drf_permission_classes"] if view_payload else [],
                "roles_required": _role_args(view_payload) if view_payload else [],
                "unresolved": unresolved,
            }
            classification = _classify(view_payload or {"decorators": [], "drf_permission_classes": []})
            # Unresolved views cannot be classified as "candidate_anonymous" — we
            # genuinely don't know what protects them. Mark separately.
            if unresolved:
                classification["candidate_anonymous"] = False
            row.update(classification)
            rows.append(row)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_by": "scripts/audit_role_permission_matrix.py",
                "row_count": len(rows),
                "views_indexed": len(view_index),
                "summary": _summarize(rows),
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "url_pattern", "view_symbol", "urls_file", "view_file",
            "kind", "decorators", "drf_permission_classes", "roles_required",
            "login_gated", "role_gated", "permission_gated",
            "candidate_anonymous", "unresolved",
        ])
        for r in rows:
            w.writerow([
                r["url_pattern"], r["view_symbol"], r["urls_file"], r["view_file"] or "",
                r["kind"] or "", " | ".join(r["decorators"]),
                " | ".join(r["drf_permission_classes"]),
                ",".join(r["roles_required"]),
                int(r["login_gated"]), int(r["role_gated"]),
                int(r["permission_gated"]), int(r["candidate_anonymous"]),
                int(r["unresolved"]),
            ])

    summary = _summarize(rows)
    print(f"audit_role_permission_matrix: {len(rows)} url->view rows")
    print(f"  views indexed:        {len(view_index)}")
    print(f"  login-gated:          {summary['login_gated']}")
    print(f"  role-gated:           {summary['role_gated']}")
    print(f"  permission-gated:     {summary['permission_gated']}")
    print(f"  candidate-anonymous:  {summary['candidate_anonymous']} (review for public routes)")
    print(f"  unresolved-view:      {summary['unresolved']} (view_symbol not found in views*.py)")
    print(f"  json:                 {OUT_JSON.relative_to(ROOT).as_posix()}")
    print(f"  csv:                  {OUT_CSV.relative_to(ROOT).as_posix()}")
    return 0


def _summarize(rows: list[dict]) -> dict:
    return {
        "login_gated": sum(1 for r in rows if r["login_gated"]),
        "role_gated": sum(1 for r in rows if r["role_gated"]),
        "permission_gated": sum(1 for r in rows if r["permission_gated"]),
        "candidate_anonymous": sum(1 for r in rows if r["candidate_anonymous"]),
        "unresolved": sum(1 for r in rows if r["view_file"] is None),
    }


if __name__ == "__main__":
    sys.exit(main())
