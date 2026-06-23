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

v2.83 capabilities (vs v2.80):
- Per-file alias map: follows `from apps.X.views import Y as Z` so
  routes that reference aliased symbols resolve to the real view.
- Class-based view detection: `path("X", MyClassView.as_view())`
  resolves `MyClassView` against the indexed classes.
- `# rbac-allow: <reason>` markers on the same line as a `path(...)`
  call (or the line immediately above) opt a route out of the
  candidate-anonymous bucket with an audit-visible reason.
- Inline-auth detection: views whose body contains an `If` test
  with `is_authenticated` / `is_anonymous` are flagged
  `has_inline_auth_check=True` and treated as login_gated rather
  than candidate_anonymous. Inline auth is harder to audit than a
  decorator but doesn't deserve to be lumped with truly-unprotected.

Honest caveats:
- The inline-auth check matches ANY `If` whose test mentions
  `is_authenticated` / `is_anonymous`. Rare false positives possible
  (e.g. a view that conditionally hides UI rather than rejecting
  the request). The output's `has_inline_auth_check` column lets
  reviewers spot these.
- DRF `permission_classes` are still detected as class-body
  assignments only — runtime overrides via `get_permissions()` are
  invisible to AST.
- Decorators applied imperatively in `urlpatterns` (e.g.
  `path("X", login_required(view))`) still aren't unwrapped.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"
CONFIG = ROOT / "config"
OUT_JSON = ROOT / "docs" / "generated" / "role_permission_matrix.json"
OUT_CSV = ROOT / "docs" / "generated" / "role_permission_matrix.csv"

EXTRA_VIEW_FILES = (
    APPS / "apicenter" / "oauth_views.py",
    APPS / "api" / "consumers.py",
)

EXTRA_URLS_FILES = (
    CONFIG / "urls.py",
    CONFIG / "manager_urls.py",
    CONFIG / "routing.py",
    APPS / "apicenter" / "oauth_urls.py",
)

WEBSOCKET_PATH_RE = re.compile(
    r"""re_path\(\s*r?["']([^"']*)["']\s*,\s*([A-Za-z_][A-Za-z0-9_.]*)\.as_asgi\(\)\s*\)""",
    re.DOTALL,
)

KNOWN_AUTH_DECORATORS = {
    # Django built-ins / DRF
    "login_required",
    "staff_member_required",
    "user_passes_test",
    "require_POST",
    "require_GET",
    "require_http_methods",
    # apps/accounts/decorators.py
    "role_required",
    "permission_required",
    "object_permission_required",
    "invoice_access_required",
    "student_detail_access_required",
    "portal_toggle_required",
    # apps/schools/control_plane.py — control-plane / super-surface gates
    "require_super_access_with_host",
    "require_super_access",
    "require_control_plane_access",
    "control_plane_only",
    "superadmin_required",
    "school_admin_required",
    # apps/schools/* + apps/portal/* tenant / feature gates
    "require_school",
    "require_school_permission",
    "require_feature",
    "require_parent_child_access",
    # apps/accounts/permissions.py — finance / evaluation / mfa gates
    "finance_access_required",
    "evaluation_access_required",
    "mfa_required",
    "require_platform_scope",
    # apps/marketplace/publisher_access.py — verified-publisher / operator gate
    "require_verified_publisher_with_host",
    # Django built-in predicate gate (used e.g. for staff/superuser-only views)
    "user_passes_test",
    # other custom gates
    "observability_auth_required",
    "webhook_security_required",
}


_AUTH_GATING_NAMES = {
    "login_required",
    "permission_required",
    "role_required",
    "staff_member_required",
    "require_super_access_with_host",
    "require_super_access",
    "require_control_plane_access",
    "control_plane_only",
    "superadmin_required",
    "school_admin_required",
    "require_school",
    "require_school_permission",
    "require_feature",
    "require_parent_child_access",
    "finance_access_required",
    "evaluation_access_required",
    "invoice_access_required",
    "student_detail_access_required",
    "object_permission_required",
    "mfa_required",
    "require_platform_scope",
    # Verified-publisher / operator gate (apps/marketplace/publisher_access.py):
    # asserts super-surface + authenticated + control-plane-or-verified-publisher.
    "require_verified_publisher_with_host",
    # Django predicate gate: @user_passes_test(<test>) redirects users who fail the
    # test to login; conventionally used for staff/superuser/role gating.
    "user_passes_test",
    "observability_auth_required",
    "webhook_security_required",
}
_ROLE_GATING_NAMES = {
    "role_required",
    "require_super_access_with_host",
    "require_super_access",
    "require_control_plane_access",
    "control_plane_only",
    "superadmin_required",
    "school_admin_required",
    "finance_access_required",
    "evaluation_access_required",
}


