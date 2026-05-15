# docs/archive/legacy_2026_05_14/

Archived 2026-05-14 as part of the doc-graveyard sweep. Files in this directory
were identified by:

1. Walking `docs/*.md` for filenames matching `*_COMPLETE.md`, `*_CLOSURE.md`,
   `*_CLOSEOUT.md`, `STEP_*.md`, `WAVE*.md`, `WEEK*.md` patterns (one-shot
   work-completion records).
2. Running `grep -rln` across `apps/`, `config/`, `scripts/`, `templates/`,
   `docs/` to count external references to each candidate.
3. Archiving only the files with **zero external references** — i.e. nothing
   else linked to them. The contents remain readable here; nothing was deleted.

## Files moved this pass (initial 5, NS-1)

| File | External refs at archive time | Reason |
|---|---|---|
| `AUTOMATION_IMPLEMENTATION_COMPLETE.md` | 0 | One-shot wave-closure record |
| `OPTION_D_IMPLEMENTATION_COMPLETE.md` | 0 | One-shot decision-path closure |
| `OPTIONAL_FUTURE_WORK_POOL_CLOSURE.md` | 0 | One-shot backlog closure |
| `REAL_WORLD_SCENARIOS_OPTIONAL_STEPS_COMPLETE.md` | 0 | One-shot closure |
| `STEP_I.md` | 0 | One-shot single-step note |

## Files moved in wave NS-3 (2026-05-14)

Another zero-reference pass picked up 28 more one-shot closure /
phase-checklist documents. Same criteria: matched a one-shot pattern
(`*_COMPLETE.md`, `*_CLOSURE.md`, `STEP_*.md`, `WAVE_*.md`, `PHASE_*.md`,
`PASS_*.md`) AND had zero inbound references anywhere in `apps/`,
`config/`, `scripts/`, `templates/`, or other `docs/*.md`.

| File | Pattern | Reason |
|---|---|---|
| `OPTIONAL_IMPROVEMENTS_COMPLETED.md` | `_COMPLETE` | Wave-closure record |
| `PHASE_1_2_2_RANKING.md` | `PHASE_*` | Sub-phase completion report |
| `PHASE_1_2_6_TRANSLATIONS_GUIDE.md` | `PHASE_*` | Sub-phase translation guide |
| `PHASE_1_2_9_ANALYTICS_DASHBOARDS.md` | `PHASE_*` | Sub-phase analytics closure |
| `PHASE_1_2_ANALYSIS.md` | `PHASE_*` | Phase 1.2 plan |
| `PHASE_10_11_RUNMYCAMPUS.md` | `PHASE_*` | Phase 10–11 delivery memo |
| `PHASE_8_INDEX.md` | `PHASE_*` | Phase 8 index |
| `PHASE_COMPLIANCE_CHECKLIST.md` | `PHASE_*` | Compliance plan 3.9 |
| `PHASE_E_CHECKLIST_POLISH.md` | `PHASE_*` | Polish checklist |
| `PHASE_F_CHECKLIST_POLISH.md` | `PHASE_*` | Polish checklist |
| `PHASE_F_PARENT_PORTAL.md` | `PHASE_*` | Parent portal plan |
| `PHASE_G_CHECKLIST_POLISH.md` | `PHASE_*` | Polish checklist |
| `PHASE_H_CHECKLIST_POLISH.md` | `PHASE_*` | Polish checklist |
| `PHASE_H_MANUAL_PASS_CHECKLIST.md` | `PHASE_*` | Manual QA checklist |
| `PHASE_I_CHECKLIST_POLISH.md` | `PHASE_*` | Polish checklist |
| `POWERHOUSE_PHASE_DOC_A_B_SUMMARY.md` | `PHASE_*` | Powerhouse phase summary |
| `PREMIUM_UX_MANUAL_PASS_BR13.md` | `PHASE_*` | Manual pass record |
| `RUNMYCAMPUS_AUDIT_PLAN_COMPLETE_NO_BACKLOG.md` | `_COMPLETE` | Audit closure |
| `RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md` | `_COMPLETE` | Single-plan closure |
| `S2E_ROWS_6_7_8_13_CLOSURE.md` | `_CLOSURE` | §2e rows closure |
| `STRATEGY_REPORT_GAP_CLOSURE.md` | `_CLOSURE` | Strategy gap closure |
| `SWEEP_VERIFICATION_COMPLETE.md` | `_COMPLETE` | Sweep verification |
| `THEME_COLOR_FIX_STEP_PLAN.md` | `_COMPLETE` | Theme-color step plan |
| `WAVE_4_TASKS.md` | `WAVE_*` | Wave 4 tasks |
| `WAVE_5_SCHEDULING_SOW.md` | `WAVE_*` | Wave 5 scheduling SOW |
| `WAVE_6_LESSON_STANDARDS.md` | `WAVE_*` | Wave 6 standards |
| `WAVE_EXECUTION_RUNBOOKS.md` | `WAVE_*` | Wave 1–8 runbooks |
| `WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md` | `_COMPLETE` | Backlog snapshot |

