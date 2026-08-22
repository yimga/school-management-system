#!/usr/bin/env python3
"""AWS P1: SSE handlers fail-closed on tenant hosts without school context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    failures: list[str] = []

    ai_stream = (ROOT / "apps" / "portal" / "views_ai_stream.py").read_text(encoding="utf-8")
    if 'status=403' not in ai_stream or "tenant_required" not in ai_stream:
        failures.append("views_ai_stream.py must 403 tenant hosts without school")

    workflow = (
        ROOT / "apps" / "platform_runtime" / "views_workflow_progress.py"
    ).read_text(encoding="utf-8")
    if "tenant_required" not in workflow or "stream_view" not in workflow:
        failures.append("views_workflow_progress.py stream_view must guard tenant hosts")
    if 'host_kind not in {"manager", "local"}' not in workflow:
        failures.append("workflow SSE must distinguish manager vs tenant hosts")

    mc_views = (ROOT / "apps" / "migration_cloud" / "views.py").read_text(encoding="utf-8")
    if "_tenant_scoped_bundle" not in mc_views:
        failures.append("migration_cloud views must scope bundles by tenant")
    if "MigrationCloudProgressStreamView" not in mc_views:
        failures.append("migration cloud operator progress SSE view missing")

    mc_tenant = (
        ROOT / "apps" / "migration_cloud" / "views_tenant_upload.py"
    ).read_text(encoding="utf-8")
    if "TenantMigrationProgressStreamView" not in mc_tenant:
        failures.append("migration cloud tenant progress SSE view missing")
    if "_tenant_bundle_or_404" not in mc_tenant:
        failures.append("tenant migration views must scope bundles via _tenant_bundle_or_404")
    if "_TenantAdminRequiredMixin" not in mc_tenant:
        failures.append("tenant migration held/progress surfaces must use tenant-admin gate")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(f"verify_sse_tenant_ingress: {len(failures)} FAIL", file=sys.stderr)
        return 1
    print("verify_sse_tenant_ingress: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
