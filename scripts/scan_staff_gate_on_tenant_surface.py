#!/usr/bin/env python3
"""scan_staff_gate_on_tenant_surface.py — seal the "is_staff as an operator gate
on a tenant-reachable surface" class (H1 of
docs/generated/tenant_operator_isolation_forensic_audit_2026_07_04.md).

WHY THIS GATE EXISTS
--------------------
The platform DELIBERATELY mints ``is_staff=True`` tenant-scoped users
(``ensure_default_tenant_admin`` sets ``user.is_staff = True`` on a ``role=ADMIN``
user that carries a ``SchoolMembership``; ``create_teacher_parent_accounts`` does the
same for a principal). Django's ``@staff_member_required`` is exactly
``is_active and is_staff`` — nothing more. Therefore, on any view reachable from
``config/tenant_urls.py`` (the urlconf a real tenant subdomain resolves through),
``@staff_member_required`` is NOT an operator gate: a tenant admin passes it.

Operator-flavoured views must gate on ``user_has_control_plane_access`` — via
``require_control_plane_access`` / ``require_super_access`` /
``require_super_access_with_host`` / ``require_platform_scope`` — which fail-closes on
ANY ``SchoolMembership`` holder (``apps/schools/control_plane.py``). This is the same
keystone the whole tenant->operator boundary rests on.

WHAT IT DOES
------------
1. Statically resolves the transitive ``include()`` tree rooted at
   ``config/tenant_urls.py`` to the set of view callables routed on the tenant host.
   (``config/urls.py`` / ``config/manager_urls.py`` are NOT reachable from
   ``tenant_urls`` — no include of them — so operator views mounted only there are
   correctly excluded.)
2. For each resolvable view, reads its decorator chain (function decorators, class
   ``@method_decorator(...)``, decorators on ``dispatch``/``get``/``post``) plus any
   route-level wrapper (``staff_member_required(view)`` / ``login_required(view)``).
3. Flags any view whose only auth signal is ``staff_member_required`` (bare or via
   ``@method_decorator``) with NO control-plane signal and NO
   ``# tenant-surface-staff-allow: <reason>`` marker.

FALSE-NEGATIVE BIASED: any view reference it cannot statically resolve is SKIPPED,
never flagged, so a clean tree never reddens CI on resolution ambiguity. Deps-free
(stdlib ``ast`` + filesystem) so it runs in the ``architectural-boundaries.yml``
boundary job. ``user_passes_test`` / inline ``is_staff`` body checks are intentionally
out of scope (too ambiguous to classify without false positives) — this gate targets
the unambiguous Django ``staff_member_required`` decorator.

Guard an intentional staff-gated tenant surface with
``# tenant-surface-staff-allow: <reason>`` on the def line, a decorator line, or the
line directly above the first decorator.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
TENANT_ROOT_MODULE = "config.tenant_urls"
BASELINE_PATH = os.path.join(
    REPO_ROOT, "var", "security-audit-baseline-staff-gate-on-tenant-surface.json"
)
MARKER = "tenant-surface-staff-allow"

STAFF_TOKEN = "staff_member_required"
CONTROL_PLANE_TOKENS = frozenset(
    {
        "require_platform_scope",
        "require_control_plane_access",
        "require_super_access",
        "require_super_access_with_host",
    }
)
# Names that, when seen wrapping a routed view at the URL layer, are benign (they do
# not turn an is_staff gate into a control-plane gate, but they are not themselves the
# is_staff gate either).
_BENIGN_WRAPPERS = frozenset({"login_required", "cache_page", "csrf_exempt", "never_cache"})
_MAX_DEPTH = 8


def _module_to_file(dotted: str) -> str | None:
    """Map a dotted module ("apps.assist_dock.urls") to its .py file, if it exists."""
    rel = dotted.replace(".", os.sep)
    candidate = os.path.join(REPO_ROOT, rel + ".py")
    if os.path.isfile(candidate):
        return candidate
    pkg_init = os.path.join(REPO_ROOT, rel, "__init__.py")
    if os.path.isfile(pkg_init):
        return pkg_init
    return None


@lru_cache(maxsize=None)
def _parse(path: str) -> ast.Module | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return ast.parse(fh.read(), filename=path)
    except (OSError, SyntaxError, ValueError):
        return None


@lru_cache(maxsize=None)
def _raw_lines(path: str) -> tuple[str, ...]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return tuple(fh.read().splitlines())
    except OSError:
        return tuple()


def _package_of(dotted_module: str) -> str:
    """Package portion of a dotted module ("apps.assist_dock.urls" -> "apps.assist_dock")."""
    return dotted_module.rsplit(".", 1)[0] if "." in dotted_module else dotted_module


def _build_import_map(tree: ast.Module, self_module: str) -> dict:
    """name -> ("symbol", module_dotted, symbol) | ("module", module_dotted)."""
    package = _package_of(self_module)
    imap: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level >= 1:
                # relative import: `from . import X` / `from .views import a`
                base = package
                for _ in range(node.level - 1):
                    base = _package_of(base)
                target_mod = f"{base}.{node.module}" if node.module else base
            else:
                target_mod = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                if node.level and node.level >= 1 and not node.module:
                    # `from . import X`  -> X is a submodule of the package
                    imap[local] = ("module", f"{target_mod}.{alias.name}")
                else:
                    imap[local] = ("symbol", target_mod, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                imap[local] = ("module", alias.name)
    return imap


def _dunder_import_target(call: ast.Call):
    """Resolve `__import__("apps.a.b", fromlist=["x"]).x` -> ("apps.a.b", "x")."""
    # call is the Attribute(.x)'s value being a Call to __import__.
    if not (isinstance(call.func, ast.Name) and call.func.id == "__import__"):
        return None
    if not call.args or not isinstance(call.args[0], ast.Constant):
        return None
    return str(call.args[0].value)


def _resolve_view_ref(node: ast.AST, imap: dict, self_module: str, self_path: str,
                      wrappers: set[str]):
    """Resolve a view reference AST node to (file_path, symbol) or None.

    Accumulates any URL-layer wrapper names into `wrappers`.
    """
    # Unwrap route-level wrappers: some_wrapper(inner_view, ...)
    if isinstance(node, ast.Call):
        func = node.func
        # Class-based: X.as_view(...)
        if isinstance(func, ast.Attribute) and func.attr == "as_view":
            return _resolve_view_ref(func.value, imap, self_module, self_path, wrappers)
        # __import__("apps.a.b", fromlist=[...]).symbol
        if isinstance(func, ast.Name):
            fname = func.id
            if fname == "__import__":
                return None  # a bare __import__ call isn't a view
            # wrapper(inner, ...) e.g. login_required(view), staff_member_required(view)
            wrappers.add(fname)
            if node.args:
                return _resolve_view_ref(node.args[0], imap, self_module, self_path, wrappers)
            return None
        if isinstance(func, ast.Attribute):
            # e.g. cache_page(60)(view) chains, or module.func(...) -> not a view call we track
            return _resolve_view_ref(func, imap, self_module, self_path, wrappers)
        return None

    if isinstance(node, ast.Attribute):
        # __import__("apps.a.b", fromlist=["x"]).x
        if isinstance(node.value, ast.Call):
            mod = _dunder_import_target(node.value)
            if mod:
                f = _module_to_file(mod)
                return (f, node.attr) if f else None
        # module_alias.symbol
        if isinstance(node.value, ast.Name):
            resolved = imap.get(node.value.id)
            if resolved and resolved[0] == "module":
                f = _module_to_file(resolved[1])
                return (f, node.attr) if f else None
        return None

    if isinstance(node, ast.Name):
        name = node.id
        resolved = imap.get(name)
        if resolved:
            if resolved[0] == "symbol":
                f = _module_to_file(resolved[1])
                return (f, resolved[2]) if f else None
            if resolved[0] == "module":
                # bare module used as a view — not valid; skip
                return None
        # Locally defined in the urlconf module itself
        if _find_def(self_path, name) is not None:
            return (self_path, name)
        return None

    return None


@lru_cache(maxsize=None)
def _defs_index(path: str) -> dict:
    tree = _parse(path)
    out: dict = {}
    if tree is None:
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
    return out


def _find_def(path: str, name: str):
    return _defs_index(path).get(name)


def _decorator_token(dec: ast.AST) -> str | None:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Call):
        return _decorator_token(dec.func)
    return None


def _collect_decorator_tokens(dec: ast.AST, out: set[str]) -> None:
    """Collect decorator name tokens, unwrapping method_decorator(inner, ...)."""
    tok = _decorator_token(dec)
    if tok:
        out.add(tok)
    if isinstance(dec, ast.Call) and _decorator_token(dec.func) == "method_decorator":
        for arg in dec.args:
            if isinstance(arg, (ast.Name, ast.Attribute, ast.Call)):
                inner = _decorator_token(arg)
                if inner:
                    out.add(inner)
            elif isinstance(arg, (ast.List, ast.Tuple)):
                for elt in arg.elts:
                    inner = _decorator_token(elt)
                    if inner:
                        out.add(inner)


def _view_decorator_tokens(def_node: ast.AST) -> set[str]:
    tokens: set[str] = set()
    if isinstance(def_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for dec in def_node.decorator_list:
            _collect_decorator_tokens(dec, tokens)
    elif isinstance(def_node, ast.ClassDef):
        for dec in def_node.decorator_list:
            _collect_decorator_tokens(dec, tokens)
        for item in def_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in (
                "dispatch",
                "get",
                "post",
                "put",
                "patch",
                "delete",
            ):
                for dec in item.decorator_list:
                    _collect_decorator_tokens(dec, tokens)
    return tokens


def _has_marker_near(path: str, def_node: ast.AST) -> bool:
    lines = _raw_lines(path)
    if not lines:
        return False
    first = def_node.lineno
    if getattr(def_node, "decorator_list", None):
        first = min(first, min(d.lineno for d in def_node.decorator_list))
    lo = max(0, first - 2)
    hi = min(len(lines), def_node.lineno + 1)
    return any(MARKER in lines[i] for i in range(lo, hi))


def _path_literal(call: ast.Call) -> str:
    """The route's path pattern string ('' when dynamic/non-literal).

    Handles f-string patterns (``f"super/wizards/{key}/"``) by keeping the literal
    segments and replacing each interpolation with a separator, so segment-level
    checks (``super``) still see the literal prefix.
    """
    if not call.args:
        return ""
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        parts = []
        for v in arg.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("/")  # interpolation placeholder preserves segment boundary
        return "".join(parts)
    return ""


def _has_super_segment(full_path: str) -> bool:
    """True when the accumulated URL path has a `super` segment — an operator route
    sealed on the tenant host by TenantSuperAdminRequiredMiddleware, so not a finding."""
    return "super" in (full_path or "").strip("/").split("/")


def _collect_routed_views(tenant_root_file: str):
    """BFS the include() tree; yield (view_file, symbol, wrappers, url_file, lineno, full_path)."""
    seen_modules: set[str] = set()
    root_mod = TENANT_ROOT_MODULE
    # queue holds (url_file, self_module_dotted, depth, path_prefix)
    queue = [(tenant_root_file, root_mod, 0, "")]
    seen_modules.add(root_mod)
    results = []

    while queue:
        url_file, self_module, depth, prefix = queue.pop()
        tree = _parse(url_file)
        if tree is None:
            continue
        imap = _build_import_map(tree, self_module)

        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            fname = call.func.id if isinstance(call.func, ast.Name) else (
                call.func.attr if isinstance(call.func, ast.Attribute) else None
            )
            if fname not in ("path", "re_path", "url"):
                continue
            if len(call.args) < 2:
                continue
            view_arg = call.args[1]
            pattern = _path_literal(call)

            # include(...) => recurse to the included urlconf, carrying the prefix
            if isinstance(view_arg, ast.Call) and (
                (isinstance(view_arg.func, ast.Name) and view_arg.func.id == "include")
            ):
                if depth >= _MAX_DEPTH:
                    continue
                inc_mod = _include_target_module(view_arg.args[0] if view_arg.args else None)
                if inc_mod and inc_mod not in seen_modules:
                    f = _module_to_file(inc_mod)
                    if f:
                        seen_modules.add(inc_mod)
                        queue.append((f, inc_mod, depth + 1, prefix + pattern))
                continue

            wrappers: set[str] = set()
            resolved = _resolve_view_ref(view_arg, imap, self_module, url_file, wrappers)
            if resolved and resolved[0]:
                results.append(
                    (resolved[0], resolved[1], wrappers, url_file, call.lineno, prefix + pattern)
                )

    return results


def _include_target_module(node: ast.AST) -> str | None:
    """Extract the dotted module from an include() first arg."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # include(("apps.x.urls", "ns"), namespace="ns")
    if isinstance(node, ast.Tuple) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