## Files moved in wave NS-7 / v2.16 (2026-05-14)

The third graveyard pass took a content-driven approach (not just reference
counting): files were grouped by **era** rather than filename pattern.
Two stale eras account for the whole batch — anything that referenced
the moved files was either auto-generated (`docs/generated/*.json`) or
itself another stale planning doc.

**Era A — single-tenant Buea / Cameroon / GileadTech-High** (8 files).
The platform pivoted to multi-tenant SaaS in early 2026; these are
single-tenant operating manuals from the prior era.

| File | Reason |
|---|---|
| `BUEA_SEED_FEATURE_CONFIRMATION.md` | Single-tenant Buea feature signoff |
| `BUEA_SMS_GUIDELINE_AUDIT.md` | Buea SMS UX audit |
| `CAMEROON_BUEA_SETUP_GUIDE.md` | Single-tenant deployment guide (links rerouted in `AUTOMATION_QUICK_REFERENCE.md`, `REGION_AND_LOCALIZATION.md`) |
| `CAMEROON_PLAN_STATUS_AUDIT.md` | Single-tenant plan status |
| `COMPREHENSIVE_TEST_PLAN_BUEA.md` | Buea-specific QA plan |
| `GILEADTECH_STAFF_ORG_ID_PLAN.md` | First tenant org-ID plan |
| `ROLLOVER_COMPARISON_BUEA.md` | Buea-specific year-rollover comparison |
| `SMS_BUEA_SECURITY_AND_READABILITY.md` | Buea-specific UX/security audit |

**Era B — superseded admin / theme / dashboard planning** (27 files).
Apple-tier theme system v2 (NS-2 → v2.0 wave) and the design-tokens.css
canonical foundation supersede every one of these planning docs. The
canonical theme docs (`THEME_CANONICAL_TOKENS.md`, `THEME_COMPONENT_KITS.md`,
`THEME_JSON_SCHEMA.md`) stay in `docs/`.

| File | Reason |
|---|---|
| `ADMIN_BLACK_THEME.md` | Pre-v2 admin theme exploration |
| `ADMIN_DASHBOARD_CHANGE_PLAN.md` | Pre-v2 admin dashboard plan |
| `ADMIN_FORMS_AND_CHILD_MENUS_THEME_PLAN.md` | Pre-v2 admin forms theme plan |
| `ADMIN_PRE_BUILD_CHECKLIST.md` | Pre-v2 admin checklist |
| `ADMIN_SIDEBAR_RESTRUCTURE_PLAN.md` | Pre-v2 admin sidebar plan |
| `ADMIN_UI_THEME_AND_LAYOUT_AUDIT.md` | Pre-v2 admin UI audit |
| `ADMIN_UNFOLD_SPEC_ALIGNMENT.md` | Pre-v2 Unfold alignment plan |
| `ADMIN_UX_FIXES_AND_IMPROVEMENTS_PLAN.md` | Pre-v2 admin UX fixes plan |
| `ADMIN_VS_BACKEND_GAP_ANALYSIS.md` | Pre-v2 admin/backend gap analysis |
| `COLOR_PICKER_AND_HARMONY_INTEGRATION_PLAN.md` | Pre-v2 color picker plan |
| `DASHBOARD_AND_ADMIN_MASTER_PLAN.md` | Pre-v2 master plan |
| `DASHBOARD_CLEAN_CLASSY_PLAN.md` | Pre-v2 clean/classy dashboard plan |
| `DASHBOARD_CONSOLIDATION_PLAN.md` | Pre-v2 dashboard consolidation plan |
| `DASHBOARD_THEME_MASTER_PLAN.md` | Pre-v2 dashboard theme plan |
| `MASTER_PLAN_THEME_AND_DASHBOARD.md` | Pre-v2 master theme plan |
| `OPTIMIZATION_PLAN_RESPONSIVE_AND_THEME.md` | Pre-v2 responsive theme plan |
| `OPTIMIZATION_PLAN_RESPONSIVE_PERF_THEME.md` | Pre-v2 responsive perf theme plan |
| `SITE_SETTINGS_UX_AND_THEME_FINDINGS.md` | Pre-v2 settings UX findings |
| `THEME_AND_COLOR_GAPS_DETAILED_AUDIT.md` | Pre-v2 color-gap audit |
| `THEME_AND_CONFIG_MASTER_PLAN.md` | Pre-v2 theme/config master plan |
| `THEME_AND_SITE_CONTROL_PLAN.md` | Pre-v2 theme + site control plan |
| `THEME_COLOR_STYLE_ASSESSMENT.md` | Pre-v2 theme/color assessment |
| `THEME_CONSOLIDATION_AND_IMPROVEMENTS.md` | Pre-v2 theme consolidation plan |
| `THEME_EXPERIENCE_COMBINED_PAGE_PLAN.md` | Pre-v2 combined-page experience plan |
| `THEME_OPTIONS_REVISITED.md` | Pre-v2 theme-options revisit memo |
| `THEME_VISIBILITY_CODEBASE_PLAN.md` | Pre-v2 codebase visibility plan |
| `THEMEPACK_AND_PLATFORM_REVAMP_PLAN.md` | Pre-v2 theme-pack revamp plan |

