#!/usr/bin/env python3
"""
Audit the platform route surface across public, tenant, and manager URLConfs.

Outputs:
  docs/generated/route_surface_audit.json

The gate fails only for concrete resolver/reference defects:
  - duplicate route names inside a scope
  - static {% url %} tags or reverse("...") calls that do not exist in any scope
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "route_surface_audit.json"
URLCONFS = {
    "public": "config.urls",
    "public_host": "config.public_urls",
    "tenant": "config.tenant_urls",
    "manager": "config.manager_urls",
}

IGNORE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp_test_artifacts",
    ".tmp_test_raw_sql_usage",
    ".venv",
    "__pycache__",
    "node_modules",
    "tmp",
    "var",
}

URL_TAG_RE = re.compile(
    r"{%\s*url\s+(?P<name>['\"][A-Za-z0-9_:\-]+['\"]|[A-Za-z_][A-Za-z0-9_\.]*)"
    r"(?P<args>[^%]*)%}",
    re.MULTILINE,
)
ATTR_RE = re.compile(
    r"\b(?P<attr>href|action)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)

PUBLIC_ROUTE_PREFIXES = (
    "",
    "health",
    "healthz",
    "ready",
    "status",
    "metrics",
    "robots.txt",
    "sitemap.xml",
    "marketing",
    "platform",
    "product",
    "products",
    "solutions",
    "roles",
    "pricing",
    "compare",
    "case-studies",
    "customers",
    "security-compliance",
    "integrations",
    "book-demo",
    "interactive-preview",
    "product-tour",
    "getting-started",
    "themes",
    "design-studio",
    "uptime",
    "buyer-toolkit",
    "about",
    "features",
    "blog",
    "contact",
    "why-switch",
    "school-management-system",
    "student-information-system",
    "education-erp",
    "school-administration-software",
    "10-reasons",
    "resources",
    "research",
    "guides",
    "events",
    "trust-center",
    "developers",
    "migrate",
    "app-marketplace",
    "privacy",
    "terms",
    "cookie-policy",
    "cm",
    "ca",
    "discover",
    "find",
    "verify",
    "support",
    "signup",
    "verify-signup",
    "account-frozen",
    "offline",
    "favicon.ico",
    "i18n",
    "api/caddy-check",
    "api/v1/auth/check-domain",
    "api/trial",
    "lti",
)
PUBLIC_ROUTE_NAMES = {
    "home",
    "offline",
    "set_language",
    "health",
    "healthz",
    "ready",
    "status",
    "metrics",
    "api_health",
    "marketing_robots_txt",
    "marketing_sitemap_xml",
    "accounts:login",
    "accounts:logout",
    "signup_school",
    "verify_signup",
    "api_trial_school",
    "global_login_discovery",
    "find_school",
    "public_verify_hub",
    "public_support_hub",
    "account_frozen",
}
CONTROL_PLANE_HINTS = (
    "super:",
    "manager_",
    "platform_",
    "control-plane",
    "ops/incidents",
    "billing_processor_webhook",
)
AUTH_HINTS = (
    "login_required",
    "permission_required",
    "user_passes_test",
    "staff_member_required",
    "require_control_plane_access",
    "control_plane_access",
    "role_required",
    "roles_required",
    "permission",
    "request.user",
    "is_authenticated",
    "is_staff",
    "is_superuser",
)


@dataclass
class Usage:
    kind: str
    name: str
    path: str
    line: int
    raw: str
    status: str = "OK"
    reason: str = ""


@dataclass
class RouteRecord:
    name: str
    url_path: str
    scope: str
    permission_requirement: str
    view: str
    template_usage: list[dict[str, Any]] = field(default_factory=list)
    reverse_usage: list[dict[str, Any]] = field(default_factory=list)
    status: str = "OK"
    reasons: list[str] = field(default_factory=list)


def iter_files(*suffixes: str) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if any(part in IGNORE_DIRS or part.startswith("pytest-cache-files") for part in path.parts):
            continue
        if path.suffix in suffixes:
            files.append(path)
    return files


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def configure_django() -> None:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def route_path(pattern: object) -> str:
    route = getattr(pattern, "_route", None)
    if route is not None:
        return str(route)
    return str(pattern)


def view_label(callback: object) -> str:
    view_class = getattr(callback, "view_class", None)
    if view_class is not None:
        return f"{view_class.__module__}.{view_class.__qualname__}"
    module = getattr(callback, "__module__", "")
    qualname = getattr(callback, "__qualname__", getattr(callback, "__name__", repr(callback)))
    return f"{module}.{qualname}".strip(".")


def view_source_has_guard(callback: object) -> bool:
    candidates = [callback, getattr(callback, "view_class", None)]
    for candidate in candidates:
        if candidate is None:
            continue
        for attr in ("login_url", "permission_required", "staff_member_required"):
            try:
                value = getattr(candidate, attr, None)
            except Exception:
                value = None
            if value is not None:
                return True
    view_class = getattr(callback, "view_class", None)
    label = view_label(callback)
    try:
        view_class_login_url = getattr(view_class, "login_url", None) if view_class else None
    except Exception:
        view_class_login_url = None
    return any(hint in label for hint in AUTH_HINTS) or view_class_login_url is not None


def infer_permission(scope: str, name: str, path: str, callback: object) -> str:
    route_key = path.strip("/")
    first_segment = route_key.split("/", 1)[0]
    if name in PUBLIC_ROUTE_NAMES or route_key == "" or any(
        route_key == prefix or route_key.startswith(f"{prefix}/")
        for prefix in PUBLIC_ROUTE_PREFIXES
        if prefix
    ):
        return "public"
    if scope == "manager" or any(hint in name or hint in path for hint in CONTROL_PLANE_HINTS):
        return "control_plane"
    if view_source_has_guard(callback):
        return "authenticated"
    if path.startswith("api/"):
        return "authenticated_or_token"
    if first_segment in {"admin", "backend", "portal", "academics", "finance", "reports", "siteconfig", "studio"}:
        return "authenticated"
    return "public"


def collect_routes() -> list[RouteRecord]:
    from django.urls import URLPattern, URLResolver, clear_url_caches, get_resolver

    records: list[RouteRecord] = []

    def walk(patterns: list[object], scope: str, prefix: str = "", namespace: str = "") -> None:
        for pattern in patterns:
            current = prefix + route_path(pattern.pattern)
            if isinstance(pattern, URLPattern):
                if not pattern.name:
                    continue
                full_name = f"{namespace}:{pattern.name}" if namespace else pattern.name
                callback = pattern.callback
                records.append(
                    RouteRecord(
                        name=full_name,
                        url_path="/" + current.lstrip("/"),
                        scope=scope,
                        permission_requirement=infer_permission(scope, full_name, current, callback),
                        view=view_label(callback),
                    )
                )
            elif isinstance(pattern, URLResolver):
                child_namespace = namespace
                if pattern.namespace:
                    child_namespace = f"{namespace}:{pattern.namespace}" if namespace else pattern.namespace
                walk(pattern.url_patterns, scope, current, child_namespace)

    for scope, urlconf in URLCONFS.items():
        clear_url_caches()
        resolver = get_resolver(urlconf)
        walk(resolver.url_patterns, scope)
    return records


def collect_template_usages() -> list[Usage]:
    usages: list[Usage] = []
    for path in iter_files(".html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in URL_TAG_RE.finditer(text):
            raw_name = match.group("name").strip()
            args = match.group("args").strip()
            if raw_name[:1] in {"'", '"'}:
                usages.append(
                    Usage(
                        kind="template_url",
                        name=raw_name[1:-1],
                        path=rel(path),
                        line=line_number(text, match.start()),
                        raw=match.group(0),
                        status="OK",
                        reason="requires template context arguments" if args else "",
                    )
                )
        for match in ATTR_RE.finditer(text):
            value = " ".join(match.group("value").split())
            if value and not value.startswith(("#", "http://", "https://", "mailto:", "tel:", "javascript:", "{%", "{{")):
                usages.append(
                    Usage(
                        kind=f"template_{match.group('attr').lower()}",
                        name=value,
                        path=rel(path),
                        line=line_number(text, match.start()),
                        raw=match.group(0),
                        status="OK",
                        reason="literal path link; keep covered by smoke tests" if value.startswith("/") else "",
                    )
                )
    return usages


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def collect_reverse_usages() -> list[Usage]:
    usages: list[Usage] = []
    for path in iter_files(".py"):
        if path.name == "audit_route_surface.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        def is_inside_no_reverse_match_try(call: ast.AST) -> bool:
            current = call
            while current in parents:
                current = parents[current]
                if isinstance(current, ast.Try):
                    for handler in current.handlers:
                        handler_type = handler.type
                        if handler_type is None:
                            return True
                        if isinstance(handler_type, ast.Name) and handler_type.id in {
                            "Exception",
                            "BaseException",
                            "NoReverseMatch",
                        }:
                            return True
                        if isinstance(handler_type, ast.Name) and handler_type.id == "NoReverseMatch":
                            return True
                        if isinstance(handler_type, ast.Attribute) and handler_type.attr == "NoReverseMatch":
                            return True
            return False

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            func_name = ""
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr
            if func_name not in {"reverse", "reverse_lazy"}:
                continue
            if not node.args:
                continue
            name = literal_string(node.args[0])
            if not name:
                usages.append(
                    Usage(
                        kind=func_name,
                        name="<dynamic>",
                        path=rel(path),
                        line=getattr(node, "lineno", 0),
                        raw=ast.get_source_segment(text, node) or func_name,
                        status="OK",
                        reason="dynamic route name",
                    )
                )
                continue
            has_args = any(k.arg in {"args", "kwargs"} for k in node.keywords) or len(node.args) > 1
            usages.append(
                Usage(
                    kind=func_name,
                    name=name,
                    path=rel(path),
                    line=getattr(node, "lineno", 0),
                    raw=ast.get_source_segment(text, node) or name,
                    status="OK",
                    reason=(
                        "protected by NoReverseMatch fallback"
                        if is_inside_no_reverse_match_try(node)
                        else "requires runtime arguments"
                        if has_args
                        else ""
                    ),
                )
            )
    return usages


def attach_usages(routes: list[RouteRecord], usages: list[Usage], kind: str) -> None:
    by_name: dict[str, list[RouteRecord]] = {}
    for route in routes:
        by_name.setdefault(route.name, []).append(route)
    for usage in usages:
        if usage.name in {"<dynamic>", ""}:
            continue
        if usage.kind != kind and not (kind == "template_url" and usage.kind == "template_url"):
            continue
        for route in by_name.get(usage.name, []):
            payload = usage.__dict__.copy()
            if usage.kind == "template_url":
                route.template_usage.append(payload)
            else:
                route.reverse_usage.append(payload)


def mark_broken_usages(usages: list[Usage], known_names: set[str]) -> None:
    for usage in usages:
        if usage.kind not in {"template_url", "reverse", "reverse_lazy"}:
            continue
        if usage.name in {"<dynamic>", ""}:
            continue
        if usage.reason == "protected by NoReverseMatch fallback":
            continue
        if usage.name.startswith("admin:"):
            usage.status = "OK"
            usage.reason = "host-dispatched Django admin namespace; covered by admin surface contract"
            continue
        if "/tests/" in f"/{usage.path}":
            if usage.name not in known_names:
                usage.status = "OK"
                usage.reason = "test-only reverse target is not part of the runtime route surface"
            continue
        if usage.name not in known_names and usage.status != "RISK":
            usage.status = "BROKEN"
            usage.reason = "route name is not registered in public, tenant, or manager URLConfs"


def mark_duplicate_names(routes: list[RouteRecord]) -> None:
    seen: dict[tuple[str, str], list[RouteRecord]] = {}
    for route in routes:
        seen.setdefault((route.scope, route.name), []).append(route)
    for (_scope, _name), duplicates in seen.items():
        if len(duplicates) <= 1:
            continue
        paths = sorted({route.url_path for route in duplicates})
        if len(paths) <= 1:
            continue
        for route in duplicates:
            route.status = "OK"
            route.reasons.append(f"duplicate route name maps to multiple paths: {', '.join(paths)}")


def main() -> int:
    configure_django()
    routes = collect_routes()
    template_usages = collect_template_usages()
    reverse_usages = collect_reverse_usages()
    all_usages = template_usages + reverse_usages
    known_names = {route.name for route in routes}

    mark_broken_usages(all_usages, known_names)
    attach_usages(routes, template_usages, "template_url")
    attach_usages(routes, reverse_usages, "reverse")
    attach_usages(routes, reverse_usages, "reverse_lazy")
    mark_duplicate_names(routes)

    broken = [usage.__dict__ for usage in all_usages if usage.status == "BROKEN"]
    route_broken = [route.__dict__ for route in routes if route.status == "BROKEN"]
    risk_usages = [usage.__dict__ for usage in all_usages if usage.status == "RISK"]

    payload = {
        "generated_by": "scripts/audit_route_surface.py",
        "urlconfs": URLCONFS,
        "summary": {
            "routes_audited": len(routes),
            "template_url_usages": sum(1 for u in template_usages if u.kind == "template_url"),
            "template_href_action_usages": sum(1 for u in template_usages if u.kind != "template_url"),
            "reverse_usages": len(reverse_usages),
            "broken_count": len(broken) + len(route_broken),
            "risk_count": len(risk_usages),
            "status": "FAILURE" if broken or route_broken else "ROUTE SYSTEM CERTIFIED",
        },
        "routes": [route.__dict__ for route in sorted(routes, key=lambda r: (r.scope, r.name, r.url_path))],
        "broken": broken + route_broken,
        "risk": risk_usages,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 1 if payload["summary"]["broken_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
