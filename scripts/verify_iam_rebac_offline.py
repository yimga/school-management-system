#!/usr/bin/env python3
"""Gate: Postgres ReBAC + offline IAM snapshot (batch 1507)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "iam_rebac_offline_audit.json"


def _ok(path: str) -> bool:
    return (ROOT / path).is_file()


def main() -> int:
    rows = []
    checks = [
        ("models-rebac", _ok("apps/accounts/models_rebac.py")),
        ("rebac-check-api", _ok("apps/accounts/rebac.py")),
        ("rebac-sync-writers", _ok("apps/accounts/rebac_sync.py")),
        ("rebac-signals", _ok("apps/accounts/rebac_signals.py")),
        ("iam-snapshot", _ok("apps/accounts/iam_snapshot.py")),
        ("offline-intents", _ok("apps/accounts/rebac_intents.py")),
        ("snapshot-api", _ok("apps/api/iam_offline_api.py")),
        ("migration-0039", _ok("apps/accounts/migrations/0039_rebac_tuples_offline_iam.py")),
        ("mgmt-sync-command", _ok("apps/accounts/management/commands/sync_rebac_tuples.py")),
        ("settings-rebac", "RMC_REBAC_ENABLED" in (ROOT / "config/settings.py").read_text(encoding="utf-8")),
    ]
    urls = (ROOT / "apps/api/urls.py").read_text(encoding="utf-8")
    checks.append(
        ("url-permission-snapshot", "offline/permission_snapshot/" in urls),
    )
    checks.append(("url-iam-intent", "offline/iam_intent/" in urls))
    manifest = (ROOT / "apps/accounts/permission_manifest.py").read_text(encoding="utf-8")
    checks.append(
        ("manifest-rebac-implemented", "postgres_rebac" in manifest and "IMPLEMENTED" in manifest),
    )
    token_api = (ROOT / "apps/api/offline_device_api.py").read_text(encoding="utf-8")
    checks.append(("token-bundles-snapshot", "iam_snapshot" in token_api))
    checks.append(
        (
            "iam-snapshot-js",
            (ROOT / "static/js/rmc-iam-snapshot-cache.js").is_file(),
        ),
    )
    checks.append(
        (
            "finance-rebac-drf",
            "RebacPermission" in (ROOT / "apps/finance/api_views.py").read_text(encoding="utf-8"),
        ),
    )
    checks.append(
        (
            "mobile-grade-rebac",
            "grade.submit" in (ROOT / "apps/api/mobile_api.py").read_text(encoding="utf-8"),
        ),
    )
    pdp = (ROOT / "apps/policies/pdp.py").read_text(encoding="utf-8")
    checks.append(("pdp-rebac-context", "_inject_rebac_context" in pdp))

    for cid, ok in checks:
        rows.append({"check_id": cid, "ok": ok})

    finding = sum(1 for r in rows if not r["ok"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "finding_count": finding,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if finding:
        print("IAM_REBAC_OFFLINE_FAIL")
        for r in rows:
            if not r["ok"]:
                print(f"  {r['check_id']}")
        return 1
    print("IAM_REBAC_OFFLINE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