# Purpose-named PUBLIC-SURFACE view files: every route in these is anonymous by
# design (the public marketing site, the pre-auth signup funnel, PWA/service-worker
# assets, the public status page). Treating them as out-of-candidate-scope — the
# same way tests/ and migrations/ are excluded — is more honest than ~185 inline
# `# rbac-allow:` suppressions, and it still forces a *conscious* file placement:
# a genuinely-sensitive view dropped into one of these files is an obvious
# code-review smell. Routes here are reported with `public_surface=True` (audit
# visible) and excluded from the candidate_anonymous count. Mixed files (e.g.
# section8_views.py, observability/views.py) are NOT here — their public routes
# still carry per-route `# rbac-allow:` markers.
_PUBLIC_SURFACE_VIEW_BASENAMES = {
    "marketing_views.py",
    "competitive_marketing_views.py",
    "marketing_competitor_views.py",
    "marketing_kb_views.py",
    "signup_views.py",
    "views_manifest.py",
    "views_manifest_icon.py",
    "views_service_worker.py",
    "views_public_status.py",
}


def _is_public_surface(view_file: str | None) -> bool:
    if not view_file:
        return False
    return view_file.replace("\\", "/").split("/")[-1] in _PUBLIC_SURFACE_VIEW_BASENAMES


def _decorator_summary(dec: ast.expr) -> dict:
    """Reduce a decorator expression to {name, args}.

    Unwraps `@method_decorator(login_required, name="dispatch")` patterns
    (common on DRF/Django class-based views) so the effective inner
    decorator is what's reported, not the meta-decorator. Without this,
    every class-based view that uses `method_decorator` looks anonymous.
    """
    # method_decorator(inner, name="dispatch") -> report `inner`
    if (
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Name)
        and dec.func.id == "method_decorator"
        and dec.args
    ):
        inner = dec.args[0]
        # @method_decorator([dec1, dec2(arg)], name="dispatch")
        if isinstance(inner, (ast.List, ast.Tuple)) and inner.elts:
            inner = inner.elts[0]
        return _decorator_summary(inner)

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


