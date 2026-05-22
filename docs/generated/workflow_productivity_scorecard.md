# Workflow Productivity Scorecard

**Phase:** 10 of the RunMyCampus platform-wide workflow audit
**Generated:** 2026-05-22
**Source:** `scripts/` not used (read-only synthesis from `docs/generated/platform_workflow_code_truth_inventory.json` + `docs/generated/workflow_click_reduction_audit.json`)
**Companion JSON:** `docs/generated/workflow_productivity_scorecard.json`

## Method

Every cataloged workflow is scored on 9 dimensions on a 1-5 scale:

| Dimension | What it measures |
|---|---|
| clarity | Is the workflow's purpose obvious? |
| click_efficiency | Does it complete in close-to-ideal clicks? |
| guidance | Is help / how-to / next-action visible? |
| ai_usefulness | Does AI give a specific, route-aware next action? 1 if absent, 5 if exact-next-action with evidence citation. |
| tenant_safety | Is tenant data isolated? Does platform-only stay platform-only? |
| operator_usefulness | Is the operator workflow load-bearing (real next action, blocker visible)? |
| accessibility | Keyboard, screen-reader, contrast (per `scan_color_contrast.py` baseline 0). |
| mobile_readiness | Responsive, no horizontal overflow (per `scan_horizontal_overflow_risk.py` baseline 0). |
| completion_confidence | Does the user actually know when they're done? |

Scoring is **honest**: every score is `measurement_status: hypothesis` unless the workflow already carries a measured marker in the click-reduction audit. Global floors lean on existing scanner baselines (e.g. `scan_tenant_queryset_safety.py` baseline 0 -> tenant-scoped paths default to 4 unless a cross-host gap is visible).

Priority buckets (sum of 9 scores, max 45):

- `p0`: total < 25 (critical, fix-first)
- `p1`: 25 - 29 (high)
- `p2`: 30 - 35 (medium)
- `p3`: 36+ (low / preserve)

## Coverage

- Workflows scored: **73** (target was at least 50)
- Source list: 6 from `workflow_click_reduction_audit.json` + the rest synthesized from `platform_workflow_code_truth_inventory.json` (50 apps, 1909 routes) cross-referenced with `apps_with_apicenter_import`, `apps_with_feedback_import`, `apps_with_help_template`, `likely_workflow_pages`, and recent wave memory (v3.39 / v3.54 / v3.55.x / v3.56 / v3.57.x).

## Score distribution

| Priority bucket | Workflow count | % of total |
|---|---|---|
| p0 (total < 25, critical) | 4 | 5.5% |
| p1 (25-29, high) | 30 | 41.1% |
| p2 (30-35, medium) | 36 | 49.3% |
| p3 (36+, preserve) | 3 | 4.1% |

## Per-dimension averages (out of 5)

| Dimension | Avg | Verdict |
|---|---|---|
| tenant_safety | **4.96** | Strongest pillar. `scan_tenant_queryset_safety.py` + `scan_tenant_isolation_marker_quality.py` baselines 0 platform-wide. |
| click_efficiency | 3.93 | Healthy; cockpit / civic-footer / today-snapshot pulls average up. |
| clarity | 3.81 | Healthy. |
| completion_confidence | 3.56 | OK; weak on log / audit / timeline surfaces where "done" is ambiguous. |
| mobile_readiness | 3.22 | OK floor of 3 from `scan_horizontal_overflow_risk.py` baseline 0 (v3.57.1 burndown). Weak on heatmap / world-map / bulk grid. |
| accessibility | 3.14 | OK floor of 3 from `scan_color_contrast.py` baseline 0. Weak on heatmap / world-map (no data-table fallback). |
| guidance | 3.12 | Weak: most workflows ship without an inline help / how-to drawer. |
| operator_usefulness | 2.30 | Weak. Most tenant workflows are not operator-load-bearing by design (correctly scored low for the operator dimension). |
| **ai_usefulness** | **1.56** | **PLATFORM-WEAKEST**. Most surfaces have no AI rail; the few that do (cockpit copilot rail) ship as stub. |

**Platform-weakest dimension: `ai_usefulness`** (avg 1.56 out of 5).

> Note: `operator_usefulness` averaging 2.30 is partly an artifact of scoring tenant-only workflows against an operator lens (a parent finance statement is correctly not operator-load-bearing). The avg restricted to operator-audience workflows is materially higher.

## Top 10 lowest-scoring workflows (the fix-first list)

