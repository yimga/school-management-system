#!/usr/bin/env python3
"""
Verify production web runtime markers (Render / manager host).

Usage:
  python scripts/verify_render_runtime_posture.py
  python scripts/verify_render_runtime_posture.py --base-url https://manager.runmycampus.com
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _fetch_json(url: str, timeout: float) -> tuple[int, dict | None, str]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body) if body else None, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = None
        return exc.code, payload, body
    except urllib.error.URLError as exc:
        return 0, None, str(exc.reason)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="https://manager.runmycampus.com",
        help="Manager host base URL (no trailing slash)",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    health_url = f"{base}/health/"

    status, payload, raw = _fetch_json(health_url, args.timeout)
    failures: list[str] = []

    if status != 200:
        failures.append(f"GET /health/ returned HTTP {status} (expected 200)")
    if not isinstance(payload, dict):
        failures.append(f"/health/ body is not JSON object (len={len(raw)})")
    else:
        if payload.get("status") != "healthy":
            failures.append(f"status={payload.get('status')!r} (expected 'healthy')")
        guard = payload.get("auth_api_guard")
        if guard != "unauthenticated-api-guard-v1":
            failures.append(
                f"auth_api_guard={guard!r} (expected 'unauthenticated-api-guard-v1')"
            )
        timeout = str(payload.get("gunicorn_timeout") or "").strip()
        if timeout and timeout != "120":
            failures.append(f"gunicorn_timeout={timeout!r} (expected '120')")
        elif not timeout:
            failures.append(
                "gunicorn_timeout missing — bare gunicorn or old deploy (set GUNICORN_TIMEOUT)"
            )
        web_start = str(payload.get("web_start") or "").strip()
        if not web_start:
            failures.append(
                "web_start missing — Render dashboard may override render_start_web.sh"
            )

    stream_url = f"{base}/platform-runtime/workflow-progress/stream/"
    stream_status, _, stream_raw = _fetch_json(stream_url, args.timeout)
    if stream_status != 401:
        failures.append(
            f"anonymous GET stream returned HTTP {stream_status} (expected 401, not 302 HTML)"
        )
    elif stream_raw and "<html" in stream_raw.lower()[:800]:
        failures.append("anonymous stream body looks like HTML login page")

    if failures:
        print("RENDER_RUNTIME_POSTURE_FAIL")
        for item in failures:
            print(f"  - {item}")
        if payload:
            print("health_json:", json.dumps(payload, sort_keys=True))
        return 1

    print("RENDER_RUNTIME_POSTURE_PASS")
    print("health_json:", json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