def _has_inline_auth_check(node: ast.AST) -> bool:
    """True if any If node in the body tests `is_authenticated` / `is_anonymous`.

    Matches the common Django guard idiom
        if not request.user.is_authenticated:
            return redirect_to_login(...)
    without requiring the if to be the first statement (some views run
    a small amount of setup first). False positives possible if a view
    conditionally hides UI rather than rejecting the request; reviewers
    can spot these via the `has_inline_auth_check` column.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.If):
            continue
        try:
            test_src = ast.unparse(sub.test)
        except Exception:
            continue
        if "is_authenticated" in test_src or "is_anonymous" in test_src:
            return True
    return False


def _base_names(class_node: ast.ClassDef) -> list[str]:
    """Trailing-segment names of every base class (handles `module.Cls`)."""
    out: list[str] = []
    for b in class_node.bases:
        try:
            txt = ast.unparse(b)
        except Exception:
            continue
        out.append(txt.rsplit(".", 1)[-1])
    return out


# Django + DRF auth-enforcing mixins shipped with the framework.
DJANGO_AUTH_MIXINS = {
    "LoginRequiredMixin",
    "UserPassesTestMixin",
    "PermissionRequiredMixin",
    "AccessMixin",
}


def scan_views_file(path: Path) -> dict[str, dict]:
    """Return mapping view_name -> {decorators, file, kind, drf_permission_classes, has_inline_auth_check, bases}."""
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
                "has_inline_auth_check": _has_inline_auth_check(node),
                "bases": [],
            }
        elif isinstance(node, ast.ClassDef):
            out[node.name] = {
                "kind": "class",
                "file": rel,
                "decorators": [_decorator_summary(d) for d in node.decorator_list],
                "drf_permission_classes": _drf_permission_classes(node),
                # Class bodies sometimes carry inline auth checks too
                # (e.g. a get() method that bails on unauthenticated),
                # though decorator/mixin-style is far more common.
                "has_inline_auth_check": _has_inline_auth_check(node),
                "bases": _base_names(node),
            }
    return out


def _is_auth_enforcing_class(payload: dict, auth_class_set: set[str]) -> bool:
    """True if the class itself is an auth-enforcing mixin (has inline auth check
    in its body) or extends one of the known auth-enforcing classes."""
    if payload["kind"] != "class":
        return False
    if payload.get("has_inline_auth_check"):
        return True
    return any(b in auth_class_set for b in payload.get("bases", []))


def _build_auth_class_set(view_index: dict[str, dict]) -> set[str]:
    """Iteratively grow the set of class names known to enforce auth.

    Seed with Django/DRF built-in auth mixins (LoginRequiredMixin etc.) and any
    indexed class whose body contains an `is_authenticated` / `is_anonymous`
    guard. Then repeatedly add classes whose bases include one of the known set.
    Fixed-point iteration handles 2-deep + chains (mixin -> intermediate -> view).
    """
    auth_set: set[str] = set(DJANGO_AUTH_MIXINS)
    # Seed with classes that themselves perform inline auth checks.
    for name, payload in view_index.items():
        if payload["kind"] == "class" and payload.get("has_inline_auth_check"):
            auth_set.add(name)
    # Fixed-point propagation through inheritance chains.
    for _ in range(8):  # 8 is plenty for any sane MRO depth
        grew = False
        for name, payload in view_index.items():
            if name in auth_set:
                continue
            if payload["kind"] != "class":
                continue
            if any(b in auth_set for b in payload.get("bases", [])):
                auth_set.add(name)
                grew = True
        if not grew:
            break
    return auth_set


# Capture path patterns. The view-symbol group accepts dotted access and
# optional `.as_view()` invocation so class-based DRF views are matched.
URL_PATH_RE = re.compile(
    r"""path\(\s*r?["']([^"']*)["']\s*,\s*([A-Za-z_][A-Za-z0-9_.]*)(\(\s*\))?\s*[,)]""",
    re.DOTALL,
)

# `# rbac-allow: <reason>` on the same line as path(...) or the line above.
RBAC_ALLOW_RE = re.compile(r"#\s*rbac-allow\s*:\s*(.+?)\s*$")


def _imports_alias_map(tree: ast.Module) -> dict[str, str]:
    """Return {local_name: real_symbol_name} for ImportFrom + Import statements.

    `from apps.x.views import a, b as c, d` ->
        {"a": "a", "c": "b", "d": "d"}
    `import apps.x.views as xv` -> {"xv": "apps.x.views"}.
    The mapping covers same-app and cross-app aliasing, which together account
    for the majority of unresolved view symbols in earlier passes.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                aliases[local] = alias.name
    return aliases


def scan_urls_file(path: Path) -> tuple[list[dict], dict[str, str]]:
    """Return (rows, alias_map).

    Each row is {url_pattern, view_symbol, urls_file, rbac_allow_reason|None}.
    The alias_map is the per-file `local_name -> real_symbol_name` mapping
    used to resolve aliased imports.
    """
    rows: list[dict] = []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows, {}

    try:
        tree = ast.parse(text)
        aliases = _imports_alias_map(tree)
    except SyntaxError:
        aliases = {}

    lines = text.splitlines()

    for m in URL_PATH_RE.finditer(text):
        pattern = m.group(1)
        view_sym = m.group(2)

        # Find the line that contains the start of this match — both for the
        # marker hunt below and to surface where the route is declared.
        line_start = text.count("\n", 0, m.start()) + 1
        line_text = lines[line_start - 1] if 0 < line_start <= len(lines) else ""

        rbac_allow_reason: str | None = None
        marker_match = RBAC_ALLOW_RE.search(line_text)
        if marker_match:
            rbac_allow_reason = marker_match.group(1).strip()
        elif line_start > 1:
            prev_line = lines[line_start - 2]
            marker_match = RBAC_ALLOW_RE.search(prev_line)
            if marker_match and prev_line.lstrip().startswith("#"):
                rbac_allow_reason = marker_match.group(1).strip()

        rows.append(
            {
                "url_pattern": pattern,
                "view_symbol": view_sym,
                "urls_file": rel,
                "rbac_allow_reason": rbac_allow_reason,
            }
        )

    return rows, aliases


