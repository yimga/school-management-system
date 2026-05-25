#!/usr/bin/env python3
"""Integration audit for batch 1507 ReBAC + offline IAM snapshot."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "rebac_integration_audit.json"


def main() -> int:
    rows: list[dict] = []

    def add(cid: str, ok: bool, detail: str, severity: str = "blocker") -> None:
        rows.append(
            {"check_id": cid, "ok": ok, "detail": detail, "severity": severity},
        )

    urls = (ROOT / "apps/api/urls.py").read_text(encoding="utf-8")
    add("api-snapshot-url", "offline/permission_snapshot/" in urls, "permission_snapshot route")
    add("api-intent-url", "offline/iam_intent/" in urls, "iam_intent route")
    add(
        "apps-rebac-signals",
        "rebac_signals" in (ROOT / "apps/accounts/apps.py").read_text(encoding="utf-8"),
        "apps.py ready()",
    )
    add(
        "models-imported",
        "RelationshipTuple" in (ROOT / "apps/accounts/models.py").read_text(encoding="utf-8"),
        "models.py re-export",
    )
    settings = (ROOT / "config/settings.py").read_text(encoding="utf-8")
    add("settings-rmc-rebac", "RMC_REBAC_ENABLED" in settings, "RMC_REBAC_* env")
    pdp = (ROOT / "apps/policies/pdp.py").read_text(encoding="utf-8")
    add("pdp-inject-rebac", "_inject_rebac_context" in pdp, "PDP context")
    manifest = (ROOT / "apps/accounts/permission_manifest.py").read_text(encoding="utf-8")
    add(
        "manifest-postgres-rebac",
        '"postgres_rebac"' in manifest and "IMPLEMENTED" in manifest,
        "manifest status",
    )
    static_js = list((ROOT / "static/js").glob("*.js"))
    add(
        "client-js-snapshot-cache",
        (ROOT / "static/js/rmc-iam-snapshot-cache.js").is_file()
        and "RMCIamSnapshot" in (ROOT / "static/js/rmc-iam-snapshot-cache.js").read_text(
            encoding="utf-8",
        ),
        "rmc-iam-snapshot-cache.js",
    )
    finance_api = (ROOT / "apps/finance/api_views.py").read_text(encoding="utf-8")
    add(
        "finance-rebac-permission",
        "RebacPermission" in finance_api,
        "finance ViewSets",
    )
    mobile_api = (ROOT / "apps/api/mobile_api.py").read_text(encoding="utf-8")
    add(
        "grades-rebac-enforce",
        "rebac_permission_denied:grade.submit" in mobile_api,
        "mobile sync_batch grades",
    )
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    add(
        "portal-wires-snapshot-js",
        "rmc-iam-snapshot-cache.js" in portal and "permissionSnapshotUrl" in portal,
        "portal_base",
    )
    add(
        "offline-action-iam-type",
        "iam.request_access" in (ROOT / "apps/platform_runtime/offline_action_types.py").read_text(),
        "SODP registry",
    )
    migration = ROOT / "apps/accounts/migrations/0039_rebac_tuples_offline_iam.py"
    add("migration-0039", migration.is_file(), str(migration))

    blockers = [r for r in rows if not r["ok"] and r["severity"] == "blocker"]
    gaps = [r for r in rows if not r["ok"] and r["severity"] == "gap"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blocker_count": len(blockers),
        "gap_count": len(gaps),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if blockers:
        print("REBAC_INTEGRATION_AUDIT_FAIL")
        for r in blockers:
            print(f"  {r['check_id']}: {r['detail']}")
        return 1
    print("REBAC_INTEGRATION_AUDIT_PASS")
    if gaps:
        print(f"  gaps={len(gaps)} (documented, non-blocking)")
        for r in gaps:
            print(f"    - {r['check_id']}: {r['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
