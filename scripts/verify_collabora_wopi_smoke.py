#!/usr/bin/env python3
"""Staging smoke for Collabora/WOPI integration."""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urljoin

import requests


def _check(url: str, allowed: tuple[int, ...], label: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        r = requests.get(url, timeout=20, allow_redirects=False, headers=headers or {})
    except requests.RequestException as exc:
        return False, f"{label}: request failed ({exc})"
    if r.status_code not in allowed:
        return False, f"{label}: expected {allowed}, got {r.status_code}"
    return True, f"{label}: {r.status_code}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-base", default=os.getenv("APP_BASE_URL", ""))
    ap.add_argument("--collabora-base", default=os.getenv("COLLABORA_BASE_URL", ""))
    ap.add_argument("--office-doc-id", default=os.getenv("WOPI_OFFICE_DOC_ID", ""))
    ap.add_argument("--session-cookie", default=os.getenv("APP_SESSION_COOKIE", ""))
    args = ap.parse_args()

    if not args.app_base:
        print("missing --app-base (or APP_BASE_URL)")
        return 2
    if not args.collabora_base:
        print("missing --collabora-base (or COLLABORA_BASE_URL)")
        return 2

    headers = {}
    if args.session_cookie:
        headers["Cookie"] = args.session_cookie

    checks: list[tuple[bool, str]] = []
    checks.append(_check(urljoin(args.collabora_base.rstrip('/') + '/', 'hosting/discovery'), (200,), 'collabora discovery'))
    checks.append(_check(urljoin(args.app_base.rstrip('/') + '/', 'kb/office/'), (200, 302, 403), 'app office list', headers=headers))

    if args.office_doc_id:
        checks.append(_check(urljoin(args.app_base.rstrip('/') + '/', f'kb/wopi/files/{args.office_doc_id}'), (200, 302, 403), 'wopi check-file-info', headers=headers))
        checks.append(_check(urljoin(args.app_base.rstrip('/') + '/', f'kb/wopi/files/{args.office_doc_id}/contents'), (200, 302, 403), 'wopi contents get', headers=headers))

    ok = True
    for passed, message in checks:
        print(message)
        ok = ok and passed

    if not ok:
        print('COLLABORA/WOPI smoke: FAIL')
        return 1

    print('COLLABORA/WOPI smoke: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
