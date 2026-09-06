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
    # Added 2026-09-06. TransactionTestCase truncates every table at teardown
    # and does not roll it back, so with --keepdb the emptied seed catalog is
    # PERSISTED into later runs: unrelated suites answer 403 and look like
    # permission regressions in code that is fine. The 2026-09-03 audit closed
    # 32 of 33 classes and told the survivor to be 'ordered last' -- advice
    # pytest cannot honour, since it runs in collection order. There were 15
    # again by 2026-09-06. The flush and the failure need not even be in the
    # same run, so nothing short of a gate catches the sixteenth.
    ("scripts/scan_unrestored_flush_testcase.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. Both wizard gates below existed, were correct, and were
    # invoked by NOTHING -- verify_unified_wizard_framework.py was even named in
    # this workflow's `paths:` filter, which triggers the job without running the
    # gate. The spec-coverage one had been reporting 14 registered wizards missing
    # from the Playwright spec into a log no run ever produced.
    ("scripts/verify_wizard_playwright_spec_coverage.py", "architectural-boundaries.yml"),
    ("scripts/verify_unified_wizard_framework.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. The four companion-* siblings are separate programs that
    # talk to this server over HTTP, and nothing ever checked that the paths they
    # hardcode exist. A resolve of every literal against all four urlconfs returned
    # 404 for every one -- including /api/v1/auth/login/, so the shipped desktop app
    # cannot complete step 1 of its own documented flow. Every client failure is
    # silent by construction (best-effort fetches, `if (resp.ok)`), so only a gate
    # can see it.
    ("scripts/verify_companion_server_contract.py", "ci.yml"),
    # Added 2026-09-02. Run by nothing since it was written: absent from every
    # workflow, from pre_push_boundary_check and from the test suite, while the
    # execution log recorded a May hand-run of it as evidence the surface was OK.
    ("scripts/verify_operator_siteconfig_cp_shell.py", "ci.yml"),
    # Added 2026-08-31. The marketing axe ratchet reports zero for two very
    # different reasons -- the surface is clean, or the sweep is not looking at
    # it -- and in CI those are indistinguishable. This coverage gate asserts
    # the sweep's page list still covers every path the two marketing specs
    # cover, that its baseline exists and is well-formed, and that a workflow
    # actually invokes it.
    ("scripts/verify_marketing_axe_ratchet_coverage.py", "architectural-boundaries.yml"),
    # Added 2026-08-22: a repeated key in a dict literal is silently collapsed by
    # Python -- last value wins, the earlier entry simply is not there. The
    # workflow registry declared parent-portal-pay-all twice and the surviving copy
    # was a paste of the neighbouring pay-invoice entry, so the workflow resolved
    # with NO steps and the single-invoice help article. verify_ux_completion
    # declared one template twice, and the shadowed entry's markers -- one of which
    # had genuinely regressed out of the template -- were never checked at all.
    ("scripts/scan_duplicate_dict_keys.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. The pre-import guard on an edge appliance reads a TABLE of
    # what each lander writes (it cannot AST-parse 35 modules before every apply, on
    # a box that may be a Raspberry Pi). A table that stops matching the code turns
    # the guard into a confident lie: a lander gains a model, the model is on no
    # rail, and the operator is told the import is clean. This gate re-resolves the
    # landers and fails on any difference in either direction.
    ("scripts/audit_lander_write_reachability.py", "ci.yml"),
    ("scripts/scan_ci_shell_command_integrity.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. A step ending in `|| true` / `|| echo` / carrying
    # continue-on-error cannot report a failure, so every gate inside it is
    # decorative. This gate is exactly the kind that gets quietly unwired,
    # because unwiring it makes nothing go red.
    ("scripts/scan_workflow_swallowed_exit_codes.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. Its own tracked artifact is what made the case: a
    # "finding_count": 0 over 1086 templates, dated 2026-05-19, while the tree
    # held 1910 -- a clean bill of health over 824 templates it had never seen.
    # An unwired reporter rots silently and is then read as a fact, so the
    # invocation itself is the thing that has to be defended.
    ("scripts/audit_no_placeholder.py", "architectural-boundaries.yml"),
    ("scripts/scan_admin_registered_on_unmounted_site.py", "architectural-boundaries.yml"),
    # Added 2026-08-27, detector integrity. These three were each green for a
    # reason unrelated to the tree being clean, which is the worst state a gate
    # can be in: a green light nobody re-checks.
    #
    # A ratchet's promise is kept by a baseline file. Delete it and most
    # scanners here do not fail -- they fall through to their "write the
    # baseline" branch, author one from what they happen to find, and exit 0.
    # scan_rls_table_coverage had exactly that shape; this is the general form.
    ("scripts/verify_ratchet_baselines_present.py", "architectural-boundaries.yml"),
    # The old matcher tested the last two names of the attribute chain, so it
    # only matched a bare AuditLog.objects.update() -- not valid Django, and not
    # what anyone writes. The real filter(...).update() in compliance/privacy.py
    # never matched, so the gate could only ever print PASS.
    ("scripts/verify_audit_log_append_only.py", "architectural-boundaries.yml"),
    # Its file matcher only opened files whose NAME said sms (one module, which
    # holds none), it enforced only under --strict, and it was wired to nothing.
    ("scripts/scan_sms_template_length.py", "architectural-boundaries.yml"),
    # Wired 2026-08-27. 436 of 809 guard scripts were invoked by no runner at
    # all. Most are one-shot wave-closeout scripts and wiring them wholesale
    # would bury the real ones, so they were triaged by evidence -- named in
    # CLAUDE.md, has a test, has a baseline -- rather than by filename. These
    # three are standing contracts that pass today.
    ("scripts/scan_undefined_color_token_fallback.py", "architectural-boundaries.yml"),
    ("scripts/verify_render_online_ai_posture.py", "architectural-boundaries.yml"),
    ("scripts/verify_tenant_scoping_burndown.py", "architectural-boundaries.yml"),
    # Narrow by construction (a hand-maintained pin on four money mutators), but
    # four enforced invariants beat zero and nothing invoked it before.
    ("scripts/verify_finance_payment_atomicity.py", "architectural-boundaries.yml"),
    # Added 2026-08-23: a merge that adds a migration to an app another branch also
    # touched produces two leaf nodes, and Django then refuses to migrate that app.
    # git reports a clean merge; the failure is in a graph no diff shows.
    ("scripts/verify_single_migration_leaf.py", "ci.yml"),
    # Added 2026-08-23: blank=True + unique=True on a text field means optional exactly
    # once, because blank stores "" and only one row may hold it under a unique index.
    # School.subdomain and three KB slugs were all live defects of this shape.
    ("scripts/scan_blank_unique_text_fields.py", "ci.yml"),
    # The floor: a module that does not compile cannot be imported at all, and every
    # other gate is then answering about a tree that does not run. Added 2026-08-19 after
    # apps/accounts/tasks.py was found TRUNCATED mid-statement on main - the reference
    # gates treat an unparseable file as opaque and skip it, so nothing reported it.
    ("scripts/verify_python_files_parse.py", "architectural-boundaries.yml"),
    # Added 2026-08-22: `include(..., {"shell": "super"})` injects a kwarg into every
    # view in the included module, and 31 views did not accept it -- 124 routes across the
    # operator AND tenant hosts were a guaranteed TypeError 500. The URL resolved, the view
    # existed, the permission passed; only calling it failed, so no route-name gate saw it.
    ("scripts/audit_url_kwarg_contract.py", "ci.yml"),
    # Added 2026-08-22: TenantAdminSite.register auto-scopes a changelist only when
    # the model has a concrete `school` field -- that column is what the mixin filters
    # on. A SHARED_APPS model WITHOUT one got no scoping at all, and its table lives in
    # `public`, which a tenant-schema request's search_path includes. 53 registrations
    # were in that state, so one school's admin could read, filter and CSV-export every
    # tenant's AuditLog / AccessLog / UserActivitySession, and mutate the platform-global
    # ThreatDetectionConfig / IPAccessRule / CountryAccessRule perimeter. The mixin was
    # working exactly as designed; it simply had nothing to filter on and said so to
    # nobody.
    ("scripts/scan_unscoped_shared_tenant_admin.py", "ci.yml"),
    # Added 2026-08-22: portal_base.html renders on the tenant host AND the operator
    # host, and its closing chrome included a bare {% url 'portal:support_quick_create' %}.
    # portal: is tenant-only, so seven /super/migration/connectors/* routes 500'd AFTER
    # the body had rendered. verify_url_name_integrity was green throughout, because the
    # name reverses -- just not on that host.
    ("scripts/audit_shell_url_namespace_contract.py", "ci.yml"),
    # Its sibling, and the half audit_shell_url_namespace_contract cannot reach:
    # that gate walks six DECLARED shells through LITERAL {% include %} edges, so a
    # control-plane body arriving via {% include operator_cp_body_template %} -- a
    # VARIABLE include -- is invisible to it, and its SHELL_HOSTS deliberately omits
    # config.urls. Both holes were live on 2026-08-31:
    # accounts/partials/operator_documentation_body.html reversed the manager-only
    # name `manager_help_center` with no namespace at all, and
    # use_control_plane_shell() serves that body on a `local` host too, so
    # /authentication/documentation/ was a 500 on every dev machine. Wired into
    # architectural-boundaries.yml the same day: its only previous home was
    # ci.yml, which has started no job since 2026-08-15.
    ("scripts/verify_cross_host_template_reverse.py", "architectural-boundaries.yml"),
    # Added 2026-08-21: `ink` and `midnight` both paired a navy ground with the WARM
    # surface ramp belonging to `steel`, so every form control on those themes rendered
    # brown inside a navy shell. Every contrast gate was green throughout -- the defect
    # is hue, and nothing asked that question until this gate.
    ("scripts/scan_theme_hue_coherence.py", "architectural-boundaries.yml"),
    # The floor for code that compiles, imports, and still never runs. Added 2026-08-20:
    # EdgeAutosyncMiddleware existed to keep a LAN box syncing when nothing pings
    # /health/, was never added to MIDDLEWARE, and so was dead during the exact failure
    # it was written for. Registration is invisible to every other gate.
    ("scripts/scan_unregistered_middleware.py", "architectural-boundaries.yml"),
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
    # The literal-path twin of the url-name gate: reverse() cannot see a path
    # written as a string, and a local dev host mounts config.urls (the full
    # surface) while a real tenant gets config.tenant_urls, so a dead path is
    # invisible until production. Added 2026-08-20 after six always-rendered
    # Action Hub chips were found 404ing on every tenant portal page.
    ("scripts/scan_hardcoded_dead_paths.py", "ci.yml"),
    # A permission code gated on but never seeded denies EVERYONE, permanently
    # and silently — has_feature_permission on an unknown code just returns
    # False. Added 2026-08-20 after six such codes were found, including the
    # pair guarding mobile offline grade/attendance sync for every teacher.
    ("scripts/scan_rbac_permission_catalog.py", "ci.yml"),
    # Added 2026-08-21. Its sibling audit_admin_form_intelligence_contract.py proves
    # the field classification is complete and disjoint, and can be perfectly green
    # while every add form on the platform is still an empty grid -- it never counts
    # how much a person has to type. This one does, and freezes the structural floor
    # so a deleted resolver or a shrunken INITIAL_BUILDERS cannot pass quietly.
    ("scripts/audit_admin_autofill_coverage.py", "ci.yml"),
    # Added 2026-08-21. These ten already existed as pass/fail gates and were
    # invoked by NOTHING -- not a workflow, not the pre-push runner. Registering
    # them here is what stops them drifting back out of CI unnoticed, which is the
    # exact failure this meta-gate was built for.
    ("scripts/audit_django_admin_canvas_contract.py", "architectural-boundaries.yml"),
    ("scripts/audit_django_admin_surface_leftovers.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_os_empty_space.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_os_sections_restore.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_os_three_click_sla.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_production_upgrade.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_replacement_roadmap.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_super_help_nav_bridge.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_sidebar_v3.py", "architectural-boundaries.yml"),
    # Added 2026-08-21 after being fixed rather than excused. Three of these
    # pinned an exact service-worker version and so reddened on every wave by
    # construction; one was missing the product escape link its 33 sibling
    # change_form templates all carry.
    ("scripts/audit_django_admin_miss_nothing.py", "architectural-boundaries.yml"),
    ("scripts/sweep_django_admin_platformwide_layout.py", "architectural-boundaries.yml"),
    ("scripts/verify_admin_tenant_change_form_product_links.py", "architectural-boundaries.yml"),
    ("scripts/audit_admin_usage_extended.py", "architectural-boundaries.yml"),
    ("scripts/audit_admin_gravity.py", "architectural-boundaries.yml"),
    ("scripts/audit_admin_os_cross_wave.py", "architectural-boundaries.yml"),
    # A bundle runner (15 sub-checks, ~8 min) so it has its own job and its own
    # timeout. Recorded as hanging before 2026-08-21; it was red on the same exact
    # service-worker pin as its siblings, reached through audit_django_admin_miss_nothing.
    ("scripts/verify_admin_manager_shell_aggressive.py", "architectural-boundaries.yml"),
    ("scripts/audit_admin_emergency_surface_contract.py", "ci.yml"),
    ("scripts/verify_django_admin_canvas_templates_compile.py", "ci.yml"),
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
    # Hand-built JSON islands must escape their interpolations. Silent console.warn
    # failure mode, locale-dependent, invisible to every status-code sweep.
    ("scripts/scan_json_island_escaping.py", "architectural-boundaries.yml"),
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
    # Added 2026-09-02: Gilead-class ingest gaps were first-class surfaces drifting
    # apart (ontology/lander/UI/sync), not missing dynamic fields.
    ("scripts/verify_tier1_academic_people_platform_contract.py", "architectural-boundaries.yml"),
    ("scripts/verify_global_country_ingestion_coverage.py", "architectural-boundaries.yml"),
    ("scripts/verify_ingestion_lexicon_offline_wiring.py", "architectural-boundaries.yml"),
    ("scripts/verify_global_local_first_ingestion_chain.py", "ci.yml"),
    ("scripts/verify_global_platform_country_readiness.py", "ci.yml"),
    ("scripts/verify_report_entity_coverage.py", "architectural-boundaries.yml"),
    # A Migration Cloud lander must keep the row it rejected and declare why.
    # Added 2026-08-21: 29 of 35 lander files threw the offending row away, which
    # makes automated remediation impossible BY CONSTRUCTION — you cannot replay a
    # row you did not keep. Every later step of the zero-touch spec depends on it.
    ("scripts/scan_lander_row_error_contract.py", "architectural-boundaries.yml"),
    # A banner promising "Exact next confirmations" printed four dict keys.
    # Added 2026-08-22 after the same `|cut:"_"` mistake was found on three
    # surfaces, one of them on every page of a live tenant.
    ("scripts/scan_raw_token_in_ui.py", "architectural-boundaries.yml"),
    # Operator workbench landings must show page header before optional cockpit chrome.
    # Added 2026-08-22 after founder + CS dashboards stacked collapsable widgets above
    # "Platform Command Center" / "Benchmark & Customer Success".
    ("scripts/verify_operator_landing_header_order.py", "architectural-boundaries.yml"),
    # Landers must not buffer list(canonical_rows) without an allow marker — frozen
    # rows_processed trips SystemicStallError on large edge applies.
    ("scripts/scan_lander_row_streaming.py", "architectural-boundaries.yml"),
    ("scripts/verify_migration_apply_stall_contract.py", "architectural-boundaries.yml"),
    # Money never float; tenant rows always scoped; offline label has code.
    ("scripts/scan_wallpaper_status_badges.py", "architectural-boundaries.yml"),
    ("scripts/verify_page_masthead_twin_contract.py", "architectural-boundaries.yml"),
    ("scripts/verify_band_count_fold_sla.py", "architectural-boundaries.yml"),
    ("scripts/scan_visibility_anti_bleed.py", "architectural-boundaries.yml"),
    ("scripts/scan_money_float.py", "architectural-boundaries.yml"),
    ("scripts/scan_tenant_queryset_safety.py", "tenant-isolation-scan.yml"),
    # Added 2026-09-02. Stdlib-only (ast + pathlib), so it rides the deps-free
    # boundary workflow rather than ci.yml::django-tests.
    ("scripts/scan_test_host_fidelity.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. Stdlib-only (re + pathlib), so it rides the deps-free
    # boundary workflow rather than ci.yml::django-tests.
    ("scripts/scan_dangling_static_reference.py", "architectural-boundaries.yml"),
    # Added 2026-09-02. Rewritten the same day to stop pinning a frozen June
    # service-worker literal -- which made it go red on EVERY cache bump and kept
    # it red for three months -- and to assert instead that the shipped cache
    # generation still covers the wave the stylesheet declares. Before this entry
    # the only file in the repository that named it was itself.
    ("scripts/verify_theme_experience_dual_plane_shell.py", "architectural-boundaries.yml"),
    # Added 2026-09-03. Zero hits across every workflow, the pre-push hook,
    # this registry, the mutation registry and package.json -- while
    # verify_help_center_tiers listed it as evidence for a tier by asserting
    # the file exists.
    ("scripts/verify_platform_back_to_top.py", "architectural-boundaries.yml"),
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
    ("scripts/scan_rls_relation_scoped_coverage.py", "ci.yml"),
    ("scripts/scan_rls_null_school_arm.py", "ci.yml"),
    # Django admin approval HTML → live shell lock (2026-07-20). Prevents shipping
    # layout waves that pass narrative audits but leave tenant/operator /admin/
    # looking unchanged (missing build chip / cache bust / approval grid).
    ("scripts/verify_django_admin_preview_parity.py", "architectural-boundaries.yml"),
    # The dynamic sibling: resolves add/change forms for every registration on both
    # real AdminSite instances and proves field classification, ownership binding,
    # evidence immutability, and optional-field preference metadata stay complete.
    ("scripts/audit_admin_form_intelligence_contract.py", "ci.yml"),
    # The cascading-OTA pipeline can be fully present and deliver nothing: every wire
    # in it (operator manifest build, box manifest build, box apply step, mounted
    # routes, cloud-pinned paths) fails SILENTLY when cut, because nothing is broken —
    # the code is simply never reached. Same class as scan_unregistered_middleware.
    ("scripts/verify_ota_pipeline_wiring.py", "architectural-boundaries.yml"),
    # Added 2026-08-31. Needs the live Django app registry (it resolves the rail
    # registry out of apps.api.sync_services), so it rides ci.yml::django-tests
    # rather than the deps-free boundary workflow.
    ("scripts/audit_rail_coverage.py", "ci.yml"),
    # Added 2026-09-03. Ten child checks behind one gate that nothing ran, so
    # every one of them was dark. It stayed unrunnable because its
    # large_collection child could only pass at zero findings while the detector
    # under it was crediting a section-navigator attribute as a row bound.
    ("scripts/verify_cp_v8_operator_closeout.py", "architectural-boundaries.yml"),
)


def _run_step_text(source: str) -> str:
    """Every `run:` body in one workflow file.

    Deliberately NOT the whole file. A script path listed under
    ``on.pull_request.paths`` only decides WHEN the workflow runs -- it never
    causes the gate to execute -- yet a whole-file substring search counts it as
    wired. That was proven by mutation: deleting the run step for
    scan_duplicate_dict_keys.py left this gate green because the path entry
    remained. Matching run bodies only is what makes the assertion true.

    Stdlib line scanner rather than a YAML parse, because this gate runs in the
    deps-free boundary job and must not import PyYAML. It is biased toward being
    GENEROUS -- an unrecognised shape yields the whole file rather than an
    accusation, since a false 'un-wired' report would send someone re-wiring a
    gate that is already wired.
    """
    lines = source.splitlines()
    bodies: list[str] = []
    index = 0
    saw_run = False
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "run:" or stripped.startswith("run: "):
            saw_run = True
            remainder = stripped[len("run:"):].strip()
            indent = len(line) - len(line.lstrip())
            if remainder and remainder[0] not in "|>":
                bodies.append(remainder)  # inline: `run: python x.py`
            index += 1
            # Block scalar: consume blank lines and anything indented deeper.
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    index += 1
                    continue
                if len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                bodies.append(nxt)
                index += 1
            continue
        index += 1
    if not saw_run:
        return source  # unrecognised shape -- never accuse
    return "\n".join(bodies)


def _workflow_text() -> str:
    """Concatenated `run:` bodies of every workflow (forward-slashed)."""
    if not WORKFLOWS_DIR.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml")):
        try:
            chunks.append(_run_step_text(path.read_text(encoding="utf-8")))
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
