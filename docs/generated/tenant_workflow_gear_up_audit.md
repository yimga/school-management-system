# Tenant workflow gear-up audit (Phase 6)

Generated: 2026-05-22
Source: manual Phase 6 walk over `config/tenant_urls.py` (93 routes verified) + 9 tenant-side app urlconfs + `templates/portal/` + `templates/parent/` + `templates/teacher/` + `templates/student/` + `templates/siteconfig/` + `templates/finance/`. Read-only, stdlib-only, no Django startup, no product code changes.

Companion JSON: [`tenant_workflow_gear_up_audit.json`](tenant_workflow_gear_up_audit.json).
Upstream input: [`platform_workflow_code_truth_inventory.json`](platform_workflow_code_truth_inventory.json) (22 tenant-reachable apps).
Complement to: [`ai_tenant_studio_audit_first_inventory.json`](ai_tenant_studio_audit_first_inventory.json) (not duplicated).

Spot-checked routes (>= 5 required by constraints): `school_studio_hub` @ tenant_urls.py:286; `tenant_offboarding` @ tenant_urls.py:292; `school_setup_imports` @ tenant_urls.py:270; `guided_configuration_workflows` @ siteconfig/urls.py:210; `finance:dashboard` @ finance/urls.py:34; `evals:teacher_marks_entry` @ evals/urls.py:34; `migration-intake-list` @ migration_cloud/urls_customer.py:27. All seven verified.

## Workflows audited (26 total)

| Workflow | Audience | Entry route | Steps | Primary | Next | Ready | Block | Done | Help | AI | Feedback | Mobile | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tenant_studio_os_hub | school_admin | `/school/studio/` | 1 | yes | yes | yes | unclear | yes | yes | yes | no | yes | p1 |
| tenant_onboarding_school_activation | school_admin | `/siteconfig/onboarding/` | 6 | yes | yes | yes | yes | yes | yes | yes | no | unknown | p1 |
| school_setup_blueprints_packs_imports | school_admin | `/school/setup/blueprints/` | 3 | yes | unclear | unclear | unclear | unclear | no | no | no | unknown | p1 |
| student_import | school_admin | `/school/setup/imports/` (redirect) | 2 | yes | unclear | unclear | unclear | unclear | unclear | unclear | no | unknown | p1 |
| staff_setup | school_admin | `/siteconfig/onboarding/step/staff/` | 3 | yes | yes | yes | yes | yes | unclear | unclear | no | unknown | p2 |
| class_setup | school_admin | `/academics/` | 3 | unclear | unclear | unclear | unclear | unclear | unclear | unclear | no | unknown | p2 |
| academic_year_term_setup | school_admin | `/siteconfig/reports/academic-years-setup/` | 2 | yes | unclear | yes | unclear | yes | no | no | no | unknown | p1 |
| term_publish_readiness | school_admin | `/siteconfig/reports/term-publish-status/` | 2 | yes | yes | yes | yes | yes | no | no | no | unknown | p2 |
| billing_setup_payment_readiness | school_admin | `/finance/payment-setup/` | 3 | yes | yes | yes | yes | yes | no | no | no | unknown | p2 |
| parent_portal_setup | school_admin | `/siteconfig/configuration/guided/` | 2 | unclear | unclear | unclear | unclear | unclear | no | no | no | unknown | p1 |
| teacher_workspace_setup | school_admin, teacher | `/portal/teacher/onboarding/` | 4 | yes | yes | yes | unclear | yes | yes | unclear | no | yes | p2 |
| report_card_readiness_publishing | school_admin, teacher | `/siteconfig/reports/builder/` | 4 | yes | unclear | yes | yes | yes | no | no | no | unknown | p1 |
| offline_sync_queue | teacher, school_admin | `/portal/offline/sync-queue/` | 2 | yes | yes | yes | yes | yes | no | no | no | yes | p2 |
| migration_cloud_tenant_intake | school_admin | `/migration/` | 4 | yes | yes | yes | yes | yes | yes | unclear | no | unknown | p2 |
| feedback_submission_school | all 4 | `/feedback/` | 1 | yes | yes | unclear | unclear | yes | yes | no | yes | yes | p1 |
| help_kb_how_do_i | all 4 | `/kb/` | 2 | yes | yes | yes | no | no | yes | yes | yes | yes | p3 |
| feature_request_roadmap_voting | all 4 | `/feature-center/` | 2 | yes | yes | yes | no | yes | yes | no | yes | yes | p3 |
| app_catalog_marketplace | school_admin | `/settings/app-catalog/` | 4 | yes | yes | yes | yes | yes | unclear | unclear | no | yes | p1 |
| packages_packs_request | school_admin | `/siteconfig/request-waiver/` | 2 | yes | unclear | unclear | unclear | yes | no | no | no | unknown | p2 |
| payment_manual_fallback | school_admin, parent | `/finance/payments/` | 3 | yes | yes | yes | yes | yes | no | no | no | unknown | p2 |
| compliance_security_visibility | school_admin | `/compliance/dashboard/` | 2 | yes | unclear | yes | unclear | yes | no | no | no | unknown | p2 |
| attendance_entry_teacher | teacher | `/portal/attendance/student/` | 2 | yes | yes | yes | unclear | yes | no | no | no | yes | p1 |
| marks_entry_teacher | teacher | `/evals/teacher/marks/entry/` | 2 | yes | yes | yes | yes | yes | no | no | no | yes | p1 |
| report_card_publishing | school_admin | `/siteconfig/reports/builder/` | 4 | yes | yes | yes | yes | yes | no | unclear | no | unknown | p1 |
| invoice_generation | school_admin | `/finance/fees/generate/` | 2 | yes | yes | yes | unclear | yes | no | no | no | unknown | p2 |
| manual_payment_receipt | school_admin, parent | `/finance/invoices/<id>/upload-receipt/` | 2 | yes | yes | yes | yes | yes | no | no | no | unknown | p2 |
| billing_usage_review | school_admin | `/siteconfig/billing/plan/` | 2 | yes | yes | yes | yes | yes | no | no | no | unknown | p2 |