Net wave NS-7: **+35 files archived** (34 → 69 total in this dir).
`docs/*.md` count: 687 → 652.

## Files moved in wave NS-9 / v2.17 (2026-05-14)

Three eras retired in one combined pass — same content-driven approach as NS-7.

**Era C — "improvements" / "implementation summary" closure docs** (12 files).
Long tail of "we did improvements" wave-closure records from prior development cycles. Superseded by the wave-by-wave docket pattern (`CSS_RETIREMENT_DOCKET.md`) plus the COVERAGE_AUDIT / SEED_EXPANSION SOTs.

| File | Reason |
|---|---|
| `BUILD_IMPROVEMENTS_IMPLEMENTATION.md` | One-shot improvements implementation log |
| `FIXES_IMPLEMENTATION_SUMMARY.md` | One-shot fix summary |
| `GAME_PLAN_PLATFORM_AUDIT_AND_IMPROVEMENTS.md` | One-shot game plan |
| `IMPLEMENTATION_COMPLETE.md` | One-shot completion record (link rerouted in `DOCS_TRUTH_AUDIT.md`) |
| `IMPROVEMENTS_BEFORE_AUTOMATION.md` | One-shot improvements plan |
| `IMPROVEMENTS_DATA_AGNOSTIC.md` | One-shot improvements plan |
| `IMPROVEMENTS_EXECUTABLE_PLAN.md` | One-shot improvements plan |
| `IMPROVEMENTS_IMPLEMENTED.md` | One-shot improvements log |
| `IMPROVEMENTS_PART_B_PLAN.md` | One-shot improvements plan part B |
| `IMPROVEMENT_TO_MAIN_DEPLOY_READINESS.md` | One-shot deploy-readiness checklist |
| `OTHER_FORESEEABLE_IMPROVEMENTS.md` | One-shot speculative improvements list |
| `PLATFORM_ASSESSMENT_AND_IMPROVEMENT_PLAN.md` | One-shot assessment + plan |

**Era D — commit / merge / render one-shot planning** (5 files).
URL-mapping plans, merge checklists, and commit-readiness optimizations from one-time deploy events. Operational runbooks (`FRESH_DB_FIX.md`, `RENDER_DATABASE_URL_FIX.md`, `RENDER_MAKEMIGRATIONS.md`, `DATABASE_RECOVERY_GUIDE.md`) intentionally **stayed** in `docs/` — they're reference for real failure modes, not historical events.

| File | Reason |
|---|---|
| `COMMIT_AND_MAIN_CHECKLIST.md` | One-shot pre-commit checklist |
| `COMMIT_READY_OPTIMIZATION.md` | One-shot commit-prep memo |
| `MERGE_IMPROVEMENTS_TO_MAIN.md` | One-shot merge plan |
| `RENDER_PRODUCTION_URL_PLAN.md` | One-shot URL plan |
| `RENDER_URL_MAPPING_PLAN.md` | One-shot URL mapping plan |

