#!/usr/bin/env python3
"""Verify R3 periodic background sync for offline outbox drain (batch 1706)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    sw = ROOT / "static/js/service-worker.js"
    if not sw.is_file():
        errors.append("missing service-worker.js")
    else:
        text = sw.read_text(encoding="utf-8")
        for needle in (
            "backgroundPeriodicSyncEnabled",
            "periodicsync",
            "PERIODIC_SYNC_TAG",
            "registerOfflineSyncRetries",
            "replayAllEnabledQueues",
            "notifyClientsSyncComplete",
        ):
            if needle not in text:
                errors.append(f"service-worker.js missing {needle}")

    reconnect = ROOT / "static/js/rmc-reconnect-rehydrate.js"
    if reconnect.is_file():
        rc = reconnect.read_text(encoding="utf-8")
        if "sync-complete" not in rc:
            errors.append("rmc-reconnect-rehydrate.js missing sync-complete hook")

    if errors:
        for err in errors:
            print(f"OFFLINE_PERIODIC_SYNC_R3_FAIL: {err}")
        return 1

    print("OFFLINE_PERIODIC_SYNC_R3_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
