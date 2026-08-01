"""Verify the approved tenant operations build/cache/service-worker triplet."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "var/tenant-configuration-operations-build-lock.json"
SURFACES = (
    "templates/platform_runtime/school_configuration_center.html",
    "templates/finance/dashboard.html",
    "templates/academics/hub.html",
    "templates/portal/offline_sync_queue.html",
    "templates/marketplace/tenant_app_catalog.html",
    "templates/compliance/dashboard.html",
)


def main() -> int:
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    build_id = data["build_id"]
    cache_bust_id = data["cache_bust_id"]
    sw_version = data["service_worker_version"]
    failures = []
    for relative in SURFACES:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if f'data-rmc-tenant-ops-build="{build_id}"' not in text:
            failures.append(f"{relative}: build ID missing")
        if cache_bust_id not in text:
            failures.append(f"{relative}: cache-bust ID missing")
    worker = (ROOT / "static/js/service-worker.js").read_text(encoding="utf-8")
    match = re.search(r'const CACHE_VERSION = "([^"]+)";', worker)
    if not match or match.group(1) != sw_version:
        failures.append("static/js/service-worker.js: version does not match build lock")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print(f"PASS build={build_id} cache={cache_bust_id} sw={sw_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
