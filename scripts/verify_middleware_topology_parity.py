#!/usr/bin/env python3
"""Gate: middleware present in the base MIDDLEWARE must also load in the tenants topology.

config/settings.py builds MIDDLEWARE twice:

    line  335  col 0   MIDDLEWARE  = [...]     # base
    line  426  col 0   MIDDLEWARE += [...]     # base
    line ~3983 col 4   MIDDLEWARE  = [...]     # inside `if USE_DJANGO_TENANTS and postgresql`

The third is a *wholesale reassignment*, not an append, and nothing mutates
MIDDLEWARE after it. Production sets USE_DJANGO_TENANTS=1 on Postgres, so the
base list is dead code in prod and the tenants list is the only one that runs.

That makes the two lists a hand-maintained duplicate pair, and it has drifted:
a middleware added to the base list alone is silently inert in production while
looking wired in code review and going green in any SQLite test (which takes the
base branch). This is the same shape as the RLS static-TABLES-list blind spot and
the watchdog beat-registry gap — a second registry nobody remembers to update.

This scanner parses both lists and requires every base entry to be classified.
Deny-by-default: an unclassified drop fails the gate.

  INTENTIONAL_BASE_ONLY — correctly base-only; must NOT be in the tenants list.
  DO_NOT_ADD            — base-only, and adding it to prod would CAUSE A BUG.
                          Wiring one of these is a FAILURE, not a fix.
  KNOWN_GAPS            — probably-real gaps, measured and awaiting triage.
                          The list may only shrink.

Exit 0 = no unclassified drift and nothing dangerous wired. Exit 1 otherwise.

NOTE ON PROVENANCE: the reasons below were verified by reading each middleware's
code, its flag defaults, and render.yaml. An earlier revision of this file carried
reasons inferred from middleware NAMES; several were wrong in ways that mattered
(RequestTimeoutMiddleware was described as a missing "timeout guard" when adding it
would in fact break tenant schema binding). Do not add an entry here whose reason
you have not confirmed against the code — a confidently-worded guess in this file
is worse than no entry, because the next reader will act on it.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

# Deliberately base-only: these must NOT be in the tenants topology.
INTENTIONAL_BASE_ONLY = {
    "apps.schools.middleware.TenantMiddleware":
        "Replaced by HealthAwareTenantMainMiddleware + TenantSchemaSchoolBridgeMiddleware "
        "(settings.py notes 'TenantMiddleware is not used' at the end of the tenants list).",
    "apps.schools.middleware.RlsResetOnExceptionMiddleware":
        "RLS-mode only; under SCHEMA tenancy (USE_DJANGO_TENANTS=1) there is no RLS session var to reset.",
    "apps.observability.middleware_agent_template_debug.AgentTemplateMissingDebugMiddleware":
        "Debug-only template-miss reporter; not a production control.",
}

# Base-only AND actively harmful to add. Wiring one of these into the tenants list
# is a regression — the gate fails if it appears there. Each reason is code-verified.
DO_NOT_ADD = {
    "config.middleware.RequestTimeoutMiddleware":
        "WOULD BREACH TENANT ISOLATION. Runs the downstream chain in a ThreadPoolExecutor "
        "worker (config/middleware.py:171-174). Django DB connections are thread-local, so "
        "the pool thread gets a FRESH connection with no search_path set -> every tenant "
        "query silently hits the PUBLIC schema. Also orphans one Postgres connection per "
        "request (CONN_MAX_AGE=120; the pool thread dies without closing it). Redundant "
        "anyway: REQUEST_TIMEOUT_SECONDS defaults to 120 = the gunicorn timeout "
        "(config/gunicorn.conf.py:72). Arguably should be removed from the base list too.",
    "apps.api.middleware_tenant_cors.TenantCorsAllowlistMiddleware":
        "CROSS-TENANT LEAK, currently masked by being broken. middleware_tenant_cors.py:78 "
        "does `settings.CORS_ALLOWED_ORIGINS = _merge_origins(...)` — a permanent PROCESS-GLOBAL "
        "mutation, never restored, despite a docstring claiming a thread-local override. It is "
        "inert today only because it sits above tenant resolution in the base list, so "
        "tenant_origins is always empty. Wiring it into prod CORRECTLY (after school "
        "resolution) is what ACTIVATES the leak: tenant A's custom origins accumulate into the "
        "global allowlist for every later request in that worker. Fix the mutation first "
        "(restore in a finally, or use the corsheaders check_request_enabled signal).",
    "apps.schools.middleware.ModuleActivationMiddleware":
        "DEAD CODE. It writes request.active_modules and nothing reads it — grepped across "
        "*.py / *.html / *.js, the only hits are the middleware itself and the settings line "
        "mounting it. Adding it buys a get_tenant_modules() call per request for nothing. "
        "Delete the middleware or keep it out; there is no 'module activation gating' to restore.",
    "apps.schools.marketing_geo_middleware.RunMyCampusGeoMiddleware":
        "REDUNDANT. marketing_media_context is a registered context processor "
        "(config/settings.py:608) and calls marketing_geo_context(request), which sets "
        "request.geo_context itself (marketing_geo_context.py:70). The only non-template "
        "reader (regional_surface_tokens.py:40) is a template helper with its own "
        "brand -> school -> 'US' fallback chain.",
}

# Probably-real gaps: absent from prod, plausibly unintended. Measured so the gate is
# green on the baseline while each is triaged; the list may only shrink. Closing one
# means DELETING its entry here.
KNOWN_GAPS = {
    # --- staged: real controls that must not ship as-is ---
    "apps.accounts.middleware_minimum_security_strength.MinimumSecurityStrengthMiddleware":
        "MASS-LOCKOUT AS-IS. SECURITY_ENFORCE_MINIMUM_STRENGTH defaults '1' (settings.py:1338) "
        "-> instant enforcement. Scoring: password 25 + MFA 30 + verified email 20 + passkey 10 "
        "+ recovery 10 + phone 5. Strict roles (ADMIN/SUPERADMIN/BURSAR/ACCOUNTANT/"
        "FINANCE_STAFF/PROPRIETOR) require 80, so an admin with password+MFA+verified email "
        "scores 75 and is pinned to the profile page. Unverified-email users score 25 and are "
        "blocked outright. Grace period anchors on date_joined, so it protects only new "
        "accounts. No /api/ bypass -> 302s API traffic. Only add with "
        "SECURITY_ENFORCE_MINIMUM_STRENGTH=0 in the same commit.",
    "apps.accounts.middleware_security_posture.SecurityPostureReviewMiddleware":
        "BOUNCES THE ENTIRE USER BASE as-is. SECURITY_POSTURE_REVIEW_NAG_ENABLED = not "
        "RUNNING_TESTS (settings.py:3614), and is_security_posture_review_due returns True when "
        "last_security_posture_review_at is None — true for every existing user. No /api/ or "
        "/static/ bypass, so the first request of a session gets 302'd even for JSON (a "
        "first-request POST loses its body). Needs an /api/ bypass + a backfill or "
        "enforcement-date anchor first. MUST sit after ModuleAccessMiddleware (see note below).",
    # --- ordering-sensitive, otherwise real ---
    # --- safe, low blast radius ---
    # --- inert behind flags render.yaml never sets: parity-only, no security value today ---
    "apps.schools.middleware_residency.DataResidencyMiddleware":
        "NO-OP: soft-log only unless DATA_RESIDENCY_ENFORCE, which render.yaml does not set. "
        "Wire it alongside the flag flip it belongs to, not before.",
    "apps.platform_runtime.middleware_regional_db.RegionalDatabaseMiddleware":
        "ALIAS-NO-OP when ENABLE_MULTI_REGION=False; residency enforce still runs if DATA_RESIDENCY_ENFORCE. M27 physical replicas EXTERNAL.",
    "apps.api.middleware_edge_fallback.EdgeSWRFallbackMiddleware":
        "NO-OP: RMC_EDGE_FALLBACK_ENABLED unset in render.yaml.",
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

    classified = set(INTENTIONAL_BASE_ONLY) | set(DO_NOT_ADD) | set(KNOWN_GAPS)
    unclassified = [m for m in missing if m not in classified]
    # A KNOWN_GAP that is now wired is a fix — tell the author to delete the entry
    # so the list can only shrink.
    stale = [m for m in KNOWN_GAPS if m in tenant_set]
    # A DO_NOT_ADD that is now wired is a REGRESSION, not a fix.
    dangerous = [m for m in DO_NOT_ADD if m in tenant_set]

    print(f"base MIDDLEWARE:    {len(base)}")
    print(f"tenants MIDDLEWARE: {len(tenants)}  (the only list that runs in prod)")
    print(f"base-only:          {len(missing)}")
    print(
        f"  intentional={len([m for m in missing if m in INTENTIONAL_BASE_ONLY])}"
        f"  do-not-add={len([m for m in missing if m in DO_NOT_ADD])}"
        f"  known-gap={len([m for m in missing if m in KNOWN_GAPS])}"
        f"  UNCLASSIFIED={len(unclassified)}"
    )

    if args.list_gaps:
        print("\nKNOWN_GAPS (absent from prod, awaiting triage):")
        for m in base:
            if m in KNOWN_GAPS and m in missing:
                print(f"  - {m}\n      {KNOWN_GAPS[m]}")
        print("\nDO_NOT_ADD (absent from prod ON PURPOSE — adding these causes bugs):")
        for m in base:
            if m in DO_NOT_ADD and m in missing:
                print(f"  - {m}\n      {DO_NOT_ADD[m]}")
        return 0

    failed = False
    if unclassified:
        failed = True
        print(
            f"\nFAIL: {len(unclassified)} middleware in the base list never load in "
            "production and are not classified.\n"
            "  Production takes the USE_DJANGO_TENANTS branch, which REPLACES MIDDLEWARE.\n"
            "  Add each to the tenants list in config/settings.py, or classify it in this\n"
            "  scanner as INTENTIONAL_BASE_ONLY / DO_NOT_ADD / KNOWN_GAPS — with a reason\n"
            "  you verified against the code, not inferred from the name."
        )
        for m in unclassified:
            print(f"  - {m}")

    if dangerous:
        failed = True
        print(
            f"\nFAIL: {len(dangerous)} middleware classified DO_NOT_ADD have been wired into "
            "the tenants list. These are base-only ON PURPOSE — adding them causes a bug "
            "(tenant-isolation breach, cross-tenant leak, or dead weight). Read the reason "
            "before assuming this is a fix:"
        )
        for m in dangerous:
            print(f"  - {m}\n      {DO_NOT_ADD[m]}")

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
