#!/usr/bin/env python3
"""Control-plane nav: every item resolves to a named route (no lazy # / void hrefs).

Writes docs/generated/route_click_targets.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "route_click_targets.json"

LAZY_HREF = re.compile(
    r'<a[^>]+class="[^"]*nav-link[^"]*"[^>]+href="(#|javascript:void\(0\))"',
    re.I,
)
SIDEBAR_TEMPLATES = (
    "templates/partials/control_plane_sidebar.html",
    "templates/partials/control_plane_sidebar_studio_focus.html",
    "templates/partials/portal_sidebar.html",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))
    import django

    django.setup()
    from django.test import RequestFactory
    from django.urls import resolve

    from apps.schools.control_plane_nav import build_control_plane_nav

    from django.contrib.auth.models import AnonymousUser

    factory = RequestFactory()
    request = factory.get("/super/", HTTP_HOST="manager.runmycampus.com")
    request.user = AnonymousUser()
    request.public_host_kind = "manager"
    request.urlconf = "config.manager_urls"
    request.path = "/super/"

    nav = build_control_plane_nav(request)
    targets: list[dict] = []
    findings: list[str] = []

    for group in nav:
        for item in group.get("items") or []:
            url = (item.get("url") or "").strip()
            url_name = item.get("url_name") or ""
            jid = item.get("id") or ""
            label = item.get("label") or ""
            if not url:
                findings.append(f"missing url for nav id={jid} label={label}")
                continue
            if url in ("#", "javascript:void(0)"):
                findings.append(f"lazy href for id={jid}")
                continue
            named = url_name or ""
            try:
                match = resolve(url)
                named = named or match.view_name or ""
            except Exception:
                pass
            if not named and not url.startswith("/"):
                findings.append(f"unresolved route name for id={jid} url={url}")
            targets.append(
                {
                    "id": jid,
                    "label": str(label)[:80],
                    "url": url,
                    "url_name": named,
                }
            )

    for rel in SIDEBAR_TEMPLATES:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in LAZY_HREF.finditer(text):
            findings.append(f"lazy nav href in {rel}: {m.group(1)}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nav_item_count": len(targets),
        "lazy_fallback_count": len(findings),
        "targets": targets,
        "findings": findings,
        "verdict": "NAV_LEDGER_PASS" if not findings else "NAV_LEDGER_FAIL",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    elif findings:
        print(f"NAV_LEDGER_FAIL ({len(findings)} findings)")
        for f in findings[:20]:
            print(f"  - {f}")
    else:
        print(f"NAV_LEDGER_PASS ({len(targets)} nav targets)")

    if args.strict and findings:
        return 1
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
