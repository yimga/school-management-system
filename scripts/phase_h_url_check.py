#!/usr/bin/env python3
"""
Phase H — URL check: resolve and optionally hit key URLs (200 vs 4xx/5xx).

Supports PHASE_H_MANUAL_CHECKLIST §2–3: verify links and pages return 200.
Requires Django (manage.py or DJANGO_SETTINGS_MODULE).

Usage:
  python scripts/phase_h_url_check.py                    # resolve only (print paths)
  python scripts/phase_h_url_check.py --hit http://localhost:8000   # resolve + GET each URL
  python scripts/phase_h_url_check.py --hit https://example.com --host manager.example.com  # with Host header
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.urls import reverse, NoReverseMatch

# Phase H critical + marketing + control plane URLs (named or path)
URL_NAMES = [
    "home",
    "health",
    "healthz",
    "accounts:login",
    "accounts:backend_dashboard",
    "portal:parent_dashboard",
    "finance:dashboard",
    "analytics:dashboard",
    "studio_os:shell",
    "studio_os:experience",
    "studio_os:automation",
    "studio_os:output",
    "studio_os:launch",
    "studio_os:control",
    "super:dashboard",
    "siteconfig:console_domains_hub",
    "marketing_landing",
    "marketing_product",
    "marketing_book_demo",
    "global_login_discovery",
]
# Paths that may require specific host (marketing on public host)
PATHS = [
    "/",
    "/product/",
    "/pricing/",
    "/book-demo/",
]


def resolve_all():
    """Resolve all URL names; return list of (name_or_path, url_path, error)."""
    results = []
    for name in URL_NAMES:
        try:
            path = reverse(name)
            results.append((name, path, None))
        except NoReverseMatch as e:
            results.append((name, None, str(e)))
    for path in PATHS:
        results.append((path, path, None))
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Phase H URL check (resolve and optionally hit)"
    )
    parser.add_argument(
        "--hit", metavar="BASE_URL", help="GET each resolved URL and report status"
    )
    parser.add_argument("--host", default="", help="Host header when using --hit")
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Only print failures"
    )
    args = parser.parse_args()

    results = resolve_all()
    failures = []
    for name_or_path, url_path, err in results:
        if err:
            failures.append(f"{name_or_path}: {err}")
            if not args.quiet:
                print(f"  FAIL reverse: {name_or_path} — {err}", file=sys.stderr)
        elif url_path and not args.quiet and not args.hit:
            print(f"  {name_or_path} -> {url_path}")

    if args.hit:
        try:
            import urllib.request
        except ImportError:
            print("urllib.request required for --hit", file=sys.stderr)
            sys.exit(1)
        base = args.hit.rstrip("/")
        headers = {"User-Agent": "PhaseH-URL-Check/1.0"}
        if args.host:
            headers["Host"] = args.host
        for name_or_path, url_path, err in results:
            if err or not url_path:
                continue
            full = (
                base + url_path if url_path.startswith("/") else base + "/" + url_path
            )
            try:
                req = urllib.request.Request(full, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as r:
                    status = r.getcode()
                    if status >= 400:
                        failures.append(f"{name_or_path} {full} -> {status}")
                        print(f"  {status}: {name_or_path} ({full})", file=sys.stderr)
                    elif not args.quiet:
                        print(f"  {status}: {name_or_path}")
            except Exception as e:
                failures.append(f"{name_or_path} {full} -> {e}")
                print(f"  ERROR: {name_or_path} — {e}", file=sys.stderr)

    if failures:
        print(f"Phase H URL check: {len(failures)} failure(s)", file=sys.stderr)
        sys.exit(1)
    print("Phase H URL check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
