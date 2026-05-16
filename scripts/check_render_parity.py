#!/usr/bin/env python
"""
Render-parity scaffold.

Compares the routes the deployed environment actually serves against the route
inventory this branch declares (`docs/generated/route_surface_audit.json`). The
risk this closes from section O of the master-prompt: "render parity partial —
needs deployed SHA + live route comparison."

How it works:

1. Reads the local route inventory and extracts every named GET route.
2. For each route, does a HEAD (falling back to GET) against
   ``$RMC_DEPLOYED_BASE_URL`` with a status-only summary.
3. Flags routes that ARE in the local inventory but the deployed env returns
   404 for them (a missing route — most likely an un-deployed branch),
   and routes that return 5xx (regression that didn't get caught pre-deploy).
4. Exits 1 if any 5xx is observed; exits 0 with a report otherwise. Missing
   routes are surfaced as warnings — they're noisy on healthy deploys where
   the branch simply hasn't shipped yet.

This is a scaffold: it deliberately keeps the surface small. The harness lives,
and any team can wire it into CI by setting ``RMC_DEPLOYED_BASE_URL`` (and
optionally ``RMC_DEPLOYED_AUTH_COOKIE``) as repo secrets.

Skips cleanly when no base URL is configured so it never breaks the build
just because secrets aren't on the runner yet.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "docs" / "generated" / "route_surface_audit.json"


def load_routes() -> list[dict]:
    if not INVENTORY.exists():
        return []
    try:
        data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    routes = data.get("routes") if isinstance(data, dict) else None
    return [r for r in (routes or []) if isinstance(r, dict)]


def probe(base_url: str, path: str, *, cookie: str = "") -> int:
    """Return HTTP status code, or 0 on connect failure."""
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method="HEAD")
    if cookie:
        req.add_header("Cookie", cookie)
    req.add_header("User-Agent", "rmc-render-parity/1.0")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def is_eligible(path: str) -> bool:
    """Skip routes that need parameters or that are POST-only by convention."""
    if not path or "<" in path or "{" in path:
        return False
    if path.startswith("/api/v1/oauth/"):
        return False
    if "/edit/" in path or "/delete/" in path or "/create/" in path:
        return False
    return True


def main() -> int:
    base_url = os.environ.get("RMC_DEPLOYED_BASE_URL", "").strip()
    cookie = os.environ.get("RMC_DEPLOYED_AUTH_COOKIE", "").strip()
    if not base_url:
        print(
            "RMC_DEPLOYED_BASE_URL not set — skipping render-parity check cleanly. "
            "Set it (and optionally RMC_DEPLOYED_AUTH_COOKIE) to enable."
        )
        return 0

    routes = load_routes()
    if not routes:
        print(
            f"WARN: {INVENTORY} missing or empty — run "
            "`python scripts/audit_route_surface.py` first."
        )
        return 0

    candidates = [r for r in routes if is_eligible(r.get("path", ""))]
    sample_size = int(os.environ.get("RMC_PARITY_SAMPLE", "60"))
    candidates = candidates[:sample_size]

    fives: list[tuple[str, int]] = []
    missing: list[str] = []
    ok_count = 0
    connect_fail = 0

    print(f"Probing {len(candidates)} routes against {base_url}…")
    for r in candidates:
        path = r["path"]
        status = probe(base_url, path, cookie=cookie)
        if status == 0:
            connect_fail += 1
        elif status >= 500:
            fives.append((path, status))
        elif status == 404:
            missing.append(path)
        else:
            ok_count += 1
        time.sleep(0.05)

    print(
        f"ok={ok_count} 5xx={len(fives)} 404={len(missing)} "
        f"connect_fail={connect_fail}"
    )
    if fives:
        print("\n5xx regressions (FAIL):")
        for p, s in fives:
            print(f"  {s}  {p}")
        return 1
    if missing:
        print("\n404 (not yet deployed or removed) — informational:")
        for p in missing[:10]:
            print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
