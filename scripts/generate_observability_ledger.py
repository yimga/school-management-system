#!/usr/bin/env python3
"""
Generate observability ledger for founder/control-plane surfaces.

The ledger is resilient: missing generated inputs degrade to explicit "missing" flags.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "docs" / "generated"
OUT_JSON = GEN / "observability_ledger.json"
OUT_MD = GEN / "observability_ledger.md"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _collect_runtime_counts() -> dict[str, int]:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django

        django.setup()
        from apps.observability.models import PlatformIncident
        from apps.platform_runtime.models import AIActionAuditLog, PlatformEventLog

        return {
            "platform_events_recent_24h": PlatformEventLog.objects.count(),
            "ai_audits_recent_24h": AIActionAuditLog.objects.count(),
            "platform_incidents_open": PlatformIncident.objects.filter(
                status__in=[
                    PlatformIncident.Status.OPEN,
                    PlatformIncident.Status.ACKNOWLEDGED,
                ]
            ).count(),
        }
    except Exception:
        return {
            "platform_events_recent_24h": -1,
            "ai_audits_recent_24h": -1,
            "platform_incidents_open": -1,
        }


def main() -> int:
    GEN.mkdir(parents=True, exist_ok=True)
    ns = _read_json(GEN / "northstar_audit.json")
    kill = _read_json(GEN / "kill_test_report.json")
    heal = _read_json(GEN / "northstar_self_heal_report.json")
    runtime = _collect_runtime_counts()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "northstar": {
            "score": ns.get("total_score"),
            "rating": ns.get("rating"),
            "present": bool(ns),
        },
        "kill_test": {
            "result": kill.get("result", "not run"),
            "critical_count": kill.get("critical_count"),
            "present": bool(kill),
        },
        "self_heal": {
            "status": heal.get("status", "not run"),
            "ticket_count": len(heal.get("unsafe_ticket_paths") or []),
            "present": bool(heal),
        },
        "runtime": runtime,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Observability ledger",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- northstar: {payload['northstar']['score']} ({payload['northstar']['rating']})",
        f"- kill_test: {payload['kill_test']['result']}",
        f"- self_heal: {payload['self_heal']['status']}",
        f"- platform_events_recent_24h: {runtime['platform_events_recent_24h']}",
        f"- ai_audits_recent_24h: {runtime['ai_audits_recent_24h']}",
        f"- platform_incidents_open: {runtime['platform_incidents_open']}",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"generate_observability_ledger: wrote {OUT_JSON} and {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