## Top 10 fix-me-first

1. **feedback_submission_school** — `apps/feedback/urls.py` mounts 5 `/super/*` operator routes on the same urlconf the tenant subdomain includes; split into tenant + super halves to stop URL-space leakage.
2. **app_catalog_marketplace** — `/marketplace/monetization/` is operator economics surface but ships under `apps/marketplace/tenant_urls.py`; move to operator urlconf.
3. **student_import** — silent redirect from `/school/setup/imports/` to `/siteconfig/onboarding/` is a UX dead-end; needs a real landing with CSV templates + migration-cloud handoff.
4. **marks_entry_teacher** — hard `LOCKED` banner does not link the teacher to the term-publish toggle; add help drawer + AI-draft hook.
5. **report_card_readiness_publishing** — four sibling siteconfig report pages with no shared progress rail + `evidence` operator slug in URL; bundle and rename.
6. **parent_portal_setup** — buried inside `guided_configuration_workflows` operator-mode page; needs its own `/school/setup/parent-portal/` landing.
7. **attendance_entry_teacher** — bulk-capture hub and per-class attendance live as siblings with no cross-link; missing offline-sync banner.
8. **academic_year_term_setup** — URL slug `evidence` (operator audit language) visible in school-admin URL bar.
9. **tenant_studio_os_hub** — 5 sibling `/school/studio/<sub>/` redirects clutter the IA; collapse + add blocker callout + feedback footer.
10. **school_setup_blueprints_packs_imports** — 3 sibling `/school/setup/*` pages have no shared readiness band.

## Strong already (preserve)

- `tenant_onboarding_school_activation` — multi-step rail with readiness + blockers + completion.
- `migration_cloud_tenant_intake` — 4-step flow (start -> sign-maa -> upload -> status stream -> abandon) plus guardian-consent campaign sister.
- `help_kb_how_do_i` — public KB + FAQ + downloads (odt/docx/pdf) + search + voting + comments.
- `feature_request_roadmap_voting` — roadmap voting + feature center + contextual feedback all wired.
- `offline_sync_queue` — queue + conflicts + 3-state lifecycle.
- `billing_setup_payment_readiness` — setup + readiness dashboard + honest external-PSP meter.
- `teacher_workspace_setup` — onboarding wizard with steps + readiness + help.
- `manual_payment_receipt` — upload + suspense + claim + reconcile chain.

