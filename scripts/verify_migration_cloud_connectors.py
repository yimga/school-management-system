#!/usr/bin/env python3
"""Gate: Migration Cloud connector layer is present and certified honestly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks = []
    checks.append(("models_connectors", (ROOT / "apps/migration_cloud/models_connectors.py").is_file()))
    checks.append(("connector_bridge", (ROOT / "apps/migration_cloud/services/connector_bundle_bridge.py").is_file()))
    checks.append(("api_pull_intake", (ROOT / "apps/migration_cloud/intake/api_pull_intake.py").is_file()))
    checks.append(("database_intake_sqlite", "sqlite_master" in (ROOT / "apps/migration_cloud/intake/database_intake.py").read_text(encoding="utf-8")))
    checks.append(("vendor_export", (ROOT / "apps/migration_cloud/connectors/vendor_export.py").is_file()))
    checks.append(("e2e_spec", (ROOT / "tests/e2e/migration-cloud.spec.js").is_file()))
    discovery = ROOT / "docs/generated/migration_cloud_connector_discovery.json"
    checks.append(("discovery_json", discovery.is_file()))
    if discovery.is_file():
        payload = json.loads(discovery.read_text(encoding="utf-8"))
        checks.append(("discovery_has_bridge", "connector_bundle_bridge" in str(payload.get("new_connector_layer", {}))))

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("MIGRATION_CLOUD_CONNECTORS_FAIL", failed)
        return 1
    print("MIGRATION_CLOUD_CONNECTORS_PASS", len(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
