#!/usr/bin/env python3
"""Batch 1532 — offline event envelope kernel gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    findings: list[str] = []

    mod = ROOT / "apps/sync_engine/event_envelope.py"
    if not mod.is_file():
        findings.append("missing event_envelope.py")
    else:
        text = mod.read_text(encoding="utf-8")
        if "MAX_ENVELOPE_BYTES = 1024" not in text:
            findings.append("MAX_ENVELOPE_BYTES not 1024")

    manifest = (ROOT / "apps/accounts/permission_manifest.py").read_text(encoding="utf-8")
    if "REJECTED" not in manifest or "crdt_edge_iam_admin" not in manifest:
        findings.append("permission manifest missing CRDT rejection")

    try:
        from apps.sync_engine.event_envelope import build_envelope

        build_envelope(
            entity="attendance_record",
            entity_id="99",
            attribute_key="status",
            attribute_value="present",
        )
    except Exception as exc:
        findings.append(f"build_envelope failed: {exc}")

    client = ROOT / "static/js/offline-queue-client.js"
    if client.is_file():
        js = client.read_text(encoding="utf-8")
        if "buildOfflineEnvelope" not in js:
            findings.append("offline-queue-client missing buildOfflineEnvelope")

    if findings:
        print("verify_offline_event_envelope: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_offline_event_envelope: OFFLINE_EVENT_ENVELOPE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
