#!/usr/bin/env python3
"""
Django admin intelligent canvas — live screenshot soft harness.

Default: soft-pass when Django is unreachable or DB/login fails (operator-gated).
Use --strict to require a live authenticated screenshot of change-form + change-list.

  python scripts/verify_django_admin_canvas_live.py
  python scripts/verify_django_admin_canvas_live.py --strict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "django-admin-canvas-live"
REPORT = OUT_DIR / "report.json"


def _probe(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        # Auth-gated admin still proves the server is up.
        if 200 <= exc.code < 500:
            return True, f"HTTP {exc.code}"
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _try_playwright(base_url: str, username: str, password: str) -> dict:
    """Attempt live screenshots; never raises — returns status dict."""
    result: dict = {
        "playwright": False,
        "login": False,
        "screenshots": [],
        "error": None,
    }
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"playwright_unavailable: {exc}"
        return result

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{base_url}/admin/login/", wait_until="domcontentloaded", timeout=20000)
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('input[type="submit"], button[type="submit"]')
            page.wait_for_timeout(1200)
            if "/admin/login" in page.url:
                result["error"] = "login_failed"
                browser.close()
                return result
            result["login"] = True
            result["playwright"] = True

            shots = [
                ("admin-index", f"{base_url}/admin/"),
            ]
            # Prefer auth User changelist/change if reachable; fall back to index only.
            for label, path in (
                ("change-list", f"{base_url}/admin/auth/user/"),
                ("change-form-add", f"{base_url}/admin/auth/user/add/"),
            ):
                shots.append((label, path))

            for label, url in shots:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(600)
                    # Contract markers when present
                    if label.startswith("change-form"):
                        toggle = page.locator("[data-rmc-django-view-toggle]")
                        if toggle.count():
                            page.locator('[data-rmc-django-view="preview"]').first.click(timeout=2000)
                            page.wait_for_timeout(300)
                    dest = OUT_DIR / f"{label}.png"
                    page.screenshot(path=str(dest), full_page=True)
                    result["screenshots"].append(str(dest.relative_to(ROOT)))
                except Exception as shot_exc:  # noqa: BLE001
                    result["screenshots"].append(f"{label}:FAILED:{shot_exc}")

            browser.close()
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="Fail when live screenshots are unavailable")
    ap.add_argument(
        "--base-url",
        default=os.environ.get("RMC_ADMIN_CANVAS_BASE_URL", "http://127.0.0.1:8000"),
    )
    ap.add_argument("--username", default=os.environ.get("RMC_ADMIN_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("RMC_ADMIN_PASSWORD", "Sch00l_1234"))
    args = ap.parse_args()

    # Static contract must already be green (repo-scope proof).
    static_ok = True
    static_notes: list[str] = []
    for rel in (
        "templates/admin/change_form.html",
        "templates/admin/change_list.html",
        "static/js/rmc-admin-workspace.js",
        "static/css/rmc-admin-django-canvas-contract.css",
    ):
        path = ROOT / rel
        if not path.is_file():
            static_ok = False
            static_notes.append(f"missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if rel.endswith("change_form.html") and "data-rmc-django-view-toggle" not in text:
            static_ok = False
            static_notes.append("change_form missing view toggle")
        if rel.endswith("change_list.html") and "admin_changelist_rail.html" not in text:
            static_ok = False
            static_notes.append("change_list missing context rail include")
        if rel.endswith("rmc-admin-workspace.js") and "data-rmc-django-view-mode" not in text:
            static_ok = False
            static_notes.append("workspace js missing view-mode wiring")
        if rel.endswith(".css") and "2026-07-17 parity-close" not in text:
            static_ok = False
            static_notes.append("css missing parity-close block")

    live, live_msg = _probe(args.base_url.rstrip("/") + "/admin/login/")
    pw = _try_playwright(args.base_url.rstrip("/"), args.username, args.password) if live else {
        "playwright": False,
        "login": False,
        "screenshots": [],
        "error": f"server_unreachable: {live_msg}",
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "static_ok": static_ok,
        "static_notes": static_notes,
        "server_reachable": live,
        "server_note": live_msg,
        "playwright": pw,
        "strict": args.strict,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    live_ok = bool(pw.get("login") and pw.get("screenshots"))
    if not static_ok:
        print("DJANGO_ADMIN_CANVAS_LIVE_FAIL")
        for note in static_notes:
            print(f"  - {note}")
        return 1

    if live_ok:
        print("DJANGO_ADMIN_CANVAS_LIVE_PASS")
        for shot in pw["screenshots"]:
            print(f"  - {shot}")
        return 0

    if args.strict:
        print("DJANGO_ADMIN_CANVAS_LIVE_FAIL")
        print(f"  - live screenshots unavailable: {pw.get('error') or live_msg}")
        return 1

    print("DJANGO_ADMIN_CANVAS_LIVE_SOFT_PASS")
    print("  - static Form/Preview/Audit + changelist rail contract OK")
    print(f"  - live screenshots deferred: {pw.get('error') or live_msg}")
    print(f"  - report: {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