**Era E — Phase-X completion logs that survived waves 1+2** (13 files).
Sub-phase completion records and roadmaps that had inbound refs at the time of wave 1+2 (which used a strict zero-reference rule), but the refs are themselves either auto-generated, already archived, or in other stale planning docs.

| File | Reason |
|---|---|
| `PHASE_1_1_OPTIMIZATION.md` | Sub-phase optimization plan |
| `PHASE_1_2_4_INTERNATIONALIZATION.md` | Sub-phase i18n plan |
| `PHASE_1_2_5_ADMIN_GUIDE.md` | Sub-phase admin guide |
| `PHASE_1_2_7_REPORT_LOCALIZATION.md` | Sub-phase localization plan |
| `PHASE_1_2_8_COMPLIANCE_LEGAL.md` | Sub-phase compliance plan |
| `PHASE7_NICE_TO_HAVE_ROADMAP.md` | Phase 7 nice-to-have roadmap |
| `PHASE_7_COMPLETION.md` | Phase 7 completion record |
| `PHASE_7_TASKS_6_9.md` | Phase 7 sub-tasks |
| `PHASE_8_COMPLETION.md` | Phase 8 completion record |
| `PHASE_9_COMPLETION.md` | Phase 9 completion record |
| `PHASE_9_ROADMAP.md` | Phase 9 roadmap |
| `PHASE_D_E_QUICK_REFERENCE.md` | Phase D/E quick ref |
| `PHASE_H_THEME_GALLERY.md` | Phase H theme gallery memo |

Net wave NS-9: **+30 files archived** (69 → 99 total in this dir).
`docs/*.md` count: 652 → 622.

## Files moved in wave NS-13 (2026-05-15)

Fifth doc-graveyard pass, three content-driven eras (F/G/H). Same rule
as waves NS-8/NS-9: read the file's first ~20 lines to confirm era +
relevance; cross-ref-grep the codebase before moving; reroute every
inbound reference (production code first, then docs).

**Era F — WORKFLOW_* planning docs that the current shipped workflow packs supersede** (2 files).
The user-facing `WORKFLOW_COMMUNICATION/FINANCE/GCE/MARKS_ENTRY/REPORT_CARDS/STUDENT_ONBOARDING/TEACHER_ONBOARDING/YEAR_ROLLOVER/YEAR_SETUP.md` how-tos stay — they are referenced from `AUTOMATION_QUICK_REFERENCE.md` and `FAQS_COMPREHENSIVE.md` and remain accurate. Only the two **planning** memos (dated 2026-01-28, written before NS-4 expanded the in-code workflow pack registry to 56 packs) move.

| File | Reason |
|---|---|
| `WORKFLOW_IMPROVEMENTS.md` | 2026-01-28 backlog of "future" workflow-center improvements; superseded by shipped admin/teacher/parent workflow centers + 56 workflow packs in `apps/automation/` |
| `WORKFLOW_IMPROVEMENT_PLAN.md` | 2026-01-28 single-tenant Cameroon/Buea-aligned planning doc; same era as NS-8 wave 3 archives |

**Era G — DATA_* one-shot policy/fix docs** (4 files).
Phase 1.2/1.3/1.4 sub-policy fixes that the parent `PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md` (marked **100% complete**, 2025-02-02) referenced. The DATA_RESIDENCY_AND_COMPLIANCE.md doc stays — it is a load-bearing compliance reference, not a one-shot fix log.

| File | Reason | Reroute |
|---|---|---|
| `DATA_INVOICE_BALANCE.md` | Phase 1.4 closure note for `Invoice.reconcile_balance()`; plan is 100% complete | None (0 inbound refs) |
| `DATA_PARENT_CONTACT.md` | Phase 1.2 single-source-of-truth policy for guardian contact | `apps/finance/tasks.py:591`, `apps/people/signals.py:161`, `docs/NOTIFICATIONS_FINANCE_PHASE2_4.md:31` all updated to point at archive path |
| `DATA_PAYMENT_REFERENCE.md` | Phase 1.3 semantics doc for `Payment.reference`/`external_reference` | `apps/finance/models.py:743,760` help_text updated to archive path; `apps/finance/migrations/0033_*.py` deliberately **not** modified (migrations are immutable historical record) |
| `DATA_VISUALIZATION_IMPROVEMENT_PLAN.md` | Planning memo for charts on Finance/Payroll/Analytics/EMIS/etc. dashboards; charts since shipped | None (0 inbound refs) |