def _scan_websocket_routing(
    path: Path,
    view_index: dict[str, dict],
    auth_class_set: set[str],
) -> list[dict]:
    """Index Channels ``re_path`` routes from config/routing.py."""
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    rows: list[dict] = []
    lines = text.splitlines()
    for m in WEBSOCKET_PATH_RE.finditer(text):
        pattern = m.group(1)
        view_sym = m.group(2)
        line_start = text.count("\n", 0, m.start()) + 1
        line_text = lines[line_start - 1] if 0 < line_start <= len(lines) else ""
        rbac_allow_reason: str | None = None
        marker_match = RBAC_ALLOW_RE.search(line_text)
        if marker_match:
            rbac_allow_reason = marker_match.group(1).strip()
        elif line_start > 1:
            prev_line = lines[line_start - 2]
            marker_match = RBAC_ALLOW_RE.search(prev_line)
            if marker_match and prev_line.lstrip().startswith("#"):
                rbac_allow_reason = marker_match.group(1).strip()

        lookup_name = view_sym.rsplit(".", 1)[-1]
        view_payload = view_index.get(lookup_name)
        unresolved = view_payload is None
        row: dict = {
            "url_pattern": pattern,
            "view_symbol": view_sym,
            "urls_file": rel,
            "view_file": view_payload["file"] if view_payload else None,
            "kind": view_payload["kind"] if view_payload else "websocket",
            "decorators": [
                f"{d['name']}({', '.join(d['args'])})" if d["args"] else d["name"]
                for d in (view_payload["decorators"] if view_payload else [])
            ],
            "drf_permission_classes": view_payload["drf_permission_classes"] if view_payload else [],
            "bases": view_payload["bases"] if view_payload else [],
            "roles_required": _role_args(view_payload),
            "rbac_allow_reason": rbac_allow_reason,
            "unresolved": unresolved,
        }
        classification = _classify(view_payload, rbac_allow_reason, auth_class_set)
        if unresolved and not rbac_allow_reason:
            classification["candidate_anonymous"] = False
        row.update(classification)
        rows.append(row)
    return rows


def _resolve_view(view_sym: str, aliases: dict[str, str], view_index: dict[str, dict]) -> dict | None:
    """Best-effort lookup: try alias map, then dotted-suffix, then bare name."""
    # Strip `.as_view` so MyClass.as_view -> MyClass.
    raw = view_sym
    if raw.endswith(".as_view"):
        raw = raw[: -len(".as_view")]

    # Try the alias map first (handles `from .views import x as y`).
    resolved = aliases.get(raw, raw)

    # Then look up by trailing segment so `views_sub.foo` -> `foo`.
    lookup_name = resolved.rsplit(".", 1)[-1]
    return view_index.get(lookup_name)


def _classify(
    view_payload: dict | None,
    rbac_allow_reason: str | None,
    auth_class_set: set[str],
) -> dict:
    if view_payload is None:
        view_payload = {
            "decorators": [], "drf_permission_classes": [],
            "has_inline_auth_check": False, "bases": [], "kind": None,
            "file": None,
        }

    decs = [d["name"] for d in view_payload["decorators"]]
    drf = view_payload["drf_permission_classes"]
    inline_auth = view_payload.get("has_inline_auth_check", False)
    bases = view_payload.get("bases", [])

    decorator_login_gated = any(n in decs for n in _AUTH_GATING_NAMES) or any(
        p in drf for p in ("IsAuthenticated", "IsAdminUser")
    )
    mixin_login_gated = any(b in auth_class_set for b in bases)
    role_gated = any(n in decs for n in _ROLE_GATING_NAMES) or any(
        cls in drf for cls in (
            "IsTeacherOrAdmin", "IsTeacher", "IsParent", "IsStudent",
            "IsStudentOrParent", "IsBursar", "IsAdminLike", "RoleBasedPermission",
        )
    )
    permission_gated = any(n == "permission_required" for n in decs)

    login_gated = (
        decorator_login_gated
        or mixin_login_gated
        or inline_auth
        or bool(rbac_allow_reason)
    )
    # Candidate-anonymous: no decorator, no DRF perms, no inline check,
    # no auth mixin, no marker.
    anonymous_ok = not login_gated and not drf
    # Public-surface view files (marketing/signup/PWA/status) are anonymous by
    # design and out of candidate scope (see _PUBLIC_SURFACE_VIEW_BASENAMES).
    public_surface = _is_public_surface(view_payload.get("file"))
    if public_surface:
        anonymous_ok = False
    return {
        "login_gated": login_gated,
        "role_gated": role_gated,
        "permission_gated": permission_gated,
        "has_inline_auth_check": inline_auth,
        "auth_mixin_gated": mixin_login_gated,
        "public_surface": public_surface,
        "candidate_anonymous": anonymous_ok,
    }


