#!/usr/bin/env python3
"""Emit manager-host HTML paths for abrupt-end Playwright sweep.

Usage:
  python scripts/generate_control_plane_sweep_routes.py --write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

OUT = REPO_ROOT / "docs" / "generated" / "control_plane_sweep_routes.json"

SKIP_PREFIXES = (
    "/api/",
    "/static/",
    "/media/",
    "/-/version/",
    "/i18n/",
    "/__debug__/",
    "/internal-admin/",
)
SKIP_SUFFIXES = (".json", ".csv", ".xml", ".txt", ".ico", ".png", ".js", ".css")
SKIP_EXACT = {"/favicon.ico", "/robots.txt", "/sitemap.xml"}
ADMIN_NON_CHANGELIST_SUFFIXES = (
    "/add/",
    "/delete/",
    "/history/",
    "/change/",
    "/autocomplete/",
    "/view/",
    "/done/",
)
# Django admin auth flows (not model changelists): /admin/password_change/done/
ADMIN_NON_MODEL_SEGMENTS = frozenset(
    {"password_change", "login", "logout", "jsi18n", "rjs"},
)
# Operator HTML surfaces (extends control_plane_base / manager shells).
OPERATOR_PREFIXES = (
    "/super/",
    "/configuration/",
    "/studio/",
    "/sales/",
    "/siteconfig/",
    "/automation/",
    "/orchestration/",
    "/observability/",
    "/feedback/",
    "/customersuccess/",
    "/offline/",
    "/help/",
    "/support/",
    "/notifications/",
    "/academics/",
    "/metadata/",
    "/marketplace/",
)
OPERATOR_EXACT = {"/", "/admin/"}


def _list_routes(urlpatterns, prefix: str = ""):
    from django.urls import URLPattern, URLResolver

    for entry in urlpatterns:
        if isinstance(entry, URLResolver):
            seg = str(entry.pattern)
            yield from _list_routes(entry.url_patterns, prefix + seg)
        elif isinstance(entry, URLPattern):
            yield prefix + str(entry.pattern), entry.name


def _normalize(path: str) -> str:
    path = re.sub(r"<[^>]+>", "", path)
    path = path.replace("\\", "")
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"/+", "/", path)
    if not path.endswith("/"):
        path += "/"
    return path


def _admin_changelist_only(path: str) -> bool:
    if not path.startswith("/admin/"):
        return False
    if any(path.endswith(s) for s in ADMIN_NON_CHANGELIST_SUFFIXES):
        return False
    parts = [p for p in path.strip("/").split("/") if p]
    # /admin/<app_label>/<model_name>/
    return (
        len(parts) == 3
        and parts[0] == "admin"
        and parts[1] not in ADMIN_NON_MODEL_SEGMENTS
    )


def _include_path(path: str, name: str | None) -> bool:
    if path in SKIP_EXACT:
        return False
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return False
    if "/api/" in path:
        return False
    if "/export/" in path or path.rstrip("/").endswith((".csv", ".pdf", ".json")):
        return False
    if any(path.endswith(s) for s in SKIP_SUFFIXES):
        return False
    if "<" in path or ">" in path or "?" in path:
        return False
    if _admin_changelist_only(path):
        return True
    if path in OPERATOR_EXACT:
        return True
    if any(path.startswith(p) for p in OPERATOR_PREFIXES):
        return True
    # Drop raw admin sub-actions and non-operator URLconf noise.
    if path.startswith("/admin/"):
        return False
    return False


def _route_tier(path: str) -> str:
    if _admin_changelist_only(path):
        return "admin_changelist"
    return "operator"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    import django

    django.setup()
    from django.urls import get_resolver

    resolver = get_resolver("config.manager_urls")
    rows = []
    seen = set()
    for raw, name in _list_routes(resolver.url_patterns):
        path = _normalize(raw)
        if not _include_path(path, name):
            continue
        if path in seen:
            continue
        seen.add(path)
        rows.append(
            {
                "path": path,
                "name": name or "",
                "tier": _route_tier(path),
                "sweep": True,
            }
        )

    rows.sort(key=lambda r: r["path"])
    operator_count = sum(1 for r in rows if r["tier"] == "operator")
    admin_count = sum(1 for r in rows if r["tier"] == "admin_changelist")
    payload = {
        "version": "2026-05-18",
        "count": len(rows),
        "operator_count": operator_count,
        "admin_changelist_count": admin_count,
        "routes": rows,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(rows)} routes to {OUT}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
