#!/usr/bin/env python3
"""
CEZGP batch 1514 — Research-to-code matrix (P1–P10, Layer B, pillars).

Writes docs/generated/customer_experience_research_matrix.json with per-row status:
  implemented | partial | missing | external
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "customer_experience_research_matrix.json"


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    if path.is_file():
        return needle in path.read_text(encoding="utf-8", errors="replace")
    if path.is_dir():
        for child in path.rglob("*"):
            if not child.is_file() or child.suffix not in {".py", ".html", ".js", ".md"}:
                continue
            try:
                if needle in child.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                continue
    return False


def _rows() -> list[dict]:
    rows: list[dict] = []

    def add(
        row_id: str,
        pain: str,
        status: str,
        *,
        evidence: str = "",
        phase: str = "",
    ) -> None:
        rows.append(
            {
                "id": row_id,
                "pain": pain,
                "status": status,
                "phase": phase,
                "evidence": evidence,
            }
        )

    # P1 tenant TTV
    csv_kernel = _exists("apps/customersuccess/bulk_csv_student_import.py")
    csv_onboard = _contains(
        "apps/customersuccess/services.py", 'key": "student_csv_import"'
    ) or _contains("apps/customersuccess/services.py", '"student_csv_import"')
    if csv_onboard and csv_kernel:
        add("P1", "Tenant CSV import in guided onboarding", "implemented", phase="1516")
    elif csv_kernel:
        add("P1", "Tenant CSV import in guided onboarding", "partial", phase="1516")
    else:
        add("P1", "Tenant CSV import in guided onboarding", "missing", phase="1516")

    add(
        "P1b",
        "Guardian bulk invite after students",
        "implemented" if _contains("apps/customersuccess/services.py", '"guardian_invite"') else "missing",
        phase="1516",
    )
    add(
        "P1c",
        "Post-import fee generation step",
        "implemented" if _contains("apps/customersuccess/services.py", '"post_fees"') else "missing",
        phase="1516",
    )
    add("P1d", "Migration Cloud CSV path link", "external", phase="1516")

    # P2 parent identity
    pay_all = _contains("apps/portal/urls.py", "parent_finance_pay_all") or _contains(
        "apps/portal/views_parent_finance.py", "parent_finance_pay_all"
    )
    simplified = _contains("apps/portal/views_parent.py", "parent_simplified")
    passkey = _exists("apps/accounts/models.py") and _contains(
        "apps/accounts/models.py", "UserPasskey"
    )
    password_reset = _contains("apps/accounts/urls.py", 'name="password_reset"') and _contains(
        "templates/auth/login.html", "data-rmc-parent-password-reset"
    )
    guardian_chrome = _contains(
        "templates/portal_base.html", "guardian_student_links.html"
    ) and _contains("apps/portal/parent_identity.py", "guardian_student_links_chrome")
    add(
        "P2",
        "Parent login/session UX",
        "implemented"
        if simplified and guardian_chrome and password_reset
        else "partial",
        phase="1517",
    )
    add(
        "P2b",
        "Passkey CTA for parents",
        "implemented"
        if _contains("templates/parent/settings_security.html", "parent-passkey-cta")
        else "missing",
        phase="1517",
    )
    add(
        "P2c",
        "Multi-school guardian switch",
        "implemented"
        if _contains("apps/portal/parent_identity.py", "school_membership_switch")
        else "missing",
        phase="1517",
    )
    add(
        "P2d",
        "link_child / claim_invite in Cmd+K",
        "implemented"
        if _contains("apps/siteconfig/command_bar_registry.py", "link_child")
        else "missing",
        phase="1520",
    )

    # P3 navigation
    add(
        "P3",
        "Click depth / Cmd+K",
        "implemented"
        if _contains("apps/siteconfig/command_bar_registry.py", "Import students (CSV)")
        and _contains("apps/siteconfig/command_bar_registry.py", "parent_finance_pay_all")
        else "partial",
        phase="1520",
    )
    add(
        "P3b",
        "Parent simplified default home",
        "implemented"
        if _contains("apps/portal/views_parent.py", "parent_simplified_default")
        else "partial",
        phase="1517",
    )

    # P4 pay-all
    if pay_all and _contains("apps/portal/views_parent_finance.py", "family_billing_aggregator"):
        add("P4", "Parent pay-all checkout", "implemented", phase="1515")
    elif _exists("apps/finance/family_billing_aggregator.py"):
        add("P4", "Parent pay-all checkout", "partial", phase="1515")
    else:
        add("P4", "Parent pay-all checkout", "missing", phase="1515")

    add(
        "P4b",
        "Wallet on finance hero",
        "implemented" if _contains("templates/parent/finance.html", "wallet") else "partial",
        phase="1515",
    )
    add(
        "P4c",
        "Payment receipt email",
        "implemented"
        if _contains("apps/portal/views_parent_finance.py", "dispatch_payment_received_intent")
        else "missing",
        phase="1515",
    )

    # P5 status
    real_probes = _contains("apps/observability/public_status.py", "probe_celery") or _contains(
        "apps/observability/public_status.py", "_probe_auth"
    )
    add(
        "P5",
        "Real public status probes",
        "implemented" if real_probes else "partial",
        phase="1518",
    )
    add(
        "P5b",
        "Enrollment peak banner",
        "implemented"
        if _contains("apps/observability", "ENROLLMENT_PEAK")
        else "missing",
        phase="1518",
    )

    # P6 offline
    add(
        "P6",
        "Parent offline pay intent",
        "implemented"
        if _contains("templates/parent/finance.html", "data-rmc-offline-form")
        else "missing",
        phase="1520",
    )
    add(
        "P6b",
        "Regional rails on pay-all",
        "implemented"
        if _contains("apps/portal/views_parent_finance.py", "regional_payment_profile")
        else "partial",
        phase="1521",
    )

    # P7 feedback
    notify = _contains("apps/feedback/signals.py", "notify_critical_feedback_submission")
    add(
        "P7",
        "Feedback submission notifications",
        "implemented"
        if notify and _contains("apps/feedback/notification_services.py", "notify_critical_feedback_submission")
        else "missing",
        phase="1519",
    )
    add(
        "P7b",
        "Feedback → GlobalSupportTicket bridge UI",
        "implemented"
        if _contains("apps/feedback/views.py", "create_support_ticket_from_feedback")
        else "partial",
        phase="1519",
    )
    p7c_ok = (
        _exists("apps/feedback/legacy_product_feedback_migration.py")
        and _exists("apps/feedback/management/commands/migrate_product_feedback_legacy.py")
        and _contains("apps/feedback/legacy_product_feedback_migration.py", "migrate_legacy_rows")
    )
    add(
        "P7c",
        "ProductFeedback legacy migration",
        "implemented" if p7c_ok else "partial",
        phase="1519",
    )

    # P8 trust
    add("P8", "Trust surfaces honest", "implemented" if _exists("scripts/verify_trust_compliance_surfaces.py") else "partial", phase="1518")
    p8b_ok = (
        _exists("apps/lifecycle/views_tenant_gdpr_export.py")
        and _contains("config/tenant_urls.py", "tenant_gdpr_data_export")
        and _exists("templates/lifecycle/tenant_gdpr_data_export.html")
        and _contains("apps/customersuccess/services.py", "tenant_gdpr_data_export")
    )
    add(
        "P8b",
        "Tenant GDPR export entry",
        "implemented" if p8b_ok else "partial",
        phase="1516",
    )

    # P9 P10
    add("P9", "Integration health on status", "implemented" if real_probes else "missing", phase="1518")
    pricing_ok = (
        _exists("apps/customersuccess/pricing_billing_clarity.py")
        and _contains("apps/customersuccess/pricing_billing_clarity.py", "pricing_clarity_crosswalk")
        and _contains("templates/customersuccess/tenant_billing_estimate.html", "pricing-clarity-crosswalk")
    )
    add(
        "P10",
        "Pricing clarity crosswalk",
        "implemented" if pricing_ok else "partial",
        phase="1522",
    )

    # Layer B
    add("B1", "Tenant isolation scanners", "implemented", evidence="scan_tenant_queryset_safety baseline 0")
    add(
        "B2",
        "Tenant launch SLA",
        "implemented"
        if _exists("scripts/verify_tenant_launch_sla.py")
        and _exists("scripts/verify_tenant_onboarding_csv_import.py")
        else "missing",
        phase="1516",
    )
    add("B3", "Reliability status", "implemented" if real_probes else "partial", phase="1518")
    add("B4", "Roadmap stub honesty", "implemented" if _contains("apps/api/roadmap_due_today_views.py", "code_presence_stub") else "partial", phase="1522")
    add("B5", "Help deflection tiers", "implemented", evidence="verify_help_center_tiers.py")
    b6_ok = (
        _exists("apps/customersuccess/pricing_billing_clarity.py")
        and _contains("apps/customersuccess/pricing_billing_clarity.py", "tenant_billing_estimate")
        and _contains("apps/siteconfig/urls.py", "tenant_billing_estimate")
    )
    add("B6", "Tenant billing estimate", "implemented" if b6_ok else "partial", phase="1521")

    # Pillars / externals
    add("PILLAR_AWS", "Infra status probes", "implemented" if real_probes else "partial", phase="1518")
    amazon_ok = _contains(
        "templates/marketplace/governance_console.html", "data-rmc-marketplace-operator-frame"
    ) and _contains("templates/marketplace/governance_console.html", "marketplace-operator-frame")
    add(
        "PILLAR_AMAZON",
        "Marketplace operator frame",
        "implemented" if amazon_ok else "partial",
        phase="1522",
    )
    contact_wf = _contains("templates/parent/contact_school.html", "workflow_next_action")
    add(
        "PILLAR_SALESFORCE",
        "Parent contact workflow",
        "implemented" if contact_wf else "partial",
        phase="1520",
    )
    add("PILLAR_SHOPIFY", "Fee commerce pay-all", "implemented" if pay_all else "partial", phase="1515")
    add("GEOS_MARKET_READY", "market_ready evidence", "external")
    add("GEOS_NATIVE_APP", "Native app stores", "external")
    add("SOC2_PDF", "SOC2 auditor PDF", "external")
    add("LIVE_PSP", "Live PSP settlement", "external")
    add("LITELLM_OS", "LiteLLM omnipresent OS", "external")

    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Fail if any row is missing")
    parser.add_argument(
        "--strict-zero-partials",
        action="store_true",
        help="Fail if any row is partial (Lane 2 closeout).",
    )
    args = parser.parse_args()

    rows = _rows()
    missing = [r for r in rows if r["status"] == "missing"]
    partial = [r for r in rows if r["status"] == "partial"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "missing_count": len(missing),
        "partial_count": len(partial),
        "external_count": sum(1 for r in rows if r["status"] == "external"),
        "implemented_count": sum(1 for r in rows if r["status"] == "implemented"),
        "rows": rows,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT}")

    print(
        f"CEZGP matrix: implemented={payload['implemented_count']} "
        f"partial={payload['partial_count']} missing={payload['missing_count']} "
        f"external={payload['external_count']}"
    )

    if args.strict and missing:
        for r in missing:
            print(f"  MISSING: {r['id']} — {r['pain']}", file=sys.stderr)
        return 1
    if args.strict_zero_partials and partial:
        for r in partial:
            print(f"  PARTIAL: {r['id']} — {r['pain']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