def _role_args(view_payload: dict | None) -> list[str]:
    if view_payload is None:
        return []
    out: list[str] = []
    for d in view_payload["decorators"]:
        if d["name"] == "role_required":
            out.extend([a.strip("'\"") for a in d["args"]])
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-candidate-anonymous",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Exit 1 if the candidate_anonymous count exceeds N. Use this in CI to gate "
            "against new unprotected routes. Pin to the current count and let it ratchet "
            "down as routes are fixed."
        ),
    )
    args = parser.parse_args()

    # Walk every Python module that conventionally holds Django/DRF views.
    # views*.py covers Django function views; *_api.py and *_views.py cover the
    # DRF class-based views (which previous passes missed because they were in
    # files like apps/api/dashboard_api.py / apps/finance/api_views.py).
    view_files: set[Path] = set()
    for pattern in ("views*.py", "*_views.py", "*_api.py", "api_views.py", "consumers.py", "oauth_views.py"):
        view_files.update(APPS.rglob(pattern))
    for extra in EXTRA_VIEW_FILES:
        if extra.is_file():
            view_files.add(extra)

    view_index: dict[str, dict] = {}
    for views_path in view_files:
        rel = str(views_path).replace("\\", "/")
        if "/tests/" in rel or "/migrations/" in rel:
            continue
        scanned = scan_views_file(views_path)
        for name, payload in scanned.items():
            existing = view_index.get(name)
            if existing is None or len(payload["decorators"]) > len(existing["decorators"]):
                view_index[name] = payload

    auth_class_set = _build_auth_class_set(view_index)

    rows: list[dict] = []
    urls_files: set[Path] = set(APPS.rglob("urls*.py"))
    for extra in EXTRA_URLS_FILES:
        if extra.is_file():
            urls_files.add(extra)

    for urls_path in sorted(urls_files):
        if "/tests/" in str(urls_path).replace("\\", "/"):
            continue
        rel = str(urls_path.relative_to(ROOT)).replace("\\", "/")
        if rel.endswith("routing.py"):
            rows.extend(_scan_websocket_routing(urls_path, view_index, auth_class_set))
            continue
        scanned_rows, aliases = scan_urls_file(urls_path)
        for raw in scanned_rows:
            view_payload = _resolve_view(raw["view_symbol"], aliases, view_index)
            unresolved = view_payload is None
            row: dict = {
                "url_pattern": raw["url_pattern"],
                "view_symbol": raw["view_symbol"],
                "urls_file": raw["urls_file"],
                "view_file": view_payload["file"] if view_payload else None,
                "kind": view_payload["kind"] if view_payload else None,
                "decorators": [
                    f"{d['name']}({', '.join(d['args'])})" if d["args"] else d["name"]
                    for d in (view_payload["decorators"] if view_payload else [])
                ],
                "drf_permission_classes": view_payload["drf_permission_classes"] if view_payload else [],
                "bases": view_payload["bases"] if view_payload else [],
                "roles_required": _role_args(view_payload),
                "rbac_allow_reason": raw["rbac_allow_reason"],
                "unresolved": unresolved,
            }
            classification = _classify(view_payload, raw["rbac_allow_reason"], auth_class_set)
            if unresolved and not raw["rbac_allow_reason"]:
                # Don't classify unresolved views as candidate_anonymous; we
                # genuinely don't know what protects them.
                classification["candidate_anonymous"] = False
            row.update(classification)
            rows.append(row)

    summary = _summarize(rows)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_by": "scripts/audit_role_permission_matrix.py",
                "row_count": len(rows),
                "views_indexed": len(view_index),
                "summary": summary,
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
            "kind", "decorators", "drf_permission_classes", "bases", "roles_required",
            "login_gated", "role_gated", "permission_gated",
            "has_inline_auth_check", "auth_mixin_gated", "rbac_allow_reason",
            "candidate_anonymous", "unresolved", "public_surface",
        ])
        for r in rows:
            w.writerow([
                r["url_pattern"], r["view_symbol"], r["urls_file"], r["view_file"] or "",
                r["kind"] or "", " | ".join(r["decorators"]),
                " | ".join(r["drf_permission_classes"]),
                " | ".join(r["bases"]),
                ",".join(r["roles_required"]),
                int(r["login_gated"]), int(r["role_gated"]),
                int(r["permission_gated"]),
                int(r["has_inline_auth_check"]),
                int(r["auth_mixin_gated"]),
                r["rbac_allow_reason"] or "",
                int(r["candidate_anonymous"]), int(r["unresolved"]),
                int(r.get("public_surface", False)),
            ])

    print(f"audit_role_permission_matrix: {len(rows)} url->view rows")
    print(f"  views indexed:        {len(view_index)}")
    print(f"  login-gated:          {summary['login_gated']}")
    print(f"  role-gated:           {summary['role_gated']}")
    print(f"  permission-gated:     {summary['permission_gated']}")
    print(f"  inline-auth-check:    {summary['has_inline_auth_check']}")
    print(f"  auth-mixin-gated:     {summary['auth_mixin_gated']}")
    print(f"  rbac-allow markers:   {summary['rbac_allow_reason']}")
    print(f"  candidate-anonymous:  {summary['candidate_anonymous']} (review for public routes)")
    print(f"  public-surface:       {summary['public_surface']} (excluded: marketing/signup/PWA/status files)")
    print(f"  unresolved-view:      {summary['unresolved']} (view_symbol not found in views*.py)")
    print(f"  json:                 {OUT_JSON.relative_to(ROOT).as_posix()}")
    print(f"  csv:                  {OUT_CSV.relative_to(ROOT).as_posix()}")

    if args.max_candidate_anonymous is not None:
        count = summary["candidate_anonymous"]
        if count > args.max_candidate_anonymous:
            print(
                f"\nFAIL: candidate_anonymous count {count} exceeds gate "
                f"{args.max_candidate_anonymous}. A new route is missing auth.",
                file=sys.stderr,
            )
            print(
                "If the new route is intentionally public, add an auth decorator "
                "(or document a middleware-based protection with a `# rbac-allow: <reason>` "
                "marker on the same line as `path(...)`). To raise the gate, first triage "
                "every new entry — never silence the scanner.",
                file=sys.stderr,
            )
            return 1
        if count < args.max_candidate_anonymous:
            print(
                f"\nNOTE: candidate_anonymous count {count} is BELOW gate "
                f"{args.max_candidate_anonymous}. Consider tightening the gate to {count}."
            )
    return 0


def _summarize(rows: list[dict]) -> dict:
    return {
        "login_gated": sum(1 for r in rows if r["login_gated"]),
        "role_gated": sum(1 for r in rows if r["role_gated"]),
        "permission_gated": sum(1 for r in rows if r["permission_gated"]),
        "has_inline_auth_check": sum(1 for r in rows if r["has_inline_auth_check"]),
        "auth_mixin_gated": sum(1 for r in rows if r.get("auth_mixin_gated")),
        "rbac_allow_reason": sum(1 for r in rows if r["rbac_allow_reason"]),
        "candidate_anonymous": sum(1 for r in rows if r["candidate_anonymous"]),
        "public_surface": sum(1 for r in rows if r.get("public_surface")),
        "unresolved": sum(1 for r in rows if r["view_file"] is None),
    }


if __name__ == "__main__":
    sys.exit(main())
