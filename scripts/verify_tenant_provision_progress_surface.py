#!/usr/bin/env python3
"""Customer provisioning progress surface — component, API contract, Tenant 360 parity."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-tenant-provision-progress-surface.json"


def _text(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _finding(code: str, detail: str, *, path: str = "") -> dict[str, str]:
    return {"code": code, "detail": detail, "path": path}


def run_scan() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    partial = REPO_ROOT / "templates" / "components" / "rmc_tenant_provision_progress.html"
    js = REPO_ROOT / "static" / "js" / "rmc-tenant-provision-progress.js"
    if not partial.is_file():
        findings.append(_finding("missing_partial", "rmc_tenant_provision_progress.html", path=str(partial)))
    if not js.is_file():
        findings.append(_finding("missing_js", "rmc-tenant-provision-progress.js", path=str(js)))
    else:
        js_txt = js.read_text(encoding="utf-8")
        for needle in (
            "aria-valuenow",
            "rmc-provision-progress__fill",
            "progress_percent",
            "data-rmc-copilot-context",
        ):
            if needle not in js_txt:
                findings.append(_finding("js_contract", f"missing:{needle}", path="static/js/rmc-tenant-provision-progress.js"))

    for tpl, marker in (
        ("templates/accounts/owner_onboarding/done.html", "rmc_tenant_provision_progress.html"),
        ("templates/accounts/owner_onboarding/account.html", "rmc_tenant_provision_progress.html"),
        ("templates/siteconfig/tenant_provisioning_status.html", "rmc_tenant_provision_progress.html"),
        ("templates/schools/tenant_setup_in_progress.html", "rmc_tenant_provision_progress.html"),
        ("templates/schools/super_tenant_360.html", "tenant-360-provisioning"),
    ):
        p = REPO_ROOT / tpl
        if not p.is_file() or marker not in p.read_text(encoding="utf-8"):
            findings.append(_finding("template_wiring", f"{tpl} missing {marker}", path=tpl))

    resolver = REPO_ROOT / "apps" / "schools" / "provisioning_progress.py"
    if not resolver.is_file():
        findings.append(_finding("missing_resolver", "provisioning_progress.py"))
    else:
        rtxt = resolver.read_text(encoding="utf-8")
        for needle in ("progress_percent", "current_step_label", "suggested_remediation", "portal_ready"):
            if needle not in rtxt:
                findings.append(_finding("resolver_contract", f"missing:{needle}", path="apps/schools/provisioning_progress.py"))

    accounts_urls = _text("apps/accounts/urls.py")
    for name in (
        "owner_onboarding_account_provision_progress",
        "owner_onboarding_provision_progress",
        "owner_onboarding_provision_apply_fix",
    ):
        if name not in accounts_urls:
            findings.append(_finding("url_missing", name, path="apps/accounts/urls.py"))

    public_urls = _text("config/public_urls.py")
    if "api_public_pending_provision_progress" not in public_urls:
        findings.append(
            _finding(
                "public_pending_api",
                "api_public_pending_provision_progress",
                path="config/public_urls.py",
            )
        )

    mw = _text("apps/schools/middleware.py")
    if "/api/pending-provision/" not in mw:
        findings.append(
            _finding(
                "pending_auth_prefix",
                "PENDING_TENANT_AUTH_PREFIXES must allow pending provision API",
                path="apps/schools/middleware.py",
            )
        )

    onboarding = _text("apps/accounts/views_owner_onboarding.py")
    if "resolve_provisioning_progress" not in onboarding:
        findings.append(_finding("owner_api", "must use resolve_provisioning_progress", path="apps/accounts/views_owner_onboarding.py"))

    tenant_api = _text("apps/lifecycle/views_tenant_lifecycle.py")
    if "resolve_provisioning_progress" not in tenant_api:
        findings.append(_finding("tenant_api", "must use resolve_provisioning_progress", path="apps/lifecycle/views_tenant_lifecycle.py"))

    fix_handlers = _text("apps/platform_runtime/workflow_fix_handlers.py")
    for kind in ("requeue_provision", "resend_welcome", "retry_dns_sync"):
        if kind not in fix_handlers:
            findings.append(_finding("owner_fix_kind", kind, path="apps/platform_runtime/workflow_fix_handlers.py"))

    auto_fix = _text("apps/platform_runtime/workflow_auto_fix.py")
    if "requeue_provision" not in auto_fix:
        findings.append(_finding("auto_fix_taxonomy", "requeue_provision", path="apps/platform_runtime/workflow_auto_fix.py"))

    old_poll = REPO_ROOT / "static" / "js" / "rmc-tenant-provisioning-status.js"
    done = _text("templates/accounts/owner_onboarding/done.html")
    if "rmc-tenant-provisioning-status.js" in done:
        findings.append(_finding("legacy_poll", "done.html still loads reload-only JS", path="templates/accounts/owner_onboarding/done.html"))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    findings = run_scan()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "findings": findings,
    }
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline ({len(findings)} findings)")
        return 0

    baseline_count = 0
    if BASELINE.is_file():
        baseline_count = int(json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0))

    if args.strict and len(findings) > baseline_count:
        for row in findings:
            print(f"TENANT_PROVISION_PROGRESS_SURFACE_FAIL {row['code']} {row.get('path','')} {row['detail']}")
        return 1

    print("TENANT_PROVISION_PROGRESS_SURFACE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