| Rank | Workflow ID | Audience | Total | Priority | Recommended first fix |
|---|---|---|---|---|---|
| 1 | orchestration_define_process | tenant_admin | 22 | p0 | Visual workflow builder + AI commentary on missing branches before publish. |
| 2 | marketplace_publisher_signup | tenant_admin | 23 | p0 | Define publisher onboarding wizard with ordered steps + verify ABAC scoping on publisher tenant. |
| 3 | marketplace_app_version_publish | tenant_admin | 23 | p0 | Add SBOM display + signature chip + AI summary of changelog before publish action. |
| 4 | student_passport | tenant_student | 24 | p0 | Define passport workflow purpose + primary action; add help drawer + AI 'what is this' explainer. |
| 5 | report_generation | tenant_admin | 25 | p1 | Collapse analytics + reports split surfaces into one governed report builder with a single primary action. |
| 6 | parent_payment_receipt | tenant_parent | 25 | p1 | Money Center should co-locate invoice + manual fallback + receipt capture; PSP path remains external-blocked but receipt capture is repo-side. |
| 7 | operator_tenant_heatmap | operator | 25 | p1 | Add screen-reader-friendly data table fallback + color-blind-safe palette + tooltip with hashed slug. |
| 8 | operator_world_map | operator | 25 | p1 | Add data-table fallback + region filter chips + AI summary of top-3 active regions. |
| 9 | tenant_activity_timeline | tenant_any | 25 | p1 | Add per-row 'what changed' link + AI rail commentary on the most consequential change. |
| 10 | academics_year_setup | tenant_admin | 25 | p1 | Add ordered checklist with done / pending / blocked pills + clone-from-last-year preset. |

## Top 10 highest-scoring workflows (the preserve list)

| Rank | Workflow ID | Audience | Total | Priority | Why preserve |
|---|---|---|---|---|---|
| 1 | migration_cloud_maa_sign | operator | 37 | p3 | v3.39 platform-trust wave hardened it end-to-end: constant-time SHA match, draft refusal, audit emission. |
| 2 | migration_cloud_health_dashboard | operator | 36 | p3 | v3.38 6-panel staff dashboard with 60s refresh + tenant-id-hashed labels. |
| 3 | tenant_help_drawer | tenant_any | 36 | p3 | v3.57.8 cross-shell close-on-outside-click parity fix landed; load-bearing. |
| 4 | migration_cloud_companion_upload | operator | 35 | p2 | v3.39 auto-fingerprint-verify on every upload + counsel-blessed receipt chain. |
| 5 | tenant_civic_footer | tenant_any | 35 | p2 | v3.55.1 + v3.57.8 4-tier civic layout shipped + cockpit_payload backed. |
| 6 | tenant_workspace_context | tenant_any | 34 | p2 | v3.56 cockpit trifecta wired it into portal_sidebar (desktop + mobile offcanvas). |
| 7 | platform_runtime_impl_command_center | operator | 34 | p2 | Go-live score + ordered blocker queue ship as primary action. |
| 8 | offline_conflict_resolution | operator | 33 | p2 | Click-reduction audit marker `measured_local_route`; 404 -> 1 explanatory action. |
| 9 | tenant_onboarding | operator | 33 | p2 | Implementation Command Center surfaces next blocker as primary chip. |
| 10 | migration_cloud_audit_export | operator | 33 | p2 | v3.38 append-only hash-chain + tri-valued `_root_signature_verified` per JSONL line. |

## "Any-score-below-4 fix list" (repo-side only)

The prompt's directive: **any score below 4 must be fixed if repo-side**. With current thresholds, **71 of 73 workflows** carry at least one dimension below 4 AND are tagged `repo_side_fixable: yes`. Only two workflows are external-blocked enough to ship below 4 without an in-repo fix path:

- `parent_payment_receipt` (PSP / Stripe path is external)
- `accounts_passkey_setup` (browser WebAuthn caps are external)

This signals the platform is mostly at "good across some axes, but always missing one" — the most actionable cross-cutting fix is **AI usefulness wiring** (1.56 avg), followed by **guidance** (3.12 avg).

## Recommended cross-cutting first fixes

1. **AI rail platform-wide**: bind cockpit `ai_copilot_service` stub (currently shipped as v3.57.0 service helper) to `services.ai_helpers` route-aware next-action with evidence citation. Single lift, lifts 60+ workflows.
2. **Inline help drawer adoption**: 19 of 50 apps in the inventory ship workflow templates with no `has_help_template`. Wire the existing tenant_help_drawer pattern (which scored 36) into the remaining workflow shells.
3. **Heatmap / world-map a11y fallback**: data-table fallback grammar + color-blind-safe palette. Two p1 entries (tenant_heatmap, world_map) move from 25 -> 31+ from this alone.

## Honest caveats

- Phase 1 classification matrix (`platform_workflow_classification_matrix.json`) was not present at scoring time; workflow audience labels were inferred from `surfaces` + `reachable_from` in the Phase 0 inventory.
- Phase 5/6/7 gear-up audits (`operator_workflow_gear_up_audit.json` / `tenant_workflow_gear_up_audit.json` / `studio_os_workflow_gear_up_audit.json`) were not present at scoring time; their findings would refine `operator_usefulness` and `completion_confidence` for the 9 operator + 6 studio_os workflows.
- `accessibility` and `mobile_readiness` lean on the two zero-tolerance scanners landed in v3.57.0 (`scan_color_contrast.py` + `scan_horizontal_overflow_risk.py`), both at baseline 0, so the platform floor is 3 unless an obvious gap is visible at the template level. Direct verification would require running the app (not done in this read-only walk).
- Every workflow carries `measurement_status: hypothesis` except `offline_conflict_resolution` which is `measured_local_route`.
- No product code, no migrations, no commits, no SOT updates were made.
