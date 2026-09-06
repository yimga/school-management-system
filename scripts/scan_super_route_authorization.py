#!/usr/bin/env python
"""Authorization inventory for the /super/ operator control plane.

WHY THIS EXISTS
---------------
`scripts/audit_role_permission_matrix.py` discovers urlconfs with
``APPS.rglob("urls*.py")`` (that file, line 648).  That glob is a PREFIX
match: it sees ``urls.py`` and ``urls_api.py`` but never ``super_urls.py``.
The four-entry ``EXTRA_URLS_FILES`` allowlist (same file, lines 64-69)
rescues ``config/urls.py``, ``config/manager_urls.py``, ``config/routing.py``
and ``apps/apicenter/oauth_urls.py`` -- and nothing else.  So every route in
``apps/schools/super_urls.py`` is absent from
``docs/generated/role_permission_matrix.csv``: not filtered, never read.

This scanner closes that hole for the control plane specifically.  It is
stdlib-only (ast / pathlib / json / argparse) and never imports Django, so it
can ride the deps-free boundary workflow.

WHAT "GUARD" MEANS HERE
-----------------------
A route is only counted as proven when an *authorization* gate is
discoverable.  ``@require_GET`` and ``@csrf_exempt`` are NOT authorization:
they constrain the method or the CSRF posture of a request that has already
been let through.  Routes carrying only those land in ``METHOD_ONLY``, which
is reported separately and never folded into the proven count.

STATUSES
--------
    AUTHZ_PROVEN  an authorization gate is discoverable (URL wrapper,
                  def-site decorator, ``method_decorator`` on a CBV, or an
                  access mixin in the class bases).
    METHOD_ONLY   decorators exist but none of them authorize.
    UNGUARDED     the view resolved and carries no decorator/mixin at all.
    UNRESOLVED    the view definition could not be located statically.
    MOUNT         ``include(...)`` -- a mount point, not a leaf route.

UNRESOLVED counts as *unclassified*, never as safe.  A resolver bug must make
this gate louder, not quieter: a bucket excluded from the denominator
flatters the score.

HONEST CAVEATS
--------------
- Resolution is static and follows re-export hops up to ``_MAX_HOPS``.  A view
  reached through a dynamic dispatch table is reported UNRESOLVED, not proven.
- A decorator is matched by NAME.  A gate named like an authorization gate but
  implemented as a no-op would score as proven here.  This inventory proves a
  gate is *wired*, not that it is *correct*.
- ``ast.walk`` is breadth-first.  Nothing here depends on walk ordering:
  ``path()`` calls are collected independently and sorted by line number, and
  decorators are read off ``node.decorator_list`` directly.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_URLCONF = ROOT / "apps" / "schools" / "super_urls.py"
OUT_JSON = ROOT / "docs" / "generated" / "super_route_authorization.json"
BASELINE = ROOT / "var" / "super-route-authorization-baseline.json"

_MAX_HOPS = 5

# The module's common wrapper, applied at the URL layer in super_urls.py.
COMMON_WRAPPER = "require_super_access_with_host"

# Authorization / authentication gates.  Seeded from the set already curated
# in scripts/audit_role_permission_matrix.py (_AUTH_GATING_NAMES, lines
# 120-162) so the two scanners share one vocabulary.
AUTH_GUARDS = {
    "login_required",
    "staff_member_required",
    "user_passes_test",
    "permission_required",
    "role_required",
    "require_super_access_with_host",
    "require_super_access",
    "require_control_plane_access",
    "control_plane_only",
    "superadmin_required",
    "school_admin_required",
    "tenant_admin_required",
    "require_school",
    "require_school_permission",
    "require_permission",
    "require_feature",
    "require_parent_child_access",
    "finance_access_required",
    "evaluation_access_required",
    "invoice_access_required",
    "student_detail_access_required",
    "object_permission_required",
    "mfa_required",
    "require_platform_scope",
    "require_verified_publisher_with_host",
    "observability_auth_required",
    "webhook_security_required",
}

# Class-based-view access mixins.  Presence in `bases` is an authorization gate.
AUTH_MIXINS = {
    "LoginRequiredMixin",
    "PermissionRequiredMixin",
    "UserPassesTestMixin",
    "AccessMixin",
    "StaffRequiredMixin",
    "SuperuserRequiredMixin",
    "SuperAdminRequiredMixin",
    "ControlPlaneRequiredMixin",
    "ControlPlaneAccessMixin",
    "SuperAccessMixin",
    "OperatorRequiredMixin",
    "TenantAdminRequiredMixin",
}

METHOD_GUARDS = {"require_POST", "require_GET", "require_http_methods", "require_safe"}
CSRF_MARKERS = {"csrf_exempt", "csrf_protect", "requires_csrf_token", "ensure_csrf_cookie"}
STEP_UP_MARKERS = {"mfa_required", "require_step_up", "step_up_required", "reauth_required"}
RATE_LIMIT_MARKERS = {"ratelimit", "rate_limit", "rate_limit_super", "throttle"}

# Callables that wrap a view in super_urls.py but are not themselves the view.
TRANSPARENT_WRAPPERS = {"partial"}

CBV_ENTRY_METHODS = {"dispatch", "get", "post", "put", "patch", "delete", "head"}


# ----------------------------------------------------------------------
# AST helpers
# ----------------------------------------------------------------------

def _decorator_name(node):
    """Base name of an expression: ``a.b.c(...)`` -> ``c``."""
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _expand_decorator(node):
    """Names contributed by one decorator.

    ``method_decorator(staff_member_required, name="dispatch")`` contributes
    BOTH ``method_decorator`` and the inner ``staff_member_required`` -- the
    inner one is the gate that actually matters.
    """
    names = []
    base = _decorator_name(node)
    if base:
        names.append(base)
    if isinstance(node, ast.Call) and base in {"method_decorator", "decorator_from_middleware"}:
        for arg in node.args:
            inner = _decorator_name(arg)
            if inner:
                names.append(inner)
            elif isinstance(arg, (ast.List, ast.Tuple)):
                for elt in arg.elts:
                    sub = _decorator_name(elt)
                    if sub:
                        names.append(sub)
    return names


def _parse(path):
    try:
        return ast.parse(path.read_bytes().decode("utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


# ----------------------------------------------------------------------
# Module / symbol resolution
# ----------------------------------------------------------------------

class Resolver:
    """Static resolver: dotted module -> file, symbol -> definition node."""

    def __init__(self, source_root):
        self.source_root = source_root
        self._tree_cache = {}
        self._import_cache = {}

    def module_file(self, dotted):
        if not dotted:
            return None
        parts = dotted.split(".")
        cand = self.source_root.joinpath(*parts).with_suffix(".py")
        if cand.is_file():
            return cand
        pkg = self.source_root.joinpath(*parts, "__init__.py")
        if pkg.is_file():
            return pkg
        return None

    def tree(self, dotted):
        if dotted not in self._tree_cache:
            f = self.module_file(dotted)
            self._tree_cache[dotted] = _parse(f) if f else None
        return self._tree_cache[dotted]

    def import_maps(self, dotted):
        """(module_aliases, symbol_imports) for a module.

        module_aliases: local name -> dotted module
        symbol_imports: local name -> (dotted module, original symbol name)
        """
        if dotted in self._import_cache:
            return self._import_cache[dotted]
        module_aliases = {}
        symbol_imports = {}
        tree = self.tree(dotted)
        if tree is None:
            self._import_cache[dotted] = (module_aliases, symbol_imports)
            return module_aliases, symbol_imports

        file = self.module_file(dotted)
        is_pkg = bool(file and file.name == "__init__.py")
        parts = dotted.split(".")
        own_package = parts if is_pkg else parts[:-1]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_aliases[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base_parts = own_package[: len(own_package) - (node.level - 1)]
                    base = ".".join(base_parts)
                    if node.module:
                        base = "{}.{}".format(base, node.module) if base else node.module
                else:
                    base = node.module or ""
                for alias in node.names:
                    local = alias.asname or alias.name
                    child = "{}.{}".format(base, alias.name) if base else alias.name
                    # `from pkg import name` is ambiguous: name may be a
                    # submodule or a symbol.  A file on disk decides it.
                    if self.module_file(child):
                        module_aliases[local] = child
                    elif base:
                        symbol_imports[local] = (base, alias.name)
        self._import_cache[dotted] = (module_aliases, symbol_imports)
        return module_aliases, symbol_imports

    def definition(self, dotted, name, _hops=0):
        """Find a top-level def/class ``name`` in module ``dotted``.

        Follows re-export hops up to ``_MAX_HOPS``.
        Returns ``(node, defining_module)`` or ``(None, None)``.
        """
        if _hops > _MAX_HOPS:
            return None, None
        tree = self.tree(dotted)
        if tree is None:
            return None, None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    return node, dotted
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == name:
                        return self.definition(dotted, node.value.id, _hops + 1)
        _, symbol_imports = self.import_maps(dotted)
        if name in symbol_imports:
            mod, orig = symbol_imports[name]
            return self.definition(mod, orig, _hops + 1)
        return None, None


# ----------------------------------------------------------------------
# Guard extraction
# ----------------------------------------------------------------------

def guards_from_definition(node):
    """Every guard-ish name attached to a view definition."""
    decorators = []
    mixins = []
    method_decorators = []

    for d in getattr(node, "decorator_list", []):
        decorators.extend(_expand_decorator(d))

    if isinstance(node, ast.ClassDef):
        for base in node.bases:
            bname = _decorator_name(base)
            if bname:
                mixins.append(bname)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name in CBV_ENTRY_METHODS:
                    for d in item.decorator_list:
                        method_decorators.extend(_expand_decorator(d))
    return {
        "decorators": decorators,
        "base_classes": mixins,
        "method_decorators": method_decorators,
    }


def classify(url_guards, defsite):
    """Return ``(status, authorization guards found)``."""
    if defsite is None:
        found = sorted({g for g in url_guards if g in AUTH_GUARDS})
        if found:
            return "AUTHZ_PROVEN", found
        return "UNRESOLVED", []

    all_names = list(url_guards) + defsite["decorators"] + defsite["method_decorators"]
    mixins = defsite["base_classes"]

    authz = sorted(
        {n for n in all_names if n in AUTH_GUARDS} | {m for m in mixins if m in AUTH_MIXINS}
    )
    if authz:
        return "AUTHZ_PROVEN", authz

    # No authorization.  Is there anything at all?
    non_auth = [n for n in all_names if n != "method_decorator"]
    if non_auth:
        return "METHOD_ONLY", []
    return "UNGUARDED", []


# ----------------------------------------------------------------------
# URL scanning
# ----------------------------------------------------------------------

def _urlpatterns_nodes(tree):
    """Every expression that contributes routes to ``urlpatterns``.

    A urlconf is not always one literal list.  ``config/urls.py`` and three
    siblings build theirs with ``urlpatterns += [...]`` and
    ``urlpatterns.append(...)``; scoping to the initial assignment alone would
    silently miss every route added that way and report a confident undercount.
    """
    nodes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "urlpatterns":
                    nodes.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "urlpatterns" and node.value is not None:
                nodes.append(node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "urlpatterns":
                nodes.append(node.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            holder = node.func.value
            if (
                isinstance(holder, ast.Name)
                and holder.id == "urlpatterns"
                and node.func.attr in {"append", "extend", "insert"}
            ):
                nodes.extend(node.args)
    return nodes


def _unwrap_view(expr):
    """Peel URL-layer wrappers off a view expression.

    Returns ``(wrapper names outermost-first, innermost expression, is_include)``.
    """
    wrappers = []
    node = expr
    for _ in range(_MAX_HOPS):
        if isinstance(node, ast.Call):
            fname = _decorator_name(node.func)
            if fname == "include":
                return wrappers, node, True
            if fname == "as_view":
                # `SomeView.as_view()` -- the class itself is the view.
                if isinstance(node.func, ast.Attribute):
                    return wrappers, node.func.value, False
                return wrappers, None, False
            if fname in TRANSPARENT_WRAPPERS:
                node = node.args[0] if node.args else None
                if node is None:
                    return wrappers, None, False
                continue
            if fname:
                wrappers.append(fname)
            node = node.args[0] if node.args else None
            if node is None:
                return wrappers, None, False
            continue
        return wrappers, node, False
    return wrappers, node, False


_EMPTY_ROW = {
    "url_wrappers": [],
    "guard_family": "none",
    "view_module": None,
    "view_symbol": None,
    "view_kind": None,
    "authz_guards": [],
    "decorators": [],
    "base_classes": [],
    "method_decorators": [],
    "method_guards": [],
    "csrf": [],
    "step_up": [],
    "rate_limits": [],
}


def scan(urlconf, source_root):
    tree = _parse(urlconf)
    if tree is None:
        raise SystemExit("cannot parse urlconf: {}".format(urlconf))
    pattern_nodes = _urlpatterns_nodes(tree)
    if not pattern_nodes:
        raise SystemExit("no urlpatterns in {}".format(urlconf))

    resolver = Resolver(source_root)
    try:
        rel = urlconf.resolve().relative_to(source_root.resolve())
        self_dotted = ".".join(rel.with_suffix("").parts)
    except ValueError:
        self_dotted = urlconf.stem
    resolver._tree_cache[self_dotted] = tree
    module_aliases, symbol_imports = resolver.import_maps(self_dotted)

    seen = set()
    calls = []
    for scope in pattern_nodes:
        for n in ast.walk(scope):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id in {"path", "re_path"}
                and (n.lineno, n.col_offset) not in seen
            ):
                seen.add((n.lineno, n.col_offset))
                calls.append(n)
    # ast.walk is breadth-first; never rely on its order.
    calls.sort(key=lambda n: (n.lineno, n.col_offset))

    rows = []
    for call in calls:
        if not call.args:
            continue
        pat_node = call.args[0]
        pattern = pat_node.value if isinstance(pat_node, ast.Constant) else ast.unparse(pat_node)
        name = None
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name = kw.value.value
        view_expr = call.args[1] if len(call.args) > 1 else None

        row = {
            "line": call.lineno,
            "route": pattern,
            "url_name": name,
            "urlconf": urlconf.name,
            "view_expr": ast.unparse(view_expr) if view_expr is not None else None,
        }
        row.update(_EMPTY_ROW)

        if view_expr is None:
            row["status"] = "UNRESOLVED"
            rows.append(row)
            continue

        wrappers, inner, is_include = _unwrap_view(view_expr)

        if is_include:
            target = None
            if isinstance(inner, ast.Call) and inner.args and isinstance(inner.args[0], ast.Constant):
                target = inner.args[0].value
            row["status"] = "MOUNT"
            row["url_wrappers"] = wrappers
            row["guard_family"] = "mount"
            row["view_module"] = target
            row["view_kind"] = "include"
            rows.append(row)
            continue

        # Resolve the innermost symbol to a module + name.
        mod = sym = None
        if isinstance(inner, ast.Name):
            if inner.id in symbol_imports:
                mod, sym = symbol_imports[inner.id]
            else:
                mod, sym = self_dotted, inner.id
        elif isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name):
            holder = inner.value.id
            if holder in module_aliases:
                mod, sym = module_aliases[holder], inner.attr
            elif holder in symbol_imports:
                mod, sym = symbol_imports[holder][0], inner.attr

        node = None
        defining_module = None
        if mod and sym:
            node, defining_module = resolver.definition(mod, sym)

        defsite = guards_from_definition(node) if node is not None else None
        status, authz = classify(wrappers, defsite)

        if COMMON_WRAPPER in wrappers:
            family = "common_wrapper"
        elif wrappers:
            family = "specialised_url_wrapper"
        elif authz:
            family = "specialised_defsite"
        else:
            family = "none"

        d = defsite or {"decorators": [], "base_classes": [], "method_decorators": []}
        all_names = wrappers + d["decorators"] + d["method_decorators"]
        row["status"] = status
        row["url_wrappers"] = wrappers
        row["guard_family"] = family
        row["view_module"] = defining_module or mod
        row["view_symbol"] = sym
        if node is not None:
            row["view_kind"] = "class" if isinstance(node, ast.ClassDef) else "function"
        row["authz_guards"] = authz
        row["decorators"] = d["decorators"]
        row["base_classes"] = d["base_classes"]
        row["method_decorators"] = d["method_decorators"]
        row["method_guards"] = sorted({n for n in all_names if n in METHOD_GUARDS})
        row["csrf"] = sorted({n for n in all_names if n in CSRF_MARKERS})
        row["step_up"] = sorted({n for n in all_names if n in STEP_UP_MARKERS})
        row["rate_limits"] = sorted({n for n in all_names if n in RATE_LIMIT_MARKERS})
        rows.append(row)
    return rows


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------

def route_key(row):
    return "{}::{}::{}".format(row["urlconf"], row["url_name"] or "<unnamed>", row["route"])


def unclassified_keys(rows):
    """Routes with NO discoverable authorization gate."""
    return sorted(route_key(r) for r in rows if r["status"] in {"UNGUARDED", "UNRESOLVED"})


def partial_keys(rows):
    return sorted(route_key(r) for r in rows if r["status"] == "METHOD_ONLY")


def summarise(rows):
    counts = {}
    families = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        families[r["guard_family"]] = families.get(r["guard_family"], 0) + 1
    leaf = [r for r in rows if r["status"] != "MOUNT"]
    return {
        "total_url_entries": len(rows),
        "leaf_routes": len(leaf),
        "mounts": len(rows) - len(leaf),
        "by_status": dict(sorted(counts.items())),
        "by_guard_family": dict(sorted(families.items())),
        "fully_classified": counts.get("AUTHZ_PROVEN", 0),
        "partially_classified": counts.get("METHOD_ONLY", 0),
        "unclassified": counts.get("UNGUARDED", 0) + counts.get("UNRESOLVED", 0),
    }


def write_json(path, payload):
    """docs/generated/*.json is `text eol=lf` in .gitattributes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(data.encode("utf-8"))


def write_baseline(path, payload):
    """var/*-baseline.json follows the repo default (CRLF working tree)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(data.replace("\n", "\r\n").encode("utf-8"))


def human_summary(rows, summary):
    lines = []
    lines.append("/super/ route authorization inventory")
    lines.append("=" * 44)
    lines.append("  url entries scanned : {}".format(summary["total_url_entries"]))
    lines.append("  leaf routes         : {}".format(summary["leaf_routes"]))
    lines.append("  include() mounts    : {}".format(summary["mounts"]))
    lines.append("")
    lines.append("  status:")
    for k, v in summary["by_status"].items():
        lines.append("    {:<14} {:>5}".format(k, v))
    lines.append("")
    lines.append("  guard family:")
    for k, v in summary["by_guard_family"].items():
        lines.append("    {:<24} {:>5}".format(k, v))
    part = [r for r in rows if r["status"] == "METHOD_ONLY"]
    unc = [r for r in rows if r["status"] in {"UNGUARDED", "UNRESOLVED"}]
    if part:
        lines.append("")
        lines.append("  METHOD_ONLY (decorated, but nothing authorizes) -- {}:".format(len(part)))
        for r in part:
            marks = ",".join(r["method_guards"] + r["csrf"]) or "-"
            lines.append("    L{:<6} {:<50} [{}]".format(r["line"], r["route"][:50], marks))
    if unc:
        lines.append("")
        lines.append("  UNCLASSIFIED -- {}:".format(len(unc)))
        for r in unc:
            lines.append(
                "    L{:<6} {:<11} {:<46} {}".format(
                    r["line"], r["status"], r["route"][:46], r["view_expr"] or ""
                )
            )
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--urlconf", default=str(DEFAULT_URLCONF), help="urlconf to scan")
    ap.add_argument("--source-root", default=str(ROOT), help="import root for view resolution")
    ap.add_argument("--out", default=str(OUT_JSON), help="inventory JSON destination ('' to skip)")
    ap.add_argument("--baseline", default=str(BASELINE), help="ratchet baseline path")
    ap.add_argument("--compare", action="store_true", help="fail on routes unclassified beyond baseline")
    ap.add_argument("--write-baseline", action="store_true", help="record the current unclassified set")
    ap.add_argument("--strict", action="store_true", help="with --compare, also ratchet METHOD_ONLY")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    urlconf = Path(args.urlconf).resolve()
    source_root = Path(args.source_root).resolve()
    rows = scan(urlconf, source_root)
    summary = summarise(rows)
    unc = unclassified_keys(rows)
    part = partial_keys(rows)

    try:
        shown = str(urlconf.relative_to(source_root)).replace("\\", "/")
    except ValueError:
        shown = str(urlconf)

    payload = {
        "generator": "scripts/scan_super_route_authorization.py",
        "urlconf": shown,
        "summary": summary,
        "unclassified": unc,
        "partially_classified": part,
        "routes": rows,
    }
    if args.out:
        write_json(Path(args.out), payload)

    if args.write_baseline:
        write_baseline(
            Path(args.baseline),
            {
                "_comment": (
                    "Routes under /super/ with no discoverable authorization gate. "
                    "Ratchet DOWN only. scripts/scan_super_route_authorization.py "
                    "--compare fails on anything not listed here."
                ),
                "unclassified": unc,
                "partially_classified": part,
            },
        )

    if not args.quiet:
        print(human_summary(rows, summary))

    if args.compare:
        try:
            base = json.loads(Path(args.baseline).read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            print("\nFAIL: baseline missing or unreadable: {}".format(args.baseline), file=sys.stderr)
            return 1
        base_unc = set(base.get("unclassified", []))
        base_part = set(base.get("partially_classified", []))
        new_unc = sorted(set(unc) - base_unc)
        new_part = sorted(set(part) - base_part) if args.strict else []
        fixed = sorted(base_unc - set(unc))
        if fixed:
            print(
                "\nRATCHET: {} baselined route(s) now guarded -- re-run --write-baseline.".format(
                    len(fixed)
                )
            )
        if new_unc or new_part:
            print("\nFAIL: newly unclassified /super/ route(s):", file=sys.stderr)
            for k in new_unc + new_part:
                print("  {}".format(k), file=sys.stderr)
            return 1
        print("\nOK: 0 new unclassified routes ({} still baselined).".format(len(base_unc)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