**Era H — pre-multi-tenant verification docs** (2 files).
The current SaaS multi-tenant state-of-play lives in `MULTI_TENANT_GLOBAL_ROADMAP.md` (canonical), `STATE_OF_PLATFORM_2026_05_14.md`, `MULTI_TENANT_ISOLATION.md`, `MULTI_TENANT_ADMIN_AND_URLS.md`, `MULTI_TENANT_CREATE_NEW_SITE.md`, and `QUICK_REFERENCE_MULTI_TENANT.md` — all stay. Only the two superseded artifacts move:

| File | Reason | Reroute |
|---|---|---|
| `MULTI_TENANT_VERIFICATION_AND_IMPROVEMENTS.md` | Phase-era audit checklist; superseded by `STATE_OF_PLATFORM_2026_05_14.md` + `MULTI_TENANT_GLOBAL_ROADMAP.md` | `docs/MULTI_TENANT_CREATE_NEW_SITE.md:68` rerouted to point at archive path + current SOTs |
| `MULTI_SCHOOL_ADD_NEW_SCHOOL.md` | "Option A: same server, separate DB per school" — predates the current single-DB + tenant FK SaaS model | `docs/REGION_AND_LOCALIZATION.md:88` + `docs/REGION_AND_PLAN_IMPROVEMENTS_CHECKLIST.md:22` both rerouted to archive path (REGION_AND_LOCALIZATION.md also annotated with pointer to the current `MULTI_TENANT_CREATE_NEW_SITE.md`) |

Net wave NS-13: **+8 files archived** (99 → 107 total in this dir).
`docs/*.md` count: 623 → 615.

**Cumulative across waves NS-1, NS-3, NS-8, NS-9, NS-13: 106 docs archived** (5 + 28 + 35 + 30 + 8).

**Why only 8 this wave (target was ~25):** content-driven discipline. The three target eras (F/G/H) yielded a smaller candidate pool than wave NS-9 once the load-bearing how-tos (9 generic `WORKFLOW_*.md` user guides) and the canonical living docs (`MULTI_TENANT_GLOBAL_ROADMAP.md`, `MULTI_TENANT_ISOLATION.md`, `DATA_RESIDENCY_AND_COMPLIANCE.md`, `SINGLE_TENANT_PRODUCTION.md`, `GILEAD_RESIDUE.md`, `GILEAD_REFERENCE_CLASSIFICATION.md`) were correctly excluded. Padding to 25 would have either archived live docs or pulled in out-of-era candidates (AUDIT_*, PASS_*, etc.) better handled in a later wave with a different rubric.

## What stays in `docs/` after this sweep

The remaining 700+ docs split roughly into:

- **Canonical living docs** (must stay current): `SECURITY.md`, `OBSERVABILITY.md`,
  `COMPETITIVE_PARITY_ROADMAP.md`, `NORTH_STAR_PLATFORM.md`,
  `MULTI_TENANT_GLOBAL_ROADMAP.md`, `ECOSYSTEM_STRATEGY.md`,
  `CSS_RETIREMENT_DOCKET.md`, `STATE_OF_PLAY.md`, `ACCESS_POINTS.md`,
  `AGENTS.md`, `bounded_context_ownership.md`, `STATE_OF_PLATFORM_2026_05_14.md`,
  `BOUNDED_CONTEXT_AUDIT_2026_05_14.md`, `CONTRAST_AUDIT_2026_05_14.md`,
  `PENTEST_SOW_2026_05_14.md`, `ML_AT_RISK_TRAINING.md`,
  `AI_MEDIA_GENERATION_PIPELINE_2026_05_14.md`.
- **Domain reference docs** (load-bearing for one bounded context):
  `BILLING_*.md`, `MIGRATION_*.md`, `AI_*.md`, `ADMIN_*.md`, `RLS_*.md`, etc.
- **Audit / plan / closure docs that are still cross-referenced** —
  *most* of the remainder. Triage of these belongs to a multi-day
  consolidation wave, not this single session.

## Recommended next sweep

The bigger graveyard cleanup needs file-by-file content review (not just
reference counting). Suggested approach for a future session:

1. For each `docs/*.md` with ≤ 3 external references, run a content-only
   check: is this a "what we did in 2025" historical doc, or a "how things
   currently work" reference doc?
2. Historical → archive. Reference → keep + flag for index.
3. Build a new `docs/README.md` table of contents with the canonical list.
4. Delete-after-archive (or move to git-LFS) when the archive grows beyond ~200 files.

Estimated effort for the full sweep: 1 working day for one engineer.
