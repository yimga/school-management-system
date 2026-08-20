#!/usr/bin/env python
"""Meta-gate: assert every critical CI gate stays WIRED into a workflow.

The architectural CI gates protect the code — but nothing protected the
*gates themselves* from being silently un-enforced. A peer edit to
``.github/workflows/ci.yml`` once dropped the ``verify_url_name_integrity``
step entirely: the verifier still existed, its baseline still said 0, its
tests still passed — but it no longer RAN on any PR, so a new
``NoReverseMatch`` could ship uncaught. That regression is invisible to every
other gate (they check code, not whether they're invoked).

This guard closes that meta-loophole. It holds a SOT registry of the gates
that MUST run on every PR and asserts each one's ``scripts/<gate>.py``
invocation appears in at least one workflow file under ``.github/workflows/``.
A gate missing from every workflow is a finding (exit 1).

Deliberately a pure-text scan (no YAML parse, no Django) so it runs in the
deps-free ``architectural-boundaries.yml`` boundary job alongside the static
scanners it protects. "Wired in ANY workflow" is the right contract — a gate
may legitimately move between workflow files, but it must never vanish from
all of them. Removing a gate on purpose is a reviewed change to
``REQUIRED_GATES`` here, which is exactly the audit trail we want.

Pass/fail gate (no finding-count baseline), like ``verify_slo_registry``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# SOT: gates that MUST be invoked on every PR. Each entry is the scanner's
# script path (the substring searched for in workflow files) + the workflow
# it is expected to live in (documentation / diagnostic only — the assertion
# is "present in SOME workflow"). Removing a gate from CI is a reviewed edit
# to this tuple.
REQUIRED_GATES: tuple[tuple[str, str], ...] = (
    # The floor: a module that does not compile cannot be imported at all, and every
    # other gate is then answering about a tree that does not run. Added 2026-08-19 after
    # apps/accounts/tasks.py was found TRUNCATED mid-statement on main - the reference
    # gates treat an unparseable file as opaque and skip it, so nothing reported it.
    ("scripts/verify_python_files_parse.py", "architectural-boundaries.yml"),
    # The same floor for the code that runs in the BROWSER. Added 2026-08-20: the Python
    # gate's own write-up named this hole and stopped there. A JavaScript SyntaxError is
    # quieter than a Python one - no server log, no Sentry event, just a feature that
    # does not work - and in static/js/service-worker.js it silently stops the offline
    # shell an appliance depends on from ever updating.
    ("scripts/verify_javascript_files_parse.py", "architectural-boundaries.yml"),
    # The same floor for MARKUP, and the quietest of the three. An unclosed <div> does
    # not raise, does not log, and does not fail a test: the page 200s and the browser
    # silently reparents everything after it into a container it was never meant to be
    # inside. Added 2026-08-20 after nine served templates were found unbalanced,
    # including one that shipped a </motion> end tag - an element that does not exist.
    ("scripts/verify_template_html_structure.py", "architectural-boundaries.yml"),
    # Reference-integrity family — the "literal string -> runtime registry ->
    # 500/silent" loophole class. All members must always run.
    ("scripts/scan_import_reference_integrity.py", "architectural-boundaries.yml"),
    # i18n: added 2026-07-21. This gate existed and ran on NO workflow, so the
    # 19 highest-traffic UI strings could silently fall back to English in every
    # shipped catalog while nothing noticed.
    ("scripts/verify_critical_msgid_depth.py", "architectural-boundaries.yml"),

    ("scripts/verify_get_model_integrity.py", "ci.yml"),
    ("scripts/verify_url_name_integrity.py", "ci.yml"),
    ("scripts/verify_template_reference_integrity.py", "ci.yml"),
    # Compile sibling of the two template gates above: a balanced-but-invalid
    # tag argument ({% trans 'a'b' %}) compiles-fail without being a missing
    # reference or a structural imbalance, so it slips both. Must always run.
    ("scripts/verify_template_compiles.py", "ci.yml"),
    ("scripts/verify_static_reference_integrity.py", "ci.yml"),
    ("scripts/verify_settings_key_integrity.py", "ci.yml"),
    ("scripts/verify_field_reference_integrity.py", "ci.yml"),
    ("scripts/verify_relation_path_integrity.py", "ci.yml"),
    ("scripts/verify_orm_filter_field_integrity.py", "ci.yml"),
    # Documented-baseline drift meta-check (doc vs JSON).
    ("scripts/check_documented_baselines.py", "architectural-boundaries.yml"),
    # Template render safety + attribute-context layout-frame guard.
    ("scripts/audit_template_render_safety.py", "architectural-boundaries.yml"),
    ("scripts/scan_attribute_context_includes.py", "architectural-boundaries.yml"),
    # M9 CSP enforce seal: no inline on*= event handlers on served (non-admin)
    # templates — strict script-src blocks them, so the enforce flip needs 0.
    ("scripts/scan_inline_event_handlers.py", "architectural-boundaries.yml"),
    # Eager filter-arg VariableDoesNotExist 500 class (ops_surface / slice / add).
    # Static scanner stays deps-free; completion verifier (static-only in boundaries,
    # full Django run in ci.yml) is the only allowed "done" proof.
    ("scripts/scan_include_with_default_context_var.py", "architectural-boundaries.yml"),
    # Full completion (Django sparse renders + regression module) in ci.yml;
    # static-only subset also runs in architectural-boundaries.yml.
    ("scripts/verify_eager_filter_arg_completion.py", "ci.yml"),
    # Platform nav catalog: static projector wiring in architectural-boundaries;
    # full reverse() of spine url_names in ci.yml.
    ("scripts/verify_nav_engine_coverage.py", "architectural-boundaries.yml"),
    # Money never float; tenant rows always scoped; offline label has code.
    ("scripts/scan_wallpaper_status_badges.py", "architectural-boundaries.yml"),
    ("scripts/verify_page_masthead_twin_contract.py", "architectural-boundaries.yml"),
    ("scripts/verify_band_count_fold_sla.py", "architectural-boundaries.yml"),
    ("scripts/scan_visibility_anti_bleed.py", "architectural-boundaries.yml"),
    ("scripts/scan_money_float.py", "architectural-boundaries.yml"),
    ("scripts/scan_tenant_queryset_safety.py", "tenant-isolation-scan.yml"),
    # A SHARED model may never FK a TENANT table. Nothing else can catch it:
    # the Postgres CI job runs USE_DJANGO_TENANTS="0" (one schema, so the FK
    # resolves) and SQLite cannot create tenant schemas — while production runs
    # "1", where `migrate_schemas --shared` dies on any fresh database.
    ("scripts/scan_cross_tenancy_fk.py", "architectural-boundaries.yml"),
    ("scripts/verify_offline_capability_implementation.py", "architectural-boundaries.yml"),
    # Offline manifest taxonomy: the compiled tenant manifest must always carry the
    # operational_context contract keys (operational_state et al.) even when the ops
    # resolver fails. This gate existed but ran on NO workflow (only in a paths:
    # filter), and was RED when executed — wired into ci.yml (needs Django) 2026-08-01.
    ("scripts/verify_offline_manifest_taxonomy.py", "ci.yml"),
    # Tenant-facing money renders the locale currency, never a hardcoded symbol.
    ("scripts/scan_locale_display.py", "architectural-boundaries.yml"),
    # Global academic kernel — the canonical world grade-scale families must
    # stay seeded; without this gate a deploy could ship an empty registry and
    # the catalog's "9 world scales" claim becomes silent theater.
    ("scripts/verify_grading_scale_registry_coverage.py", "ci.yml"),
    # Config SOT (Wave A, target #2) — lock the three-store resolver's invariants
    # so a config field can never silently skip the per-tenant override merge.
    # Owner-map sync is stdlib (architectural-boundaries); live-model parity is
    # Django-aware (ci.yml).
    ("scripts/verify_domain_ownership_exact_storage.py", "architectural-boundaries.yml"),
    ("scripts/verify_runtime_defaults_model_parity.py", "ci.yml"),
    # Tenant lifecycle (Wave C, target #1) — lock the unified-lifecycle FSM so a
    # state can never be added without its transitions/spine mapping (which would
    # silently brick the state or blind the Tenant 360 timeline). Django-aware
    # (spine map values are SchoolLifecycleStage.Stage), so it lives in ci.yml.
    ("scripts/verify_unified_lifecycle_fsm_integrity.py", "ci.yml"),
    # Authorization-consolidation ratchet — the zero-tolerance guarantee that
    # fragmented access checks can only go DOWN is only real while this runs
    # on every PR; without meta-protection a dropped step re-opens silent
    # regrowth (B-validated gap, 2026-07-03).
    ("scripts/scan_access_resolver_fragmentation.py", "architectural-boundaries.yml"),
    # Config-SOT adoption ratchet (2026-07-05) — the read-side twin: the frozen
    # tail of raw get_effective_site_settings / singleton-record reads can only
    # go DOWN, and new code must read through get_effective_config /
    # config_service. Same silent-regrowth risk without meta-protection.
    ("scripts/scan_config_resolver_fragmentation.py", "architectural-boundaries.yml"),
    # Granular-RBAC adoption ratchet (2026-07-05) — coarse admin-tier gates
    # (@tenant_admin_required / permission_required("settings.*")) on tenant
    # operational surfaces (finance/payroll/evals/reports/analytics/compliance)
    # can only go DOWN; a new coarse gate on a delegable surface fails CI. Must run
    # every PR or the "every operational surface is grantable to a non-admin role"
    # guarantee silently regrows.
    ("scripts/scan_granular_rbac_adoption.py", "architectural-boundaries.yml"),
    # Tenant->operator boundary (H1 seal) — no is_staff-only operator gate on a
    # tenant-reachable view. The platform mints is_staff tenant admins, so
    # @staff_member_required is not an operator gate; this must run every PR or a
    # new operator surface can silently land on the tenant host gated only by
    # is_staff (2026-07-05).
    ("scripts/scan_staff_gate_on_tenant_surface.py", "architectural-boundaries.yml"),
    # Tenant->operator boundary (H4 seal, 2026-07-05) — the four axes the isolation
    # audit found ungated: no tenant template links to an operator route; every
    # super: route is covered by the tenant-host guard (end-to-end negative proof);
    # every /super/ view carries a platform-scope decorator; offboarding stays
    # operator-only.
    ("scripts/scan_tenant_template_operator_links.py", "architectural-boundaries.yml"),
    ("scripts/verify_tenant_cannot_reach_operator_routes.py", "ci.yml"),
    ("scripts/verify_super_platform_scope_coverage.py", "ci.yml"),
    ("scripts/verify_tenant_offboarding_operator_only.py", "ci.yml"),
    # H4.7 — the penetration scenario matrix stays fresh (regenerated + committed).
    ("scripts/generate_tenant_isolation_penetration_report.py", "architectural-boundaries.yml"),
    # Migration Cloud lander phantom-field seal (2026-07-09) — a lander must never
    # hand-build a .create/.get_or_create/.update_or_create with a keyword (or a
    # defaults literal key) that is not a real model field; those raise + get
    # swallowed = silent data loss. Zero-tolerance from day 1; must run every PR
    # or the class silently re-opens.
    ("scripts/scan_lander_phantom_fields.py", "architectural-boundaries.yml"),
    # Migration transaction side-effects (2026-07-19) — the deploy-abort seal. A
    # migration that does a DB op inside a broad swallowing except (or any
    # email/network/Celery I/O) can poison the migrate transaction and abort the
    # whole Render deploy (the schools/0078 crash). Zero-tolerance; must run every
    # PR or the class silently re-opens.
    ("scripts/scan_migration_transaction_side_effects.py", "architectural-boundaries.yml"),
    # Metric 24 (Documentation): every installed app has a README whose factual
    # claims are checked against the live app registry. Unwired, per-app docs rot
    # back to nothing -- which is exactly the state this gate was written to end.
    ("scripts/verify_app_readmes.py", "ci.yml"),
    # Table-level RLS coverage. scan_rls_force_coverage answers only "does this
    # app have both RLS migration FILES", which is green even when a table added
    # after the migration's hard-coded TABLES list has no RLS at all. This one
    # answers "is this table actually enumerated", and must stay wired so the
    # uncovered set cannot grow before an RLS-mode flip.
    ("scripts/scan_rls_table_coverage.py", "ci.yml"),
    # Django admin approval HTML → live shell lock (2026-07-20). Prevents shipping
    # layout waves that pass narrative audits but leave tenant/operator /admin/
    # looking unchanged (missing build chip / cache bust / approval grid).
    ("scripts/verify_django_admin_preview_parity.py", "architectural-boundaries.yml"),
)


def _workflow_text() -> str:
    """Concatenated text of every workflow file (forward-slashed for matching)."""
    if not WORKFLOWS_DIR.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml")):
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(chunks).replace("\\", "/")


def find_unwired(required=REQUIRED_GATES) -> list[dict]:
    """Return a finding per required gate whose invocation is in NO workflow."""
    haystack = _workflow_text()
    findings: list[dict] = []
    for script, expected_workflow in required:
        if script not in haystack:
            findings.append({"script": script, "expected_workflow": expected_workflow})
    return findings


def _payload(findings: list[dict]) -> dict:
    return {
        "rule": "every gate in REQUIRED_GATES must be invoked in at least one "
        ".github/workflows/*.yml file (prevents a gate from being silently "
        "un-enforced by an unrelated workflow edit)",
        "required_count": len(REQUIRED_GATES),
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = find_unwired()
    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        f"CI gate wiring: {len(REQUIRED_GATES)} required gate(s) checked, "
        f"{len(findings)} un-wired"
    )
    for f in findings:
        print(
            f"  MISSING: {f['script']} is in NO workflow "
            f"(expected in {f['expected_workflow']}) — gate is no longer enforced"
        )
    if findings:
        print(
            "\nA required gate vanished from every workflow. Re-wire it, or — if "
            "removal is intentional — drop it from REQUIRED_GATES in this script "
            "(a reviewed change)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
