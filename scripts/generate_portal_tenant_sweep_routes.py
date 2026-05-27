#!/usr/bin/env python3
"""Emit path-prefixed tenant URLs (/t/<slug>/...) for abrupt-end Playwright sweep.

Walks ``config.tenant_urls`` (same tree UrlConfSwitcherMiddleware uses) and
writes JSON for ``scripts/verify_platform_abrupt_end_sweep.mjs``.

Usage:
  python scripts/generate_portal_tenant_sweep_routes.py --write
  TENANT_SWEEP_SLUG=demo-school TENANT_SWEEP_MAX=200 python ... --write
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

OUT = REPO_ROOT / "docs" / "generated" / "portal_tenant_sweep_routes.json"

SKIP_PREFIXES = (
    "/api/",
    "/static/",
    "/media/",
    "/-/version/",
    "/i18n/",
    "/__debug__/",
    "/internal-admin/",
    "/metrics/",
    "/healthz/",
    "/health/",
    "/ready/",
    "/status/",
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
)
# Inner paths (under tenant urlconf) that are HTML shells / portal surfaces.
TENANT_INNER_PREFIXES = (
    "authentication/",
    "portal/",
    "siteconfig/",
    "school/",
    "studio/",
    "marketplace/",
    "kb/",
    "reports/",
    "automation/",
    "academics/",
    "events/",
    "demo/",
    "settings/",
    "configuration/",
    "evals/",
    "domain-events/",
    "api-center/",
)


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


def _admin_changelist_only(inner: str) -> bool:
    if not inner.startswith("/admin/"):
        return False
    if any(inner.endswith(s) for s in ADMIN_NON_CHANGELIST_SUFFIXES):
        return False
    parts = [p for p in inner.strip("/").split("/") if p]
    return len(parts) == 3 and parts[0] == "admin"


def _include_inner(path: str, _name: str | None) -> bool:
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
    if path == "/":
        return True
    stripped = path.lstrip("/")
    return any(stripped.startswith(p) for p in TENANT_INNER_PREFIXES)


def _full_tenant_path(slug: str, inner: str) -> str:
    inner = inner.strip("/")
    if not inner:
        return f"/t/{slug}/"
    return f"/t/{slug}/{inner}/"


PRIORITY_INNER_PREFIXES = (
    "school/studio/",
    "authentication/",
    "portal/",
    "siteconfig/",
    "school/",
)

# Always include School Studio routes even when --max caps the list.
MANDATORY_SCHOOL_STUDIO_INNER = (
    "/school/studio/",
    "/school/studio/setup/",
    "/school/studio/readiness/",
    "/school/studio/migration/",
    "/school/studio/help/",
    "/school/studio/launch/",
    "/school/studio/provisioning/",
    "/school/studio/fast-path/",
    "/school/studio/lifecycle/",
    "/school/studio/offboarding/",
    "/siteconfig/onboarding/",
)


def _priority(inner: str) -> int:
    stripped = inner.lstrip("/")
    for i, pref in enumerate(PRIORITY_INNER_PREFIXES):
        if stripped.startswith(pref) or stripped == pref.rstrip("/"):
            return i
    return len(PRIORITY_INNER_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--max",
        type=int,
        default=int(os.environ.get("TENANT_SWEEP_MAX", "200")),
        help="Cap routes after sort (default TENANT_SWEEP_MAX or 200).",
    )
    args = parser.parse_args()

    slug = os.environ.get("TENANT_SWEEP_SLUG", "demo-school").strip().strip("/")
    if not slug or not re.match(r"^[a-z0-9][a-z0-9-]*$", slug, re.I):
        print("Invalid TENANT_SWEEP_SLUG", file=sys.stderr)
        return 1

    import django

    django.setup()
    from django.urls import get_resolver

    resolver = get_resolver("config.tenant_urls")
    rows = []
    seen: set[str] = set()
    for raw, name in _list_routes(resolver.url_patterns):
        inner = _normalize(raw)
        if not _include_inner(inner, name):
            continue
        full = _full_tenant_path(slug, inner)
        if full in seen:
            continue
        seen.add(full)
        rows.append(
            {
                "path": full,
                "inner": inner,
                "name": name or "",
                "slug": slug,
                "sweep": True,
            }
        )

    rows.sort(key=lambda r: (_priority(r["inner"]), r["path"]))
    if args.max > 0 and len(rows) > args.max:
        mandatory = [r for r in rows if r["inner"] in MANDATORY_SCHOOL_STUDIO_INNER]
        rest = [r for r in rows if r["inner"] not in MANDATORY_SCHOOL_STUDIO_INNER]
        cap = max(args.max - len(mandatory), 0)
        rows = mandatory + rest[:cap]

    payload = {
        "version": "2026-05-18",
        "slug": slug,
        "count": len(rows),
        "routes": rows,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(rows)} tenant paths to {OUT}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