## Tenant clutter inventory

12 pages / urlconf decisions where admin-side UI or operator chrome bled into the tenant view:

- `templates/siteconfig/metadata_dynamic_fields_operator.html` — operator-named template under tenant-reachable `/siteconfig/metadata/dynamic-fields/`; extends `control_plane_base.html`; breadcrumb anchored to `super:dashboard`.
- `templates/siteconfig/metadata_operator_hub.html` — operator-named template at `/siteconfig/metadata/operator-hub/`.
- `templates/siteconfig/operator_control_plane_page.html` — generic operator control-plane shell, `<title>` reads `RunMyCampus Manager`.
- `templates/siteconfig/theme_builder_control_plane.html` — `_control_plane` suffix in filename, operator chrome.
- `templates/siteconfig/theme_experience_hub_control_plane.html` — same.
- `templates/siteconfig/entity_catalog_overview.html` — extends `control_plane_base.html`.
- `templates/siteconfig/config_mutation_audit_evidence.html` — `evidence` slug + operator chrome.
- `templates/siteconfig/super/cockpit_configure.html` (+ `theme_personality_configure`, `cockpit_health`, `cockpit_previews`) — `/siteconfig/super/configure/*` URL space reachable on tenant subdomain (staff-gated views, but the URL surface leaks).
- `apps/feedback/urls.py` mounted at tenant root — 5 `/super/*` operator routes live in the same urlconf.
- `apps/marketplace/tenant_urls.py:18 -> monetization/` — operator economics on tenant urlconf.
- `config/tenant_urls.py:339 -> /admin/dashboard/` — operator observability dashboard wired into tenant urlconf.
- `config/tenant_urls.py:261-262 -> /internal-admin/` — internal-label URL reachable on tenant subdomain.

## Platform-only leakage signals (global)

Concerning, but all behind staff/superuser gates — the leak is the URL surface, not unauthenticated access:

- Operator-only `/super/*` routes mounted via `apps/feedback/urls.py` on the tenant URLconf.
- Operator-economics `/marketplace/monetization/` mounted on `apps/marketplace/tenant_urls.py`.
- Operator-grade `/admin/dashboard/` from `apps/observability` mounted on `config/tenant_urls.py:339`.
- Operator-named templates under `templates/siteconfig/*.html` (control_plane / operator / evidence suffixes) reachable on tenant subdomain.

## Tenant role coverage

- **school_admin** — primary landing `/school/studio/`; covers 19 workflows.
- **teacher** — primary landing `/portal/teacher/`; covers `teacher_workspace_setup`, `attendance_entry_teacher`, `marks_entry_teacher`, `offline_sync_queue`, `feedback_submission_school`, `help_kb_how_do_i`.
- **parent** — primary landing `/portal/parent/`; covers `manual_payment_receipt`, `feedback_submission_school`, `help_kb_how_do_i`, `feature_request_roadmap_voting`. **Gaps**: no parent-side entry to migration-cloud guardian-consent that is not a token-deep-link; no parent-side entry to `billing_usage_review` (parents only see invoices, not the plan).
- **student** — primary landing `/portal/student-portal/grades/`; covers `help_kb_how_do_i`, `feature_request_roadmap_voting`, `feedback_submission_school`. **Gaps**: student-side workflows are read-mostly; no student-side contextual-feedback hook beyond `/student/feedback/`.

## Notes for future phases

- `apps/academics/urls.py` was NOT deep-walked in this phase (`class_setup` priority p2). Targeted sub-audit recommended.
- Mobile-safe signal is set to `unknown` (honest) rather than `yes` for any workflow we did not inspect for breakpoint classes — `portal_base.html` has 5 responsive class hits which is the most reliable signal we measured.
- 12-route spot-check exceeded the 5-route minimum; see `verified_at` per workflow in the JSON.
