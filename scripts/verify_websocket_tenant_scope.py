#!/usr/bin/env python3
"""AWS pillar: WebSocket ASGI stack binds tenant before consumers connect."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    failures: list[str] = []

    asgi = ROOT / "config" / "asgi.py"
    text = asgi.read_text(encoding="utf-8")
    if "TenantChannelsMiddleware" not in text:
        failures.append("config/asgi.py missing TenantChannelsMiddleware")
    if "AuthMiddlewareStack" not in text:
        failures.append("config/asgi.py missing AuthMiddlewareStack")

    mw = ROOT / "apps" / "schools" / "channels_tenant_middleware.py"
    if not mw.is_file():
        failures.append("missing apps/schools/channels_tenant_middleware.py")
    else:
        mw_text = mw.read_text(encoding="utf-8")
        for needle in (
            "bind_websocket_tenant_scope",
            "user_may_access_school_api",
            "tenant_sync_room_name",
        ):
            if needle not in mw_text:
                failures.append(f"channels_tenant_middleware.py missing {needle}")

    consumers = ROOT / "apps" / "api" / "consumers.py"
    ctext = consumers.read_text(encoding="utf-8")
    if "tenant_sync_room_name" not in ctext:
        failures.append("apps/api/consumers.py missing tenant_sync_room_name")
    if 'f"students_sync_{self.user.id}"' in ctext:
        failures.append("legacy user-only WS group name still present")

    wal = ROOT / "apps" / "wal_stream" / "consumers.py"
    wtext = wal.read_text(encoding="utf-8")
    if "school_access_denied" not in wtext:
        failures.append("wal_stream consumer missing school_access_denied check")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(f"verify_websocket_tenant_scope: {len(failures)} FAIL", file=sys.stderr)
        return 1
    print("WEBSOCKET_TENANT_SCOPE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
