#!/usr/bin/env bash
# Lane 2 local smoke — repo-contained subset (real iOS/Android pilot remains external).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "lane2-local-smoke: offline outbox encryption (vitest)"
npm run test -- tests/offline-outbox-encryption.test.ts --run

echo "lane2-local-smoke: global footprint + glocal offline integration"
python scripts/verify_global_footprint_glocal_offline_integration.py

echo "lane2-local-smoke: offline queue encryption at rest"
python scripts/verify_offline_queue_encryption_at_rest.py

echo "LANE2_LOCAL_SMOKE_PASS"
echo "note: batches 1172/1173 real-device PWA install + offline replay remain external pilot work"
