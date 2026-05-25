#!/usr/bin/env python3
"""
Django-client smoke: platform admin changelists from sweep routes render
steering strip + scroll host (P3 fallback when Playwright server unavailable).

ADMIN_RENDER_FULL=1 crawls every admin_changelist in control_plane_sweep_routes.json.
Use --write to emit docs/generated/admin_changelist_render_audit.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

ROUTES_JSON = ROOT / "docs/generated/control_plane_sweep_routes.json"
AUDIT_JSON = ROOT / "docs/generated/admin_changelist_render_audit.json"

# Changelists that intentionally leave /admin/ (studio/product redirects).
ADMIN_REDIRECT_ESCAPE_PREFIXES: tuple[str, ...] = (
    "/admin/brand_experience/themepack/",
)


def _is_full_crawl() -> bool:
    return (os.environ.get("ADMIN_RENDER_FULL", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _max_routes() -> int:
    if _is_full_crawl():
        return 0
    return int(os.environ.get("ADMIN_RENDER_SAMPLE_MAX", "24"))


HOST = os.environ.get("VERIFY_ADMIN_RENDER_HOST", "manager.runmycampus.com")


def _final_path(response, fallback: str) -> str:
    req = getattr(response, "request", None)
    if isinstance(req, dict):
        return req.get("PATH_INFO") or fallback
    return getattr(req, "path", None) or fallback


def _is_redirect_escape(path: str, final_path: str, redirect_chain: list) -> bool:
    if any(path.startswith(prefix) for prefix in ADMIN_REDIRECT_ESCAPE_PREFIXES):
        return True
    if redirect_chain and not str(final_path).startswith("/admin/"):
        return True
    return False


def _check_shell(html: str) -> list[str]:
    issues: list[str] = []
    if "data-rmc-admin-steering-strip" not in html:
        issues.append("missing_steering_strip_markup")
    if "data-rmc-operator-surface-strip" in html:
        issues.append("surface_strip_on_changelist")
    if "data-rmc-admin-changelist-live" not in html and "cp-changelist-live" not in html:
        issues.append("missing_changelist_live_marker")
    if 'data-rmc-admin-table-contract="native-table-scroll"' not in html:
        issues.append("missing_native_table_scroll_contract")
    if "rmc-admin-changelist-pagehead" not in html:
        issues.append("missing_changelist_pagehead")
    if "cp-main-content" not in html and "admin-manager-shell" not in html:
        issues.append("missing_shell_markers")
    if "data-rmc-copilot-rail" not in html:
        issues.append("missing_copilot_rail")
    if "data-rmc-page-help" not in html and 'data-rmc-page-help="1"' not in html:
        issues.append("missing_page_help_hook")
    if "TemplateSyntaxError" in html or "Server Error (500)" in html:
        issues.append("template_or_server_error")
    return issues


def _check_static_table_css() -> list[str]:
    css_path = ROOT / "static/css/rmc-admin-changelist-live.css"
    if not css_path.is_file():
        return ["missing_rmc_admin_changelist_live_css"]
    css = css_path.read_text(encoding="utf-8")
    issues: list[str] = []
    required_tokens = (
        "overflow-x: auto",
        "display: table !important",
        "display: table-header-group !important",
        "display: table-row-group !important",
        "display: table-row !important",
        "display: table-cell !important",
        "white-space: nowrap",
        "text-overflow: ellipsis",
    )
    for token in required_tokens:
        if token not in css:
            issues.append(f"missing_css_token:{token}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write docs/generated/admin_changelist_render_audit.json",
    )
    args = parser.parse_args()

    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import Client

    if not ROUTES_JSON.is_file():
        print(f"FAIL: missing {ROUTES_JSON}", file=sys.stderr)
        return 1

    css_issues = _check_static_table_css()
    if css_issues:
        for issue in css_issues:
            print(f"FAIL: {issue}", file=sys.stderr)
        return 1

    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    paths = [
        r["path"]
        for r in data.get("routes", [])
        if r.get("tier") == "admin_changelist" and r.get("sweep")
    ]
    max_routes = _max_routes()
    if max_routes > 0:
        paths = paths[:max_routes]
    if not paths:
        print("FAIL: no admin_changelist routes in sweep JSON", file=sys.stderr)
        return 1

    User = get_user_model()
    user = User.objects.filter(is_superuser=True, is_staff=True).first()
    if not user:
        print("FAIL: no superuser for admin render smoke", file=sys.stderr)
        return 1

    client = Client(HTTP_HOST=HOST)
    client.force_login(user)
    from scripts._manager_render_smoke import prepare_manager_smoke_client

    prepare_manager_smoke_client(client)

    rows: list[dict] = []
    failures: list[str] = []

    for path in paths:
        row: dict = {"path": path, "status": "ok"}
        try:
            response = client.get(path, follow=True)
        except Exception as exc:
            row["status"] = "error"
            row["detail"] = str(exc)
            failures.append(f"{path}: request error {exc}")
            rows.append(row)
            continue

        row["http_status"] = response.status_code
        final_path = _final_path(response, path)
        row["final_path"] = final_path
        if response.redirect_chain:
            row["redirect_chain"] = [
                {"path": p, "status": s} for p, s in response.redirect_chain
            ]

        if response.status_code >= 400:
            row["status"] = "http_error"
            failures.append(f"{path}: HTTP {response.status_code}")
            rows.append(row)
            continue

        if _is_redirect_escape(path, final_path, response.redirect_chain):
            row["status"] = "redirect_escape"
            row["detail"] = "intentional product redirect outside /admin/"
            rows.append(row)
            continue

        html = response.content.decode("utf-8", errors="replace")
        issues = _check_shell(html)
        if issues:
            row["status"] = "shell_fail"
            row["issues"] = issues
            failures.append(f"{path}: {', '.join(issues)}")
        rows.append(row)

    ok_count = sum(1 for r in rows if r["status"] == "ok")
    escape_count = sum(1 for r in rows if r["status"] == "redirect_escape")
    fail_count = len(failures)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": HOST,
        "full_crawl": _is_full_crawl(),
        "route_count": len(paths),
        "ok_count": ok_count,
        "redirect_escape_count": escape_count,
        "failure_count": fail_count,
        "pass": fail_count == 0,
        "rows": rows,
        "failures": failures[:50],
    }

    if args.write or _is_full_crawl():
        AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
        AUDIT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote audit to {AUDIT_JSON}")

    if failures:
        for msg in failures[:20]:
            print(f"FAIL: {msg}", file=sys.stderr)
        if len(failures) > 20:
            print(f"... and {len(failures) - 20} more", file=sys.stderr)
        print(
            f"verify_admin_changelist_render_contract: FAIL "
            f"({ok_count} ok, {escape_count} redirect_escape, {fail_count} failed / {len(paths)} routes)",
            file=sys.stderr,
        )
        return 1

    print(
        f"verify_admin_changelist_render_contract: OK "
        f"({ok_count} ok, {escape_count} redirect_escape / {len(paths)} admin changelists)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
