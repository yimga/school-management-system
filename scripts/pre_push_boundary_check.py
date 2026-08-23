#!/usr/bin/env python3
"""Local pre-push mirror of the fast, deps-free architectural-boundary gates.

Why this exists
---------------
`architectural-boundaries.yml` only triggers on ``pull_request`` (plus manual
``workflow_dispatch``), so a commit pushed straight to ``main`` never runs the
boundary gates — redness lands on the default branch and is only discovered
later, when some unrelated PR finally runs the workflow. On this repository a
required-status-check (GitHub branch protection) is not available (private repo
on the free plan), so the only enforcement lever left is *local*: run the gates
before the push leaves the machine.

This runner shells out to the exact same CSS/template zero-tolerance gates the
CI job runs, with the exact same flags, so a green run here means a green
`architectural-boundaries` job there. It intentionally covers ONLY the
stdlib-only gates (no Django import), which is both the fast subset and the
subset that catches the CSS/template redness that has repeatedly shipped to
``main`` (undefined CSS classes, off-token colours, theme-locked text, inline
styles, render safety, attribute-context includes, service-worker monotonicity).

Behaviour
---------
* Default is ENFORCING (since 2026-08-21): a failed gate exits non-zero, so
  `git push` aborts. It was warn-only until then, on the reasoning that a shared
  clone should never wedge a teammate mid-push -- but that reasoning assumed
  something downstream would catch what slipped through, and nothing does.
  Branch protection is unavailable on this plan, and GitHub Actions has started
  no job since 2026-08-15 (each run is created and refused for budget, so the
  workflows report red without executing). This hook is the whole chain.
* WARN-ONLY (``--warn-only`` or env ``RMC_PREPUSH_STRICT=0``) reports and exits 0.
  Still one env var away, deliberately -- the point is not to make the override
  hard, it is to make it a decision someone made rather than the silent default.
* A gate that TIMES OUT is reported as a resource result, not a finding. The
  ceiling is ``RMC_PREPUSH_GATE_TIMEOUT_S`` (default 600s), generous because
  several agents share this machine and a squeezed ceiling manufactures failures.

Usage
-----
    python scripts/pre_push_boundary_check.py              # enforcing (default)
    python scripts/pre_push_boundary_check.py --warn-only  # report, exit 0
    RMC_PREPUSH_STRICT=0 git push                          # override via env
    RMC_PREPUSH_GATE_TIMEOUT_S=1200 git push               # slow/busy machine
    python scripts/pre_push_boundary_check.py --list       # show the gate list
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Repo root = parent of this file's directory (scripts/), so the runner works
# regardless of the caller's cwd (a git hook runs from the worktree root, but a
# developer may invoke it from anywhere).
REPO_ROOT = Path(__file__).resolve().parent.parent

# (label, argv) — argv mirrors the CI step invocation that owns each gate, so a
# green run here means a green job there. Most are
# .github/workflows/architectural-boundaries.yml stdlib-only jobs; keep those in
# sync byte-for-byte. Where a gate's home is a DIFFERENT workflow, the entry says
# so, because a reader syncing this list against one workflow would otherwise
# delete it as foreign.
GATES: list[tuple[str, list[str]]] = [
    # First: a module that does not compile cannot be imported at all, and every
    # gate below it is answering about a tree that does not run.
    ("python-files-parse", ["verify_python_files_parse.py"]),
    # Cheap, stdlib-only, and it answers a question no other gate asks: is the OTA
    # pipeline still CONNECTED? A cut wire here ships a green tree that upgrades nobody.
    ("ota-pipeline-wiring", ["verify_ota_pipeline_wiring.py"]),
    # The admin-surface family. Every one of these was written as a pass/fail gate,
    # passes on the current tree, and runs in under a second -- and until 2026-08-21
    # not one was invoked by any workflow or by this runner, so nothing distinguished
    # 'this area is covered' from 'nobody has looked'. Four SIBLINGS of these are
    # deliberately absent because they are currently RED (they pin an exact
    # service-worker version and cache-bust string from
    # var/admin-approval-build-lock.json that peer waves have moved past) and two more
    # hang; see docs/CSS_RETIREMENT_DOCKET.md.
    ("admin-canvas-contract", ["audit_django_admin_canvas_contract.py"]),
    ("admin-surface-leftovers", ["audit_django_admin_surface_leftovers.py"]),
    ("admin-os-empty-space", ["verify_admin_os_empty_space.py"]),
    ("admin-os-sections-restore", ["verify_admin_os_sections_restore.py"]),
    ("admin-os-three-click-sla", ["verify_admin_os_three_click_sla.py"]),
    ("admin-production-upgrade", ["verify_admin_production_upgrade.py"]),
    ("admin-replacement-roadmap", ["verify_admin_replacement_roadmap.py"]),
    ("admin-super-help-nav-bridge", ["verify_admin_super_help_nav_bridge.py"]),
    ("operator-admin-sidebar-v2", ["verify_operator_admin_sidebar_v2.py"]),
    ("tenant-admin-sidebar-v2", ["verify_tenant_admin_sidebar_v2.py"]),
    # Red until 2026-08-21, and red for a reason that made them unwireable: they
    # asserted an EXACT service-worker version from var/admin-approval-build-lock.json
    # while the deploy checklist bumps CACHE_VERSION every wave. Now monotonic.
    ("admin-miss-nothing", ["audit_django_admin_miss_nothing.py"]),
    ("admin-platformwide-sweep", ["sweep_django_admin_platformwide_layout.py"]),
    ("admin-change-form-product-links", ["verify_admin_tenant_change_form_product_links.py"]),
    # Its sibling, and for a worse failure mode: a JavaScript file that does not parse
    # fails SILENTLY in the browser - the tag 200s, the console throws, and the page
    # renders normally with one feature dead. Skipped (not failed) when Node is absent,
    # so a Python-only environment is not blocked by a toolchain it does not have.
    ("javascript-files-parse", ["verify_javascript_files_parse.py"]),
    # And the third: markup that does not close. Quieter than either of the above,
    # because it does not fail anywhere - the page 200s and the browser silently
    # reparents everything after the unclosed element. Nine served templates were
    # found this way on 2026-08-20, one of them shipping a </motion> end tag.
    ("template-html-structure", ["verify_template_html_structure.py"]),
    # And the fourth floor gate, for code that parses, imports, and never runs.
    # EdgeAutosyncMiddleware was defined, correct, and referenced NOWHERE but its own
    # class statement — written to keep a LAN box syncing when nothing pings /health/,
    # and never added to MIDDLEWARE, so the box it existed for never synced. Nothing
    # else can see this: it imports cleanly and has no unused-import warning.
    ("unregistered-middleware", ["scan_unregistered_middleware.py", "--strict"]),
    ("undefined-css-classes", ["scan_undefined_css_classes.py", "--compare"]),
    ("off-token-colors", ["scan_off_token_colors.py", "--strict"]),
    ("theme-locked-token-text", ["scan_theme_locked_token_text.py", "--strict"]),
    ("inline-style-off-token", ["scan_inline_style_off_token.py", "--compare"]),
    # M9 CSP enforce seal: no inline on*= event handlers in served (non-admin)
    # templates — a strict script-src (no 'unsafe-inline') blocks them.
    ("inline-event-handlers", ["scan_inline_event_handlers.py", "--compare"]),
    ("template-render-safety", ["audit_template_render_safety.py", "--compare"]),
    ("attribute-context-includes", ["scan_attribute_context_includes.py"]),
    # {% include with x|default:missing_var %} → VariableDoesNotExist 500 (ops_surface class).
    # |default:missing_var anywhere (not only {% include with %}) → VariableDoesNotExist 500.
    # Static-only completion proof (full Django rows run in ci.yml).
    ("include-with-default-context-var", ["scan_include_with_default_context_var.py", "--strict"]),
    ("eager-filter-arg-completion-static", ["verify_eager_filter_arg_completion.py", "--static-only"]),
    ("nav-engine-coverage-static", ["verify_nav_engine_coverage.py", "--static-only"]),
    ("report-entity-coverage", ["verify_report_entity_coverage.py"]),
    ("service-worker-version", ["verify_service_worker_version.py", "--check-monotonic"]),
    # Approval HTML → live admin: fails if build lock / visible chip / grid drift.
    # Prevents another "CSS-only commit looks unchanged after deploy" silent miss.
    ("django-admin-preview-parity", ["verify_django_admin_preview_parity.py"]),
    # Freeze the set of direct request.FILES intake sites that skip the shared
    # upload validator (apps.security.upload_validation). Enforced here — the
    # real gate on direct pushes — and mirrored as the architectural-boundaries
    # `upload-validation-coverage` job for pull_request runs.
    ("upload-validation-coverage", ["scan_upload_validation_coverage.py", "--compare"]),
    # "6 access requests awaiting approval" with no link. An attention row must
    # carry the page that RESOLVES it, or say why it has none. Runs WITHOUT
    # --compare on purpose: the class is at zero, so there is no baseline to hide
    # behind and the very next dead end blocks the push.
    ("actionless-attention-surfaces", ["scan_actionless_attention_surfaces.py"]),
    # A Migration Cloud lander must KEEP the row it rejected and declare WHY.
    # You cannot replay a row you did not keep, so this is the prerequisite for
    # every automated-remediation step in the zero-touch spec. Zero-tolerance and
    # deliberately WITHOUT --compare: there is no baseline to hide behind, and the
    # next lander that throws a row away blocks the push.
    ("lander-row-error-contract", ["scan_lander_row_error_contract.py", "--strict"]),
    # Non-streaming landers freeze rows_processed during long DB writes and trip
    # SystemicStallError on edge boxes. Zero-tolerance: stream canonical_rows or
    # carry lander-stream-allow + maybe_stall_pulse in post-buffer loops.
    ("lander-row-streaming", ["scan_lander_row_streaming.py", "--strict"]),
    # Row pulses → LoopWatchdog, tier-scaled timeout, lander pulse hook, repair reclaim.
    ("migration-apply-stall-contract", ["verify_migration_apply_stall_contract.py"]),
    # A theme whose surfaces come from a different palette than its ground renders the
    # wrong hue on every card, alert, dropdown and form control it touches -- and the
    # contrast gates stay green while it does, because the pair that shipped measured
    # 6.95:1. Zero-tolerance and without --compare: there is no baseline to hide behind.
    ("theme-hue-coherence", ["scan_theme_hue_coherence.py", "--strict"]),
    # "Exact next confirmations: funding_type, learner_scale, connectivity,
    # operating_model" -- a banner promising exactness and handing over dict
    # keys. `|cut:"_"` DELETES the separator, so the same page said
    # "Inputcompleteness" and the tenant lifecycle strip said "dailyoperations".
    # Zero-tolerance and WITHOUT --compare: there is no input for which cutting
    # a word separator out of a token is the right answer.
    ("raw-token-in-ui", ["scan_raw_token_in_ui.py", "--strict"]),
    # A repeated key in a dict literal is not an error and not a warning -- Python
    # keeps the last value and the earlier entry is simply gone. It cost a workflow
    # definition its steps and a gate two of its markers, one of which was already
    # failing. Zero-tolerance and WITHOUT --compare: there is no baseline, because
    # a dict that discards one of its own entries is never what was meant.
    ("duplicate-dict-keys", ["scan_duplicate_dict_keys.py", "--strict"]),
    # --- RLS: the two halves that `rls-table-coverage` does NOT cover ---------
    # scan_rls_table_coverage (DJANGO_GATES, below) catches a NEW tenant-scoped
    # table with no RLS at all. It says nothing about whether the RLS that exists
    # actually binds. These two close that, and both were sitting in scripts/
    # wired to NOTHING -- not this runner, not any of the 64 workflows -- while
    # the property they protect is the isolation mechanism on every sovereign
    # edge box (USE_DJANGO_TENANTS=0 + RLS).
    #
    # FORCE matters because PostgreSQL exempts a table's OWNER from its own row
    # policies unless FORCE ROW LEVEL SECURITY is set -- and Django connects AS
    # the owner. Without FORCE the policies are decorative on the one connection
    # that matters. Both gates run clean today (force: 0 gaps; policy: every
    # enable_rls_postgresql migration has its matching default-deny), so wiring
    # them costs nothing now and locks the property from here on.
    ("rls-force-coverage", ["scan_rls_force_coverage.py", "--compare"]),
    # No --compare: this one is a structural pairing check with nothing to
    # baseline. A bare run is the gate; --update-baseline is what rewrites, and
    # is deliberately not passed here.
    ("rls-policy-coverage", ["scan_rls_policy_coverage.py"]),
    # `school` inside defaults= instead of the lookup of get_or_create /
    # update_or_create. Those calls match on their DIRECT kwargs; `defaults` is
    # only what gets written once the lookup has already chosen a row. So on a
    # model carrying `school` in a uniqueness key, the lookup matches ANOTHER
    # school's row -- and update_or_create then overwrites that row and
    # re-parents it by writing `school` from defaults. Silent cross-tenant
    # corruption, no exception, no log line.
    #
    # Shipped four times against metadata.DynamicFieldValue
    # (unique_together = [school, entity_type, entity_id, field_key], SHARED app,
    # so one public table holds every tenant's rows): importing one tenant's
    # custom fields could overwrite and steal another tenant's. Baselined rather
    # than zero-tolerance because 19 further call sites need per-case judgement
    # about whether their model is genuinely per-school; --compare blocks NEW ones.
    ("school-in-defaults-not-lookup", ["scan_school_in_defaults_not_lookup.py", "--compare"]),

    # The three below were deploy-gate-only until 2026-08-22. Every gate that
    # halted a full pre_deploy_gate.sh sweep that day was missing from this list,
    # and two of them existed in no workflow at all -- so the enforcement was one
    # person choosing to run a 40-minute script. Added on measurement, not
    # instinct: 1s + 3s + 6s against a hook that already runs 45 gates.
    # verify_i18n_catalog_fresh is deliberately NOT here -- it costs ~7 min.
    #
    # A page that extends control_plane_base and joins neither PHASE7 nor the
    # exempt set. Mirrors architectural-boundaries `control-plane-registry-drift`.
    ("control-plane-registry-drift", ["verify_control_plane_hub_registry_drift.py"]),
    # A broad `except Exception` swallows the failure it was not written for.
    # One around edge-TLS would have settled a box on plain HTTP in silence, and
    # `off` is also the legitimate default, so nothing would have looked wrong.
    # Mirrors architectural-boundaries `broad-except-baseline`.
    ("broad-except-baseline", ["lint_broad_except.py", "--allowlist", "scripts/allowlists/broad_except_allowlist.json", "--strict"]),
    # Pilot-school references outside their classified buckets. HOME IS
    # smoke-light.yml, not architectural-boundaries -- do not delete this entry
    # when syncing against that workflow.
    ("gilead-tree-classification", ["verify_gilead_full_tree_classification.py"]),
]

# Gates that CANNOT answer without the live Django app registry, and are therefore not
# part of the deps-free contract above. They run only when Django imports, and report
# SKIP (never PASS) when it does not.
#
# WHY THEY ARE HERE AT ALL, given this runner exists to mirror the deps-free CI job:
# these gates live in `ci.yml::django-tests`, and GitHub Actions has run NO jobs on this
# repository since 2026-08-15 (billing). So "it is covered in CI" is currently false for
# every one of them, and this runner is the only thing standing between a red gate and
# `main`. That is not hypothetical -- `scan_rls_table_coverage` is a ZERO-baseline gate
# that went red the moment PR #184 merged (three tenant-scoped pairing tables enumerated
# in no enable_rls migration) and stayed red on main until someone ran it by hand.
#
# Kept deliberately short. Each entry pays ~8s for django.setup(), so this list earns its
# place one gate at a time: zero-tolerance, security-relevant, and invisible to every
# stdlib gate above.
DJANGO_GATES: list[tuple[str, list[str]]] = [
    ("rls-table-coverage", ["scan_rls_table_coverage.py", "--compare"]),
    # TenantAdminSite.register auto-scopes a changelist only when the model has a
    # concrete `school` field -- that column is what the mixin filters on. A
    # SHARED_APPS model WITHOUT one got no scoping at all, and its table lives in
    # `public`, which a tenant-schema request's search_path includes. 53
    # registrations were in that state: one school's admin could read and export
    # every tenant's AuditLog / AccessLog / UserActivitySession, and could mutate
    # the platform-global ThreatDetectionConfig / IPAccessRule / CountryAccessRule
    # perimeter. Zero-baseline; the fail-closed arm in config/admin.py means a red
    # gate here is an unmade decision, never live exposure.
    ("unscoped-shared-tenant-admin", ["scan_unscoped_shared_tenant_admin.py"]),
    # Zero-baseline: a view that cannot accept its own URL kwargs is a certain 500,
    # and it is invisible to every stdlib gate because the URL resolves fine.
    ("url-kwarg-contract", ["audit_url_kwarg_contract.py"]),
    # Zero-baseline on UNGUARDED tags only. Guarded ones are counted, not failed --
    # a gate that reports 53 tags when 47 are already safe gets switched off, and
    # then the six real ones ride back in.
    ("shell-url-namespace-contract", ["audit_shell_url_namespace_contract.py"]),
    # Structural floor only: how many models a resolver or builder can reach.
    # The headline coverage numbers depend on the database and are deliberately
    # NOT ratcheted -- see the script's docstring.
    (
        "admin-autofill-coverage",
        [
            "audit_admin_autofill_coverage.py",
            "--compare",
            "var/admin-autofill-coverage-baseline.json",
            "--top",
            "0",
        ],
    ),
]

# Per-gate wall-clock ceiling, overridable with RMC_PREPUSH_GATE_TIMEOUT_S.
#
# Generous ON PURPOSE. Several agents share this machine, and the widest gates walk
# ~8,600 Python files or ~1,900 templates; while a peer is replaying migrations they
# take minutes. A timeout is reported as FAIL, which is INDISTINGUISHABLE from a real
# finding at a glance -- on 2026-08-21 `python-files-parse` "failed" here at 120s while
# being completely clean (8,617 files checked, 0 findings, exit 0 when run directly).
# A ceiling short enough to manufacture failures teaches people to ignore red, and under
# --strict it would block correct pushes outright. Prefer waiting to guessing.
_PER_GATE_TIMEOUT_S = int(  # magic-number-allow: pre-push per-gate wall-clock ceiling (seconds)
    os.environ.get("RMC_PREPUSH_GATE_TIMEOUT_S") or 600
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


# Exit code a gate uses to say "my toolchain is not installed here, so I did not run".
# Distinct from pass and from fail: reporting SKIP is honest, while reporting PASS would
# be a gate that silently stops gating, and reporting FAIL would block every developer
# who does not have that toolchain.
_SKIPPED_EXIT_CODE = 2


def _run_gate(label: str, argv: list[str]) -> tuple[bool | None, str]:
    """Run one gate; return ``(passed, captured_output)``.

    ``passed`` is ``None`` when the gate reported that it could not run at all.
    """
    script = REPO_ROOT / "scripts" / argv[0]
    if not script.is_file():
        # A missing gate script must not silently pass — report it as a failure
        # so the drift is visible, but the caller decides whether it blocks.
        return False, f"gate script not found: {script}"
    cmd = [sys.executable, str(script), *argv[1:]]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_PER_GATE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        # Say what this IS, because a bare "FAIL" here reads as a finding and is not one.
        return False, (
            f"gate TIMED OUT after {_PER_GATE_TIMEOUT_S}s -- this is a RESOURCE result, "
            f"not a finding. The gate did not reach a verdict, so nothing here says your "
            f"tree is dirty. Re-run it alone for a real answer:\n"
            f"    python scripts/{argv[0]} {' '.join(argv[1:])}\n"
            f"If the machine is simply busy (peers running tests), raise the ceiling with "
            f"RMC_PREPUSH_GATE_TIMEOUT_S=<seconds>."
        )
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == _SKIPPED_EXIT_CODE:
        return None, output.strip()
    return proc.returncode == 0, output.strip()


def _django_available() -> bool:
    """Can a subprocess import Django and load settings? Probed once, cheaply."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_PER_GATE_TIMEOUT_S,
            env={**os.environ, "DJANGO_SETTINGS_MODULE": os.environ.get(
                "DJANGO_SETTINGS_MODULE", "config.settings"
            )},
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def _tail(text: str, lines: int = 15) -> str:
    rows = [r for r in text.splitlines() if r.strip()]
    return "\n".join(rows[-lines:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any gate fails. This is now the DEFAULT; kept so existing "
             "callers and hooks that pass it keep working.",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Report failures but exit 0 (also via RMC_PREPUSH_STRICT=0). Use when you "
             "need to push past a gate you have already understood.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the gate list and exit.",
    )
    args, _ignored = parser.parse_known_args(argv)

    if args.list:
        print("Pre-push boundary gates (mirror of architectural-boundaries.yml):")
        for label, gate_argv in GATES:
            print(f"  - {label}: python scripts/{' '.join(gate_argv)}")
        for label, gate_argv in DJANGO_GATES:
            print(f"  - {label}: python scripts/{' '.join(gate_argv)}  [needs Django]")
        return 0

    # ENFORCING BY DEFAULT since 2026-08-21.
    #
    # This hook is not one layer of several -- it is currently the ONLY thing that gates a
    # push. Branch protection is unavailable on this plan (see CLAUDE.md), and GitHub
    # Actions has started no job since 2026-08-15: every run is created and immediately
    # refused with "The job was not started because an Actions budget is preventing
    # further use", so the workflows report red without ever executing. Warn-only on top
    # of that meant nothing, anywhere, enforced anything -- a red gate reached `main` and
    # no later stage would catch it.
    #
    # Opting out is still one env var, deliberately: the ceiling is now 600s so a busy
    # machine no longer manufactures failures (see _PER_GATE_TIMEOUT_S), which is what
    # made warn-only defensible before. The difference is that skipping a red gate is now
    # an act someone chose and can be seen in a shell history, not the silent default.
    _strict_env = (os.environ.get("RMC_PREPUSH_STRICT") or "").strip()
    if args.warn_only:
        strict = False
    elif _strict_env:
        strict = _truthy(_strict_env)
    else:
        strict = True

    print("Pre-push boundary gates (deps-free subset of CI, plus Django-only gates)...")
    failures: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for label, gate_argv in GATES:
        passed, output = _run_gate(label, gate_argv)
        if passed is None:
            # Said so out loud rather than counted as green: a gate that cannot run is
            # not a gate that passed, and hiding that is how coverage quietly evaporates.
            print(f"  SKIP  {label}")
            skipped.append((label, output))
        elif passed:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}")
            failures.append((label, output))

    if DJANGO_GATES:
        if _django_available():
            for label, gate_argv in DJANGO_GATES:
                passed, output = _run_gate(label, gate_argv)
                if passed is None:
                    print(f"  SKIP  {label}")
                    skipped.append((label, output))
                elif passed:
                    print(f"  PASS  {label}")
                else:
                    print(f"  FAIL  {label}")
                    failures.append((label, output))
        else:
            for label, _argv in DJANGO_GATES:
                print(f"  SKIP  {label}")
                skipped.append((label, "Django could not be imported in this environment"))

    for label, output in skipped:
        print("")
        print(f"  -- {label} did NOT run --")
        for row in _tail(output, 3).splitlines():
            print(f"    {row}")

    if not failures:
        print("All boundary gates green - safe to push.")
        return 0

    print("")
    print(f"{len(failures)} boundary gate(s) FAILED:")
    for label, output in failures:
        print(f"\n  -- {label} --")
        tail = _tail(output)
        for row in tail.splitlines():
            print(f"    {row}")

    print("")
    if strict:
        print(
            "Push ABORTED (gates are enforcing by default).\n"
            "  A gate that TIMED OUT is a resource result, not a finding -- re-run that one\n"
            "  alone, or raise RMC_PREPUSH_GATE_TIMEOUT_S, rather than overriding.\n"
            "  To push anyway once you have understood the failure:\n"
            "      RMC_PREPUSH_STRICT=0 git push        (or: --warn-only)\n"
            "  Nothing downstream will catch this for you: branch protection is unavailable\n"
            "  on this plan and Actions has run no job since 2026-08-15.",
        )
        return 1

    print(
        "WARN-ONLY (override in effect): push NOT blocked.\n"
        "  You asked for this explicitly, so the gate above is yours to own -- and it is\n"
        "  the last check in the chain. Actions has started no job since 2026-08-15, so\n"
        "  no CI run will re-report it after you push.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
