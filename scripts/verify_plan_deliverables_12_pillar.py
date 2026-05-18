#!/usr/bin/env python
"""12-pillar plan deliverables verifier.

Companion to `verify_plan_deliverables.py` (which gates the original
7-pillar plan). This one gates the **extended 12-pillar plan** at
`C:/Users/yimga/.claude/plans/look-through-this-plan-sparkling-rain.md`,
specifically its "Final deliverables checklist" section.

The audit at batch 1269 (memory: 12-pillar-plan-audit-closeout-v3-23-5)
found that the older `verify_plan_deliverables.py` returned "All required
plan deliverable docs present" while 5 docs from the new plan's checklist
were silently missing. This verifier closes that gap: every new doc
required by the 12-pillar plan is enumerated here, and CI fails if any
required artifact is missing.

Usage:
    python scripts/verify_plan_deliverables_12_pillar.py
    python scripts/verify_plan_deliverables_12_pillar.py --strict   # exit 1 on missing
    python scripts/verify_plan_deliverables_12_pillar.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Per-pillar required artifacts. Each entry is (pillar, kind, path, why).
# Kind is informational — file / dir / verifier_must_exist. The check is
# always "the path exists".
REQUIRED_ARTIFACTS: tuple[tuple[str, str, str, str], ...] = (
    # --- P0/P6 deploy gate ---
    ("P0", "file",  "apps/automation/migrations/0018_workflow_trigger_offline_action.py", "Offline-action migration (deploy gate)"),
    ("P0", "file",  "scripts/verify_migration_files_tracked.py", "Migration-file tracking gate"),
    ("P6", "file",  "scripts/release/render_predeploy.sh", "Render predeploy pipeline"),
    ("P6", "file",  "docs/DEPLOY_PIPELINE_RUNBOOK.md", "Deploy pipeline runbook"),
    # --- P1/P2 design + a11y ---
    ("P1", "file",  "static/css/design-tokens.css", "Canonical design tokens"),
    ("P1", "file",  "scripts/scan_sri_required.py", "SRI requirement scanner"),
    ("P1", "file",  "scripts/verify_csp_nonce_emission.py", "CSP nonce emission verifier"),
    ("P1", "file",  "lighthouserc.cjs", "Lighthouse CI thresholds"),
    ("P2", "file",  "apps/compliance/tests/test_a11y_axe_smoke.py", "axe smoke test (public + manager + 400% zoom + RTL)"),
    ("P2", "file",  ".github/workflows/a11y-axe.yml", "axe CI workflow"),
    # --- P3/P7 tenancy + security ---
    ("P3", "file",  "scripts/scan_tenant_queryset_safety.py", "Tenant queryset scanner"),
    ("P3", "file",  "scripts/audit_role_permission_matrix.py", "RBAC matrix auditor"),
    ("P3", "file",  "docs/generated/role_permission_matrix.json", "RBAC matrix JSON output"),
    ("P3", "file",  "apps/tenancy/__init__.py", "Tenancy app"),
    ("P7", "file",  "apps/security/csp_middleware.py", "CSP middleware"),
    ("P7", "file",  "apps/finance/regional_payment_profiles.py", "Data-residency / regional payment routing"),
    ("P7", "file",  "apps/integrations_marketplace/token_refresh.py", "OAuth token rotation"),
    ("P7", "file",  "scripts/scan_ai_gateway_boundary.py", "AI inference boundary"),
    # --- P4/P5 data + finance ---
    ("P4", "dir",   "apps/migration_cloud/intake", "Migration intake wizard"),
    ("P4", "file",  "apps/sync_engine/conflict_resolver.py", "Sync conflict resolver"),
    ("P4", "file",  "apps/analytics/management/commands/verify_pgvector_index.py", "pgvector index verifier"),
    ("P5", "dir",   "apps/billing", "Billing app"),
    ("P5", "dir",   "apps/plans_entitlements", "Plans + entitlements"),
    ("P5", "file",  "apps/marketplace/monetization.py", "Marketplace monetization"),
    ("P5", "file",  "scripts/scan_money_float.py", "Money/float scanner"),
    ("P5", "file",  "apps/finance/tests/test_webhook_signature_verifiers.py", "Webhook signature tests"),
    # --- P8 AI/ML governance ---
    ("P8", "file",  "apps/analytics/management/commands/bootstrap_at_risk_registry.py", "Registry bootstrap"),
    ("P8", "file",  "apps/analytics/management/commands/verify_ai_promotion_readiness.py", "Promotion-readiness verifier"),
    ("P8", "file",  "apps/analytics/management/commands/verify_ai_ml_readiness.py", "End-to-end AI readiness verifier"),
    ("P8", "file",  "apps/analytics/tests/test_at_risk_model_registry.py", "Registry tests"),
    ("P8", "file",  "apps/analytics/tests/test_verify_ai_promotion_readiness.py", "Promotion-readiness tests"),
    ("P8", "file",  "services/ai_helpers.py", "AI helpers (looks_like_pii + redact_pii + invoke_with_request)"),
    ("P8", "file",  "docs/AI_ML_GOVERNANCE_AUDIT.md", "AI/ML governance audit doc"),
    # --- P9 mobile / PWA / offline ---
    ("P9", "file",  "apps/portal/views_offline_sync.py", "Offline sync views"),
    ("P9", "file",  "apps/platform_runtime/offline_queue.py", "Offline queue"),
    ("P9", "file",  "static/js/service-worker.js", "Service worker"),
    ("P9", "file",  "scripts/verify_service_worker_version.py", "SW version verifier"),
    ("P9", "file",  "scripts/scan_pwa_manifest_coverage.py", "PWA manifest coverage scanner"),
    # --- P10 observability ---
    ("P10", "file", "apps/observability/slo.py", "SLO registry"),
    ("P10", "file", "scripts/verify_slo_registry.py", "SLO registry verifier"),
    ("P10", "file", "apps/observability/db_liveness.py", "DB liveness"),
    ("P10", "file", "apps/platform_runtime/views_rum.py", "RUM beacon endpoint"),
    ("P10", "file", "apps/integrations_marketplace/sentry_alert_rules.py", "Sentry alert rules as code"),
    ("P10", "file", "scripts/verify_sentry_alert_rule_drift.py", "Sentry alert drift detector"),
    ("P10", "file", "docs/OBSERVABILITY_SLO_REGISTRY.md", "Observability SLO registry doc"),
    # --- P11 comms + i18n ---
    ("P11", "file", "apps/communication/email_signing.py", "Email DKIM signing"),
    ("P11", "file", "apps/siteconfig/i18n_catalog_builder.py", "i18n catalog builder"),
    ("P11", "file", "scripts/verify_i18n_catalog_fresh.py", "Catalog freshness gate"),
    ("P11", "file", "scripts/scan_locale_coverage.py", "Locale coverage drift scanner"),
    ("P11", "file", "docs/I18N_RTL_AUDIT.md", "i18n + RTL audit doc"),
    # --- P12 test infra + DR ---
    ("P12", "file", "pytest.ini", "pytest config + coverage thresholds"),
    ("P12", "file", "conftest.py", "conftest"),
    ("P12", "file", "scripts/verify_dr_drill_schedule.py", "DR drill schedule verifier"),
    ("P12", "file", "scripts/restore_drill.py", "Restore drill tool"),
    ("P12", "file", "var/dr-drill-schedule.json", "DR drill schedule"),
    ("P12", "file", "docs/generated/dr_drill_log.json", "DR drill history"),
    ("P12", "file", ".github/workflows/coverage-gate.yml", "Coverage gate workflow"),
    ("P12", "file", "docs/TEST_INFRA_AUDIT.md", "Test infrastructure audit doc"),
    ("P12", "file", "docs/DR_RUNBOOK.md", "DR runbook"),
)


def _check(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any required artifact is missing.")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout instead of text.")
    args = parser.parse_args()

    rows = []
    missing = []
    for pillar, kind, path, why in REQUIRED_ARTIFACTS:
        ok = _check(path)
        rows.append({"pillar": pillar, "kind": kind, "path": path, "why": why, "present": ok})
        if not ok:
            missing.append((pillar, path, why))

    if args.json:
        json.dump(
            {
                "total": len(rows),
                "present": len(rows) - len(missing),
                "missing": len(missing),
                "items": rows,
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(
            f"12-pillar plan deliverables: {len(rows) - len(missing)}/{len(rows)} present\n"
        )
        if missing:
            sys.stdout.write("MISSING:\n")
            for pillar, path, why in missing:
                sys.stdout.write(f"  [{pillar}] {path}  ({why})\n")
        else:
            sys.stdout.write("All 12-pillar plan deliverables present.\n")

    if args.strict and missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
