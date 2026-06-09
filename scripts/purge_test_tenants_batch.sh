#!/usr/bin/env bash
# Purge inactive test tenants on Render (or any prod shell) with policy override.
# Run from Render Dashboard → school-management-system → Shell.
set -euo pipefail

echo "=== Dry-run inventory (no deletes) ==="
python scripts/purge_test_tenants_batch.py

echo ""
echo "=== APPLY permanent purge ==="
python scripts/purge_test_tenants_batch.py --apply
