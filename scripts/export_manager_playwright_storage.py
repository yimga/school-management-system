#!/usr/bin/env python3
"""Write Playwright storage state for manager host using Django test client login."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Playwright storage must use DB sessions — cache backends are per-process and
# invisible to runserver when REDIS_URL is cleared for E2E.
os.environ["REDIS_URL"] = ""
os.environ["RMC_FORCE_DB_SESSIONS"] = "1"
def _usable_sqlite_db(path: Path) -> bool:
    """Skip empty placeholder files (0-byte db_working.sqlite3 breaks E2E export)."""
    try:
        return path.is_file() and path.stat().st_size > 4096
    except OSError:
        return False


_root = Path(__file__).resolve().parent.parent
if not (os.environ.get("DB_FILE") or "").strip():
    for _db_name in ("db_working.sqlite3", "db.sqlite3"):
        _db_path = _root / _db_name
        if _usable_sqlite_db(_db_path):
            os.environ["DB_FILE"] = str(_db_path)
            break
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

AUTH_PATH = ROOT / "artifacts" / "manager-playwright-auth.json"
MANAGER_HOST = os.environ.get("VISUAL_QA_MANAGER_HOST", "manager.runmycampus.com")
USERNAME = os.environ.get("VISUAL_QA_USERNAME", "visualqa_admin")
PASSWORD = os.environ.get("VISUAL_QA_PASSWORD", "VisualQaPass123!")


def main() -> int:
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client

    from apps.schools.tests.manager_client import bind_manager_session, mark_manager_mfa_verified

    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username=USERNAME,
        defaults={
            "email": f"{USERNAME}@example.com",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "role": "SUPERADMIN",
        },
    )
    user.is_staff = True
    user.is_superuser = True
    user.role = getattr(user, "role", None) or "SUPERADMIN"
    user.set_password(PASSWORD)
    user.save()

    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.filter(user=user).delete()
        device, _ = TOTPDevice.objects.update_or_create(
            user=user,
            name=os.environ.get("VISUAL_QA_TOTP_DEVICE", "e2e-playwright"),
            defaults={"confirmed": True},
        )
        device.key = os.environ.get(
            "VISUAL_QA_TOTP_HEX_KEY",
            "eab95095c004f245721ba0fa7ebf82d5dc73",
        )
        device.save()
    except Exception as exc:
        print(f"FAIL: could not seed E2E TOTP device: {exc}", file=sys.stderr)
        return 1

    # Match Playwright Chromium default UA so SessionPinningMiddleware does not flush
    # exported cookies on the first real HTTP request (test client UA is empty).
    playwright_ua = os.environ.get(
        "VISUAL_QA_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    client = Client(HTTP_HOST=MANAGER_HOST, HTTP_USER_AGENT=playwright_ua)
    client.get("/authentication/login/")
    client.force_login(user)
    bind_manager_session(client)
    mark_manager_mfa_verified(client)
    probe = client.get("/super/schools/", follow=False)
    if probe.status_code == 302:
        location = probe.headers.get("Location") or ""
        if any(
            fragment in location
            for fragment in (
                "/authentication/login",
                "/mfa/setup",
                "/mfa/verify",
            )
        ):
            print(
                "FAIL: manager session not ready for /super/schools/ "
                f"(HTTP 302 → {location})",
                file=sys.stderr,
            )
            return 1
    if probe.status_code != 200:
        print(
            f"FAIL: manager schools probe returned {probe.status_code}",
            file=sys.stderr,
        )
        return 1

    port = os.environ.get("VISUAL_QA_PORT", "8000")
    base_url = os.environ.get("MANAGER_BASE_URL", f"http://{MANAGER_HOST}:{port}")

    cookies_out = []
    seen: set[str] = set()
    for name, morsel in client.cookies.items():
        if not str(morsel.value or "").strip():
            continue
        if name in seen:
            continue
        seen.add(name)
        cookies_out.append(
            {
                "name": name,
                "value": morsel.value,
                "domain": MANAGER_HOST,
                "path": "/",
                "expires": -1,
                "httpOnly": name.endswith("sessionid") or name.endswith("csrftoken"),
                "secure": False,
                "sameSite": "Lax",
            }
        )
    session_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    if not any(c["name"] == session_name for c in cookies_out):
        print(f"FAIL: missing manager session cookie {session_name}", file=sys.stderr)
        return 1

    from django.contrib.sessions.backends.db import SessionStore

    session_key = next(c["value"] for c in cookies_out if c["name"] == session_name)
    store = SessionStore(session_key=session_key)
    store.load()
    if not store.get("_auth_user_id"):
        print("FAIL: exported session is not authenticated", file=sys.stderr)
        return 1
    if not store.get("mfa_verified"):
        print("FAIL: exported session missing mfa_verified", file=sys.stderr)
        return 1

    if os.environ.get("MANAGER_PLAYWRIGHT_HTTP_PROBE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        import urllib.error
        import urllib.request
        from urllib.parse import urlparse

        cookie_header = "; ".join(
            f"{item['name']}={item['value']}" for item in cookies_out
        )
        parsed = urlparse(base_url)
        loopback_port = parsed.port or int(os.environ.get("VISUAL_QA_PORT", "8000"))
        probe_url = f"http://127.0.0.1:{loopback_port}/super/schools/"
        http_req = urllib.request.Request(
            probe_url,
            headers={
                "Host": MANAGER_HOST,
                "Cookie": cookie_header,
                "User-Agent": playwright_ua,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(http_req, timeout=30) as http_resp:
                final_url = http_resp.geturl()
                body = http_resp.read(1024).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            final_url = exc.geturl()
            body = exc.read(256).decode("utf-8", errors="replace")
            print(
                "FAIL: live manager HTTP probe failed "
                f"(HTTP {exc.code} → {final_url})",
                file=sys.stderr,
            )
            return 1
        if "data-rmc-list-bulk" not in body and "login" in final_url.lower():
            print(
                "FAIL: live manager HTTP probe not authenticated "
                f"(url={final_url})",
                file=sys.stderr,
            )
            return 1

    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cookies": cookies_out, "origins": []}
    AUTH_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {AUTH_PATH} ({len(cookies_out)} cookies) for {base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
