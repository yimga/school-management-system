"""
Live topology reflection: URL registry + coarse permission signals for AI context.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache
from django.urls import URLPattern, URLResolver, get_resolver

logger = logging.getLogger(__name__)

_CACHE_KEY = "ai:topology:reflection:v1"
_CACHE_TTL = 3600


def _decorator_names(func: Any) -> list[str]:
    names: list[str] = []
    current = func
    seen: set[int] = set()
    for _ in range(12):
        if current is None:
            break
        oid = id(current)
        if oid in seen:
            break
        seen.add(oid)
        if hasattr(current, "__name__"):
            names.append(current.__name__)
        current = getattr(current, "__func__", None) or getattr(current, "__wrapped__", None)
    return names


def _permission_signals(view: Any) -> list[str]:
    signals: list[str] = []
    if view is None:
        return signals
    for name in _decorator_names(view):
        low = name.lower()
        if "login_required" in low or low == "login_required":
            signals.append("login_required")
        if "staff_member_required" in low or "staff_required" in low:
            signals.append("staff_required")
        if "permission_required" in low:
            signals.append("permission_required")
        if "user_passes_test" in low:
            signals.append("custom_test")
    cls = getattr(view, "view_class", None) or (
        view.cls if hasattr(view, "cls") else None
    )
    if cls is not None:
        perms = getattr(cls, "permission_classes", None) or []
        for perm in perms:
            label = getattr(perm, "__name__", None) or perm.__class__.__name__
            if label:
                signals.append(f"drf:{label}")
    return list(dict.fromkeys(signals))


def _walk_patterns(patterns, prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            nested = (prefix + str(pattern.pattern)).replace("//", "/")
            rows.extend(_walk_patterns(pattern.url_patterns, nested))
            continue
        if not isinstance(pattern, URLPattern):
            continue
        route = (prefix + str(pattern.pattern)).replace("//", "/")
        if not route.startswith("/"):
            route = "/" + route
        callback = pattern.callback
        view = getattr(callback, "cls", callback)
        methods: list[str] = []
        if hasattr(view, "http_method_names"):
            methods = [m.upper() for m in view.http_method_names if m != "options"]
        elif callable(callback):
            methods = ["GET"]
        rows.append(
            {
                "url_path": route,
                "name": pattern.name,
                "required_permissions": _permission_signals(callback),
                "allowable_methods": methods or ["GET"],
            }
        )
    return rows


class DynamicSystemInspector:
    """Caches Django URL topology with permission hints for AI grounding."""

    def __init__(self, *, cache_ttl: int = _CACHE_TTL) -> None:
        self.cache_ttl = cache_ttl

    @staticmethod
    def invalidate_cache() -> None:
        cache.delete(_CACHE_KEY)

    def refresh(self) -> list[dict[str, Any]]:
        try:
            resolver = get_resolver()
            registry = _walk_patterns(resolver.url_patterns)
            cache.set(_CACHE_KEY, registry, timeout=self.cache_ttl)
            return registry
        except Exception as exc:
            logger.warning("DynamicSystemInspector refresh failed: %s", exc)
            return []

    def get_route_registry(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        if not force_refresh:
            cached = cache.get(_CACHE_KEY)
            if isinstance(cached, list) and cached:
                return cached
        return self.refresh()

    def match_path(self, path: str) -> dict[str, Any] | None:
        normalized = (path or "").strip() or "/"
        if not normalized.startswith("/"):
            normalized = "/" + normalized
        best: dict[str, Any] | None = None
        best_len = -1
        for row in self.get_route_registry():
            route = row.get("url_path") or ""
            if not route:
                continue
            if normalized == route or normalized.startswith(route.rstrip("/")):
                if len(route) > best_len:
                    best = row
                    best_len = len(route)
        return best

    def permissions_for_path(self, path: str) -> dict[str, Any]:
        row = self.match_path(path) or {}
        return {
            "url_path": row.get("url_path"),
            "required_permissions": list(row.get("required_permissions") or []),
            "allowable_methods": list(row.get("allowable_methods") or []),
            "route_name": row.get("name"),
        }


# Test hook: append synthetic routes without mutating Django's live resolver.
_TEST_REGISTRY_APPEND: list[dict[str, Any]] = []


def _append_test_registry_row(row: dict[str, Any]) -> None:
    _TEST_REGISTRY_APPEND.append(row)


def _clear_test_registry_rows() -> None:
    _TEST_REGISTRY_APPEND.clear()


def _merged_registry(inspector: DynamicSystemInspector) -> list[dict[str, Any]]:
    base = inspector.get_route_registry()
    if _TEST_REGISTRY_APPEND:
        return base + list(_TEST_REGISTRY_APPEND)
    return base


def match_path_with_test_hooks(inspector: DynamicSystemInspector, path: str) -> dict[str, Any] | None:
    normalized = (path or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    best: dict[str, Any] | None = None
    best_len = -1
    for row in _merged_registry(inspector):
        route = row.get("url_path") or ""
        if normalized == route or normalized.startswith(route.rstrip("/")):
            if len(route) > best_len:
                best = row
                best_len = len(route)
    return best
