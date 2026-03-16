#!/usr/bin/env python3
"""
§7 Marketplace seed targets: refresh docs/generated/marketplace_seed_counts.json from platform_inventory.

Run from repo root: python scripts/refresh_marketplace_seed_targets.py

- Requires Django (manage.py). Writes docs/generated/marketplace_seed_counts.json for MARKETPLACE_SEED_TARGETS.md §2.
- Validates that counts meet MARKETPLACE_SEED_TARGETS minimums (25+ apps, 25+ blueprints, 30+ workflows, 20+ dashboards, 15+ policy).
- Exits with code 1 if minimums are not met (so CI can enforce §7).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_DIR = os.path.join(REPO_ROOT, "docs", "generated")
OUTPUT_JSON = os.path.join(GENERATED_DIR, "marketplace_seed_counts.json")

# Must match apps.platform_runtime.catalog_counts.MARKETPLACE_MINIMUMS and MARKETPLACE_SEED_TARGETS.md §1
MARKETPLACE_MINIMUMS = {
    "first_party_apps": 25,
    "blueprint_packs": 25,
    "workflow_packs": 30,
    "dashboard_packs": 20,
    "policy_bundles": 15,
}


def validate_minimums(data: dict) -> list[str]:
    """Return list of error messages if any count is below minimum."""
    errors = []
    for key, minimum in MARKETPLACE_MINIMUMS.items():
        value = data.get(key, 0)
        if not isinstance(value, (int, float)) or value < minimum:
            errors.append(f"{key}: {data.get(key, 'missing')} (need >= {minimum})")
    return errors


def main() -> int:
    os.chdir(REPO_ROOT)
    if not os.path.isdir(GENERATED_DIR):
        os.makedirs(GENERATED_DIR)
    result = subprocess.run(
        [sys.executable, "manage.py", "platform_inventory", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode
    data = json.loads(result.stdout)
    errors = validate_minimums(data)
    if errors:
        print("Marketplace seed minimums not met (MARKETPLACE_SEED_TARGETS §1):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("Run: python manage.py seed_first_party_apps && python manage.py seed_blueprint_policy_packs && python manage.py seed_workflow_dashboard_packs", file=sys.stderr)
        return 1
    data["_refreshed_at"] = datetime.now(timezone.utc).isoformat()
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {OUTPUT_JSON}")
    print(
        "Catalog counts:",
        data.get("first_party_apps"),
        "apps,",
        data.get("blueprint_packs"),
        "blueprints,",
        data.get("workflow_packs"),
        "workflows,",
        data.get("dashboard_packs"),
        "dashboards,",
        data.get("policy_bundles"),
        "policies.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