# Apps mounted ONLY on the tenant urlconf (config/tenant_urls.py) + the local full
# urlconf — never on config/manager_urls.py (verified 2026-07-05). There are no
# operator/super views in these apps, so EVERY @staff_member_required in them is a
# tenant-surface staff gate. We sweep their view modules directly as a belt-and-
# suspenders pass, because the include()-tree route resolver above returns a FALSE
# NEGATIVE when a view is re-exported through a package __init__ (e.g. finance's
# `from .views import dashboard`, where `dashboard` is re-exported from
# views_dashboard.py, not defined in views/__init__.py) — which is exactly how the
# finance dashboard's staff gate went undetected before 2026-07-05. Adding an app here
# is a reviewed change; only apps verified absent from config/manager_urls.py belong.
_TENANT_ONLY_APP_DIRS = (
    "apps/finance",
    "apps/reports",
    "apps/evals",
    "apps/analytics",
    "apps/payroll",
)
_SWEEP_EXCLUDE_DIRS = frozenset({"tests", "migrations", "__pycache__", "management"})


def _iter_app_py_files(app_rel_dir: str):
    base = os.path.join(REPO_ROOT, app_rel_dir)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SWEEP_EXCLUDE_DIRS]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def _scan_tenant_only_app_modules():
    """Flag every unmarked @staff_member_required in a tenant-only app's modules.

    Route-resolution-independent, so a package-__init__ re-export can't hide a staff
    gate. Same allowances as the routed pass: a control-plane decorator or a
    ``# tenant-surface-staff-allow`` marker clears it.
    """
    findings = []
    for app_dir in _TENANT_ONLY_APP_DIRS:
        for path in _iter_app_py_files(app_dir):
            tree = _parse(path)
            if tree is None:
                continue
            for node in tree.body:
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    continue
                tokens = _view_decorator_tokens(node)
                if STAFF_TOKEN not in tokens:
                    continue
                if tokens & CONTROL_PLANE_TOKENS:
                    continue
                if _has_marker_near(path, node):
                    continue
                findings.append(
                    {
                        "file": os.path.relpath(path, REPO_ROOT).replace(os.sep, "/"),
                        "line": node.lineno,
                        "view": node.name,
                        "routed_by": f"tenant-only app sweep ({app_dir})",
                        "reason": "staff_member_required on a tenant-only app view; use "
                        "tenant_admin_required (owner/role=ADMIN/settings.manage) — is_staff is "
                        "not a reliable tenant-admin signal — or mark # tenant-surface-staff-allow: <reason>",
                    }
                )
    return findings


