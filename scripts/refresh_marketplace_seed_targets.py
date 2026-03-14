#!/usr/bin/env python3
"""
§7 Marketplace seed targets: refresh docs/generated/marketplace_seed_counts.json from platform_inventory.
Run from repo root: python scripts/refresh_marketplace_seed_targets.py
Requires Django (manage.py); writes docs/generated/marketplace_seed_counts.json for MARKETPLACE_SEED_TARGETS.md §2.
"""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_DIR = os.path.join(REPO_ROOT, "docs", "generated")
OUTPUT_JSON = os.path.join(GENERATED_DIR, "marketplace_seed_counts.json")


def main():
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
        sys.exit(result.returncode)
    data = json.loads(result.stdout)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {OUTPUT_JSON}")
    print("Catalog counts:", data.get("first_party_apps"), "apps,", data.get("blueprint_packs"), "blueprints,",
          data.get("workflow_packs"), "workflows,", data.get("dashboard_packs"), "dashboards,", data.get("policy_bundles"), "policies.")


if __name__ == "__main__":
    main()
