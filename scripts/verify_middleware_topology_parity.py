#!/usr/bin/env python3
"""Gate: middleware present in the base MIDDLEWARE must also load in the tenants topology.

config/settings.py builds MIDDLEWARE twice:

    line  335  col 0   MIDDLEWARE  = [...]     # base
    line  426  col 0   MIDDLEWARE += [...]     # base
    line 3983  col 4   MIDDLEWARE  = [...]     # inside `if USE_DJANGO_TENANTS and postgresql`

The third is a *wholesale reassignment*, not an append, and nothing mutates
MIDDLEWARE after it. Production sets USE_DJANGO_TENANTS=1 on Postgres, so the
base list is dead code in prod and the tenants list is the only one that runs.

That makes the two lists a hand-maintained duplicate pair, and it has drifted:
a middleware added to the base list alone is silently inert in production while
looking wired in code review and going green in any SQLite test (which takes the
base branch). This is the same shape as the RLS static-TABLES-list blind spot and
the watchdog beat-registry gap — a second registry nobody remembers to update.

This scanner parses both lists and requires every base entry to be either
present in the tenants list or explicitly classified below. Deny-by-default:
an unclassified drop fails the gate.

Exit 0 = no unclassified drift. Exit 1 = drift (or KNOWN_GAP growth).
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

# Deliberately base-only: these must NOT be in the tenants topology.
# Each entry needs a reason — "it was already missing" is not a reason.
INTENTIONAL_BASE_ONLY = {
    "apps.schools.middleware.TenantMiddleware":
        "Replaced by HealthAwareTenantMainMiddleware + TenantSchemaSchoolBridgeMiddleware "
        "(settings.py notes 'TenantMiddleware is not used' at the end of the tenants list).",
    "apps.schools.middleware.RlsResetOnExceptionMiddleware":
        "RLS-mode only; under SCHEMA tenancy (USE_DJANGO_TENANTS=1) there is no RLS session var to reset.",
    "apps.observability.middleware_agent_template_debug.AgentTemplateMissingDebugMiddleware":
        "Debug-only template-miss reporter; not a production control.",
}

# Base-only entries that are believed to be REAL GAPS: they look security- or
# correctness-relevant and their absence from prod is probably unintended.
# Listed so the gate is green on the measured baseline while each is triaged;
# the count must not grow. Removing one from here (by wiring it into the tenants
# list) is the fix. Adding one here requires an explicit decision.
KNOWN_GAPS = {
    "apps.security.csp_middleware.ContentSecurityPolicyMiddleware":
        "Content-Security-Policy never enforced in prod despite settings.py claiming enforced-by-default.",
    "corsheaders.middleware.CorsMiddleware":
        "CORS headers not applied in prod.",
    "apps.api.middleware_tenant_cors.TenantCorsAllowlistMiddleware":
        "Per-tenant CORS allowlist not applied in prod.",
    "apps.api.middleware_idempotency.IdempotencyKeyMiddleware":
        "API idempotency keys not honoured in prod (cf. the payments webhook redelivery storm).",
    "apps.accounts.middleware.TenantHostControlPlaneIsolationMiddleware":
        "Operators reach tenant hosts without signed impersonation — boundary control absent from the tenant topology.",
    "apps.accounts.middleware.ImpersonationReadOnlyGuardMiddleware":
        "Tenants list carries ReadOnlyImpersonationGuardMiddleware instead; confirm they are equivalent before closing.",
    "apps.schools.middleware_operator_mfa.OperatorMfaRequiredMiddleware":
        "Operator MFA requirement not enforced in prod.",
    "apps.schools.middleware.SuperAdminRateLimitMiddleware":
        "/super/ 120/min per-user rate limit absent in prod.",
    "apps.schools.middleware_enterprise_security.EnterpriseSuperHttpAuditMiddleware":
        "Opt-in ENTERPRISE_SUPER_HTTP_AUDIT=1 audit cannot engage in prod.",
    "apps.compliance.middleware.ComplianceGuardMiddleware":
        "region -> feature_code RESTRICTED/DISABLED enforcement absent in prod.",
    "apps.accounts.middleware_security_posture.SecurityPostureReviewMiddleware":
        "Security-posture review interstitial absent in prod.",
    "apps.accounts.middleware_minimum_security_strength.MinimumSecurityStrengthMiddleware":
        "Minimum security strength not enforced in prod.",
    "apps.accounts.middleware.ManagerTenantPrimarySurfaceBlockMiddleware":
        "manager-host surface block absent in prod.",
    "apps.siteconfig.middleware.OperatorSiteconfigManagerShellMiddleware":
        "Operator siteconfig -> manager shell redirect absent in prod.",
    "apps.schools.middleware_residency.DataResidencyMiddleware":
        "Data-residency mismatch logging absent in prod (flag DATA_RESIDENCY_ENFORCE is moot).",
    "config.middleware.RequestTimeoutMiddleware":
        "Request timeout guard absent in prod.",
    "apps.siteconfig.middleware.html_no_cache.HtmlNoCacheMiddleware":
        "HTML no-cache headers absent in prod.",
    "apps.schools.middleware.ModuleActivationMiddleware":
        "Module activation gating absent in prod.",
    "apps.integrations_marketplace.middleware.TenantEmailBindingMiddleware":
        "Tenant email binding absent in prod.",
    "apps.platform_runtime.middleware_regional_db.RegionalDatabaseMiddleware":
        "Regional DB routing absent in prod (M27 region replicas are external anyway).",
    "apps.platform_runtime.workflow_request_middleware.WorkflowProgressRequestMiddleware":
        "Workflow progress request binding absent in prod.",
    "apps.api.middleware_edge_fallback.EdgeSWRFallbackMiddleware":
        "Edge stale-while-revalidate fallback absent in prod.",
    "apps.schools.marketing_geo_middleware.RunMyCampusGeoMiddleware":
        "Marketing geo routing absent in prod.",
    "apps.migration_cloud.api.rate_limiting.SoftWarnHeaderMiddleware":
        "Migration Cloud soft-warn headers absent in prod.",
}


def _middleware_strings(node: ast.AST) -> list[str]:
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def collect(settings_path: pathlib.Path) -> tuple[list[str], list[str]]:
    """Return (base, tenants) middleware paths, in declaration order."""
    tree = ast.parse(settings_path.read_text(encoding="utf-8"))
    base: list[str] = []
    tenants: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AugAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        if not (isinstance(target, ast.Name) and target.id == "MIDDLEWARE"):
            continue
        values = _middleware_strings(node.value)
        # col_offset 0 => module level (the base list). Indented => inside the
        # `if USE_DJANGO_TENANTS and postgresql` branch (the prod list).
        if node.col_offset == 0:
            base += values
        else:
            tenants += values
    return base, tenants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="config/settings.py")
    parser.add_argument(
        "--list-gaps",
        action="store_true",
        help="print the classified KNOWN_GAPS and exit 0 (triage aid, not a gate run)",
    )
    args = parser.parse_args()

    path = pathlib.Path(args.settings)
    if not path.exists():
        print(f"FAIL: {path} not found")
        return 1

    base, tenants = collect(path)
    if not base or not tenants:
        print(
            "FAIL: could not parse both MIDDLEWARE lists "
            f"(base={len(base)}, tenants={len(tenants)}). "
            "The settings topology changed — update this scanner."
        )
        return 1

    tenant_set = set(tenants)
    missing = [m for m in base if m not in tenant_set]

    classified = set(INTENTIONAL_BASE_ONLY) | set(KNOWN_GAPS)
    unclassified = [m for m in missing if m not in classified]
    # A KNOWN_GAP that is now wired is a fix — tell the author to delete the entry
    # so the list can only shrink.
    stale = [m for m in KNOWN_GAPS if m in tenant_set]

    print(f"base MIDDLEWARE:    {len(base)}")
    print(f"tenants MIDDLEWARE: {len(tenants)}  (the only list that runs in prod)")
    print(f"base-only:          {len(missing)}")
    print(
        f"  intentional={len([m for m in missing if m in INTENTIONAL_BASE_ONLY])}"
        f"  known-gap={len([m for m in missing if m in KNOWN_GAPS])}"
        f"  UNCLASSIFIED={len(unclassified)}"
    )

    if args.list_gaps:
        print("\nKNOWN_GAPS (absent from prod, awaiting triage):")
        for m in base:
            if m in KNOWN_GAPS and m in missing:
                print(f"  - {m}\n      {KNOWN_GAPS[m]}")
        return 0

    failed = False
    if unclassified:
        failed = True
        print(
            f"\nFAIL: {len(unclassified)} middleware in the base list never load in "
            "production and are not classified.\n"
            "  Production takes the USE_DJANGO_TENANTS branch, which REPLACES MIDDLEWARE.\n"
            "  Add each to the tenants list in config/settings.py, or classify it in this\n"
            "  scanner as INTENTIONAL_BASE_ONLY (with a reason) or KNOWN_GAPS."
        )
        for m in unclassified:
            print(f"  - {m}")

    if stale:
        failed = True
        print(
            f"\nFAIL: {len(stale)} entries are listed as KNOWN_GAPS but are now wired "
            "into the tenants list. Delete them from KNOWN_GAPS so the list only shrinks."
        )
        for m in stale:
            print(f"  - {m}")

    if not failed:
        print("\nOK: no unclassified middleware topology drift.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