def scan(tenant_root_file: str):
    findings = []
    for view_file, symbol, wrappers, url_file, url_lineno, full_path in _collect_routed_views(
        tenant_root_file
    ):
        if _has_super_segment(full_path):
            continue  # operator route sealed on tenant host by the super-segment guard
        def_node = _find_def(view_file, symbol)
        if def_node is None:
            continue  # unresolved -> skip (false-negative biased)
        tokens = _view_decorator_tokens(def_node)
        staff = (STAFF_TOKEN in tokens) or (STAFF_TOKEN in wrappers)
        if not staff:
            continue
        if tokens & CONTROL_PLANE_TOKENS:
            continue
        if _has_marker_near(view_file, def_node):
            continue
        findings.append(
            {
                "file": os.path.relpath(view_file, REPO_ROOT).replace(os.sep, "/"),
                "line": def_node.lineno,
                "view": symbol,
                "routed_by": os.path.relpath(url_file, REPO_ROOT).replace(os.sep, "/"),
                "reason": "staff_member_required is the only gate on a tenant-reachable view; "
                "use require_control_plane_access / require_platform_scope, move it off the "
                "tenant urlconf, or mark with # tenant-surface-staff-allow: <reason>",
            }
        )
    # Belt-and-suspenders: sweep tenant-only apps' modules directly so a
    # package-__init__ re-export can't hide a staff gate from the route resolver.
    findings.extend(_scan_tenant_only_app_modules())
    # de-dup (a view can be routed more than once, or surface via both passes)
    uniq = {}
    for f in findings:
        uniq[(f["file"], f["line"], f["view"])] = f
    return sorted(uniq.values(), key=lambda f: (f["file"], f["line"]))


def _load_baseline() -> int:
    try:
        with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
            return int(json.load(fh).get("finding_count", 0))
    except (OSError, ValueError, KeyError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="exit 1 if any finding")
    ap.add_argument("--compare", action="store_true", help="exit 1 if count > baseline")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    root = _module_to_file(TENANT_ROOT_MODULE)
    if not root:
        print("ERROR: cannot locate config/tenant_urls.py", file=sys.stderr)
        return 2

    findings = scan(root)
    count = len(findings)

    if args.write_baseline:
        os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as fh:
            json.dump({"finding_count": count, "gate": "staff-gate-on-tenant-surface"}, fh, indent=2)
        print(f"baseline written: {count}")
        return 0

    if args.json:
        print(json.dumps({"finding_count": count, "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}:{f['line']}  {f['view']}  (routed by {f['routed_by']})")
        print(f"\nstaff-gate-on-tenant-surface findings: {count}")

    if args.compare:
        base = _load_baseline()
        if count > base:
            print(f"REGRESSION: {count} > baseline {base}", file=sys.stderr)
            return 1
    if args.strict and count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
