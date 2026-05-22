# Platform workflow classification matrix (Phase 1)

Hand-curated classification of every primary workflow on the platform. Step counts are flagged `measurement_status: hypothesis` unless explicitly measured. Decision rules per the Phase 1 brief: `strong` -> preserve, `usable_but_unclear` -> simplify copy/tags/next-actions, `fragmented` -> consolidate or guided path, `broken` -> fix end-to-end, `missing_how_to` -> create how-to metadata, `missing_info_tags` -> add contextual tags, `missing_ai_help` -> add AI only where specific next action, `external_blocked` -> document honestly.

Total workflows classified: **112**

## Summary tables

### Workflows per status

| Status | Count |
|---|---:|
| `strong` | 52 |
| `usable_but_unclear` | 24 |
| `fragmented` | 12 |
| `missing_how_to` | 7 |
| `missing_info_tags` | 7 |
| `too_many_clicks` | 5 |
| `external_blocked` | 4 |
| `missing_ai_help` | 1 |

### Workflows per audience (a workflow may serve more than one)

| Audience | Count |
|---|---:|
| `tenant_school_admin` | 69 |
| `platform_operator` | 41 |
| `parent` | 20 |
| `teacher` | 17 |
| `student` | 13 |
| `developer_partner` | 10 |
| `support_success` | 7 |

### Workflows per surface

| Surface | Count |
|---|---:|
| `tenant` | 55 |
| `shared` | 27 |
| `operator` | 21 |
| `public` | 8 |
| `api` | 1 |

### Workflows per risk level

| Risk level | Count |
|---|---:|
| `medium` | 41 |
| `low` | 36 |
| `high` | 34 |
| `critical` | 1 |

### Workflows per measurement status

| Measurement status | Count |
|---|---:|
| `hypothesis` | 111 |
| `measured` | 1 |

## Top-10 fix-me-first list

Ranked by risk (descending) then status priority (broken/fragmented/too_many_clicks first). `external_blocked` rows are excluded — they are listed separately below.

| # | Workflow ID | Risk | Status | Rationale |
|---:|---|---|---|---|
| 1 | `accounts-rollover` | `critical` | `fragmented` | Wizardize: snapshot -> promotion preview -> approvals -> commit; force a rollback-safe checkpoint. |
| 2 | `accounts-entity-import` | `high` | `fragmented` | Consolidate map + validate + dry-run + commit into a 4-step wizard with row-level error report. |
| 3 | `finance-cash-closure` | `high` | `too_many_clicks` | Provide auto-tally + variance chip + single signature confirm. |
| 4 | `offline-conflict-resolve` | `high` | `fragmented` | Manager route explains tenant scope and sends operator to school selector (measured existing audit). |
| 5 | `operator-create-school` | `high` | `too_many_clicks` | Consolidate wizard into 3-step guided flow with inline plan picker and DNS preview. |
| 6 | `operator-school-onboard-wizard` | `high` | `fragmented` | Merge with implementation_command_center into one guided activation flow with a single go-live score. |
| 7 | `parent-payment-receipt` | `high` | `fragmented` | Money Center shows invoice, manual fallback, and receipt capture together (existing audit). |
| 8 | `public-school-signup` | `high` | `too_many_clicks` | Reduce to 3-step signup with progressive disclosure of detail fields. |
| 9 | `report-generation` | `high` | `fragmented` | Governed report builder exposes one primary generate/export action (existing audit). |
| 10 | `studio-os-launch` | `high` | `fragmented` | Consolidate launch_timeline + approvals + risk panels behind a single readiness score. |

## Externally blocked workflows

These cannot be fixed by in-repo Phase 4 work alone; they are gated on an actor or system outside this repo. Each row quotes the blocker verbatim from the `required_fix` field so it is auditable.

| Workflow ID | Blocker (quoted) |
|---|---|
| `migration-maa-v2-promotion` | external_blocked: 'awaits counsel signoff PDF before flip can occur'. |
| `billing-stripe-connect` | external_blocked: 'tenant must complete Stripe Connect KYC offsite before completion'. |
| `security-saml-oidc-link` | external_blocked: 'requires IdP-side admin to publish metadata before completion'. |
| `integrations-marketplace-connect` | external_blocked: 'third-party OAuth grant happens on the provider side outside this app'. |

## Full per-workflow table

Sorted by `risk_level` descending then `current_status`. `current_step_count` is a hypothesis estimate range unless `measurement_status: measured` is set.

| Workflow ID | App | Audience | Surface | Entry route | Primary goal | Current steps | Ideal | Status | Risk | Required fix | Measurement |
|---|---|---|---|---|---|---|---:|---|---|---|---|
| `accounts-rollover` | `accounts` | tenant_school_admin | `tenant` | `/authentication/rollover/` | Admin promotes students/classes into the next academic year. | 5-7 | 4 | `fragmented` | `critical` | Wizardize: snapshot -> promotion preview -> approvals -> commit; force a rollback-safe checkpoint. | `hypothesis` |
| `security-saml-oidc-link` | `accounts` | tenant_school_admin | `tenant` | `/authentication/saml/` | Tenant admin links an external IdP for SSO. | 5-7 | 4 | `external_blocked` | `high` | external_blocked: 'requires IdP-side admin to publish metadata before completion'. | `hypothesis` |
| `accounts-entity-import` | `accounts` | tenant_school_admin | `tenant` | `/authentication/entity-import/` | Admin imports student/teacher/parent CSV in bulk. | 4-6 | 4 | `fragmented` | `high` | Consolidate map + validate + dry-run + commit into a 4-step wizard with row-level error report. | `hypothesis` |
| `offline-conflict-resolve` | `portal` | teacher,tenant_school_admin | `shared` | `/offline/conflicts/` | User resolves conflicts between offline edits and server state. | 3 | 1 | `fragmented` | `high` | Manager route explains tenant scope and sends operator to school selector (measured existing audit). | `measured` |
| `operator-school-onboard-wizard` | `schools` | platform_operator | `operator` | `/super/schools/<id>/onboard/` | Walk a newly created tenant through theme, identity, and first-admin invite. | 6-9 | 4 | `fragmented` | `high` | Merge with implementation_command_center into one guided activation flow with a single go-live score. | `hypothesis` |
| `parent-payment-receipt` | `finance` | parent | `tenant` | `/finance/invoices/<id>/receipt/` | Capture payment receipt when PSP is external; preserve audit trail. | 4 | 2 | `fragmented` | `high` | Money Center shows invoice, manual fallback, and receipt capture together (existing audit). | `hypothesis` |
| `report-generation` | `analytics` | tenant_school_admin | `tenant` | `/analytics/` | Generate an ad-hoc analytics report with one primary action. | 4 | 2 | `fragmented` | `high` | Governed report builder exposes one primary generate/export action (existing audit). | `hypothesis` |
| `studio-os-launch` | `studio_os` | tenant_school_admin,platform_operator | `shared` | `/studio/launch/` | Walk a tenant through plan select, infra check, and go-live readiness. | 5-7 | 4 | `fragmented` | `high` | Consolidate launch_timeline + approvals + risk panels behind a single readiness score. | `hypothesis` |
| `teacher-attendance` | `portal` | teacher | `tenant` | `/teacher/attendance/` | Teacher records attendance for the active class. | 3 | 2 | `fragmented` | `high` | Teacher Workspace next-action strip opens attendance for the active class (existing audit). | `hypothesis` |
| `teacher-marks-entry` | `evals` | teacher | `tenant` | `/evals/grade-import/upload/` | Teacher enters marks for an assessment. | 3 | 2 | `fragmented` | `high` | Pending work card links directly to marks grid (existing audit). | `hypothesis` |
| `tenant-guided-configuration` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/guided-onboarding/` | Walk admin through canned configuration journeys (academic year, departments, grading). | 6-10 | 4 | `fragmented` | `high` | Consolidate into one orchestrated journey with completion-aware skip logic. | `hypothesis` |
| `tenant-onboarding-coach` | `platform_runtime` | tenant_school_admin | `tenant` | `/platform-runtime/implementation/` | Resolve go-live blockers in priority order against a single readiness score. | 5 | 2 | `fragmented` | `high` | Implementation Command Center exposes go-live score and primary next action (per existing audit). | `hypothesis` |
| `compliance-erasure-request` | `compliance` | parent,student,tenant_school_admin | `tenant` | `/compliance/erasure/` | Subject files erasure request with structured intake. | 3-4 | 3 | `missing_how_to` | `high` | Add plain-language explanation of what gets erased and how long it takes. | `hypothesis` |
| `compliance-regulatory-export` | `reports` | tenant_school_admin | `tenant` | `/reports/regulatory-export/` | Generate regulator-compliant export of tenant data for ministry/district. | 3-5 | 3 | `missing_how_to` | `high` | Add per-regulator pre-flight check and field-coverage badge. | `hypothesis` |
| `migration-guardian-consent` | `migration_cloud` | parent | `tenant` | `/migration/guardian/consent/` | Capture parent/guardian consent before student PII migrates. | 2-3 | 2 | `missing_how_to` | `high` | Add plain-language how-to block above consent prompt and FAQ chip. | `hypothesis` |
| `payroll-create-run` | `payroll` | tenant_school_admin | `tenant` | `/payroll/create-run/` | Admin generates a payroll run for a period. | 3-4 | 3 | `missing_how_to` | `high` | Add 'what this generates' summary chip and reversibility note. | `hypothesis` |
| `reports-promotion-preview` | `reports` | tenant_school_admin | `tenant` | `/reports/promotion-preview/` | Admin previews promotion decisions before student-class rollover. | 3-4 | 3 | `missing_how_to` | `high` | Add per-rule explanation and 'override' audit-tagged action. | `hypothesis` |
| `accounts-legacy-setup` | `accounts` | tenant_school_admin,teacher,parent,student | `shared` | `/authentication/legacy/setup/` | Legacy user sets new credentials via emailed one-time link. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `accounts-migration-wizard` | `accounts` | tenant_school_admin | `tenant` | `/authentication/migration/` | Legacy SIS user lands and re-establishes credentials on RMC. | 3-4 | 3 | `strong` | `high` | none | `hypothesis` |
| `api-token-mint` | `migration_cloud` | platform_operator,developer_partner | `operator` | `/super/migration/operator/tokens/mint/` | Mint a scoped API token with selectable scope set. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `api-webhook-subscribe` | `migration_cloud` | platform_operator,developer_partner | `operator` | `/super/migration/operator/webhooks/subscribe/` | Subscribe a customer endpoint to a Migration Cloud event class. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `migration-companion-upload` | `migration_cloud` | platform_operator,support_success | `api` | `/migration/companion/upload/` | Receive sealed-box vendor extraction from the companion-extension into a bundle. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `migration-maa-sign` | `migration_cloud` | tenant_school_admin | `tenant` | `/migration/companion/maa/sign/` | Tenant signs MAA so companion can stream sealed extraction. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `parent-claim-invite` | `portal` | parent | `tenant` | `/parent/claim-invite/<token>/` | First-time parent activates account from an invite token link. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `reports-publish-term` | `reports` | tenant_school_admin | `tenant` | `/reports/publish-term/` | Publish report cards to parents/students for a term. | 3-4 | 3 | `strong` | `high` | none | `hypothesis` |
| `security-mfa-setup` | `accounts` | tenant_school_admin,teacher,platform_operator | `shared` | `/authentication/mfa/setup/` | User enrolls TOTP / passkey as second factor. | 3-4 | 3 | `strong` | `high` | none | `hypothesis` |
| `teacher-grade-approval` | `evals` | tenant_school_admin | `tenant` | `/evals/grade-approval/` | Admin approves teacher-submitted grades before publish. | 2-3 | 2 | `strong` | `high` | none | `hypothesis` |
| `finance-cash-closure` | `finance` | tenant_school_admin,support_success | `tenant` | `/finance/payments/cash-closure/` | Reconcile cash payments at end of day and sign closure ledger. | 4-6 | 3 | `too_many_clicks` | `high` | Provide auto-tally + variance chip + single signature confirm. | `hypothesis` |
| `operator-create-school` | `schools` | platform_operator | `operator` | `/super/schools/create/` | Spin up a new school tenant with subdomain, plan, and seed admin user. | 5-7 | 3 | `too_many_clicks` | `high` | Consolidate wizard into 3-step guided flow with inline plan picker and DNS preview. | `hypothesis` |
| `public-school-signup` | `schools` | tenant_school_admin | `public` | `/signup/` | Prospective school admin self-registers a new tenant. | 4-6 | 3 | `too_many_clicks` | `high` | Reduce to 3-step signup with progressive disclosure of detail fields. | `hypothesis` |
| `tenant-onboarding-step` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/onboarding/` | Walk tenant admin through department / year / grading-scale setup before go-live. | 8-12 | 6 | `too_many_clicks` | `high` | Reduce wizard to 6 steps with auto-saved drafts and parallel-do hints. | `hypothesis` |
| `ai-center-modelfile` | `apicenter` | platform_operator | `operator` | `/super/api-center/ai/` | Operator configures, publishes, and rolls back AI modelfiles. | 4-6 | 4 | `usable_but_unclear` | `high` | Add deployment-posture context chip per services/ai_deployment_posture. | `hypothesis` |
| `billing-plan-pick` | `siteconfig` | tenant_school_admin,platform_operator | `shared` | `/siteconfig/billing-plan/` | Pick or upgrade tenant billing plan and seed Stripe customer. | 3-4 | 3 | `usable_but_unclear` | `high` | Show price delta and proration band before confirm; clarify cycle. | `hypothesis` |
| `blueprint-rollback` | `platform_runtime` | platform_operator,tenant_school_admin | `shared` | `/platform-runtime/blueprints/installations/` | Revert a blueprint install when impact assessment goes south. | 3-4 | 3 | `usable_but_unclear` | `high` | Add explicit 'what this removes' diff before confirm. | `hypothesis` |
| `operator-impersonation` | `accounts` | platform_operator,support_success | `shared` | `/authentication/impersonation/` | Allow operator/support to land in a tenant user's shell to reproduce an issue. | 3-4 | 2 | `usable_but_unclear` | `high` | Add explicit banner with end-impersonation chip and reason-required prompt. | `hypothesis` |
| `billing-stripe-connect` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/billing-stripe/` | Connect the tenant's Stripe account for PSP fallback. | 3-4 | 3 | `external_blocked` | `medium` | external_blocked: 'tenant must complete Stripe Connect KYC offsite before completion'. | `hypothesis` |
| `integrations-marketplace-connect` | `integrations_marketplace` | tenant_school_admin,platform_operator | `shared` | `/integrations/` | Tenant connects a marketplace integration with scoped scopes. | 4-5 | 3 | `external_blocked` | `medium` | external_blocked: 'third-party OAuth grant happens on the provider side outside this app'. | `hypothesis` |
| `migration-maa-v2-promotion` | `migration_cloud` | platform_operator | `operator` | `/super/migration/maa-v2-promotion/` | Stage the v2.0 MAA flip after counsel signoff and run preview-only campaign. | 4-6 | 4 | `external_blocked` | `medium` | external_blocked: 'awaits counsel signoff PDF before flip can occur'. | `hypothesis` |
| `customersuccess-guided-onboarding` | `customersuccess` | support_success,tenant_school_admin | `shared` | `/siteconfig/guided-onboarding/` | Success rep walks a tenant through guided onboarding. | 5-7 | 4 | `fragmented` | `medium` | Merge with platform_runtime implementation_command_center to share the same readiness score. | `hypothesis` |
| `ai-copilot-rail` | `portal` | platform_operator,tenant_school_admin | `shared` | `/studio/copilot/rail/` | Ask the AI Copilot for a specific next action in current context. | 1-2 | 1 | `missing_ai_help` | `medium` | Wire AI rail to services.ai_helpers per Studio OS v3.54 deferred contract. | `hypothesis` |
| `orchestration-define-process` | `orchestration` | platform_operator,developer_partner | `shared` | `/orchestration/` | Define a versioned process for the orchestration engine. | 3-5 | 3 | `missing_how_to` | `medium` | Add inline DSL reference and trigger-catalog tooltip. | `hypothesis` |
| `tenant-feature-control` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/feature-control/` | Toggle tenant features behind a guarded control panel with audit. | 2-3 | 2 | `missing_how_to` | `medium` | Add per-flag plain-language description and 'impact' chip. | `hypothesis` |
| `communication-narrative-approve` | `communication` | tenant_school_admin | `tenant` | `/communication/narrative/approve/` | Admin approves a teacher-authored narrative. | 2-3 | 2 | `missing_info_tags` | `medium` | Tag each narrative with policy-compliance hints inline. | `hypothesis` |
| `compliance-data-quality` | `compliance` | tenant_school_admin,platform_operator | `shared` | `/compliance/data-quality/` | Surface PII completeness and field-quality scores with remediation actions. | 2-3 | 2 | `missing_info_tags` | `medium` | Tag each row with severity + next-action chip; explain DLP tier inline. | `hypothesis` |
| `studio-os-output` | `studio_os` | tenant_school_admin,platform_operator | `shared` | `/studio/output/` | Compose report-card and document outputs with readiness gate. | 4-5 | 3 | `missing_info_tags` | `medium` | Wire output_readiness_summary service (Studio OS v3.54 deferred) so output mode shows real counts. | `hypothesis` |
| `teacher-syllabus-approval` | `academics` | tenant_school_admin | `tenant` | `/academics/syllabus/approval-queue/` | Admin approves syllabus submitted by teacher. | 2-3 | 2 | `missing_info_tags` | `medium` | Add per-row diff-vs-template chip and reason-for-changes column. | `hypothesis` |
| `apicenter-oauth-app` | `apicenter` | developer_partner,platform_operator | `operator` | `/super/api-center/oauth/` | Developer/operator registers an OAuth client app. | 2-3 | 2 | `strong` | `medium` | none | `hypothesis` |
| `apicenter-webhook-subscribe` | `apicenter` | developer_partner | `public` | `/api-center/webhooks/subscribe/` | Developer subscribes to a platform-level webhook event class. | 2-3 | 2 | `strong` | `medium` | none | `hypothesis` |
| `blueprint-install` | `platform_runtime` | tenant_school_admin,platform_operator | `shared` | `/platform-runtime/blueprints/` | Pick a blueprint, preview impact, and apply it scoped to the active tenant. | 4-5 | 3 | `strong` | `medium` | none | `hypothesis` |
| `change-request-approve` | `platform_runtime` | tenant_school_admin,platform_operator | `shared` | `/platform-runtime/change-requests/` | Review and approve a pending change-request with scheduled apply. | 3-4 | 3 | `strong` | `medium` | none | `hypothesis` |
| `marketplace-signup-review` | `marketplace` | platform_operator | `operator` | `/marketplace/signup/review-queue/` | Operator approves or rejects a pending publisher signup. | 2-3 | 2 | `strong` | `medium` | none | `hypothesis` |
| `marketplace-webhook-log` | `marketplace` | developer_partner | `public` | `/marketplace/publisher/webhook/log/` | Publisher diagnoses webhook delivery failures with replay option. | 2-3 | 2 | `strong` | `medium` | none | `hypothesis` |
| `migration-audit-export` | `migration_cloud` | platform_operator | `operator` | `/super/migration/audit/export/` | Export the hash-chained audit ledger with optional chain-verify. | 2 | 2 | `strong` | `medium` | none | `hypothesis` |
| `migration-bundle-advance` | `migration_cloud` | platform_operator | `operator` | `/super/migration/<id>/advance/` | Move a bundle from intake -> apply -> reconcile -> shadow with guardrails at each step. | 6-8 | 5 | `strong` | `medium` | Preserve; add inline go/no-go AI explanation block on each stage transition. | `hypothesis` |
| `offline-sync-center-manager` | `platform_runtime` | platform_operator | `operator` | `/platform-runtime/manager-offline-sync/` | Operator selects which tenant's offline queue to inspect. | 1 | 1 | `strong` | `medium` | none | `hypothesis` |
| `pack-install` | `platform_runtime` | tenant_school_admin,platform_operator | `shared` | `/platform-runtime/workflow-packs/` | Pick a pack, simulate it, and apply it to the active tenant. | 4-5 | 3 | `strong` | `medium` | none | `hypothesis` |
| `security-passkey-register` | `accounts` | tenant_school_admin,teacher,platform_operator,parent | `shared` | `/authentication/passkey/` | User registers a platform passkey. | 2-3 | 2 | `strong` | `medium` | none | `hypothesis` |
| `student-photo-upload` | `portal` | student,parent | `tenant` | `/photo-upload/generate/` | Student/parent uploads a photo via phone via single-use QR link. | 2-3 | 2 | `strong` | `medium` | none | `hypothesis` |
| `migration-connectors` | `migration_cloud` | platform_operator | `operator` | `/super/migration/connectors/` | Configure a SIS connector for a tenant and review the resulting import plan. | 5-7 | 4 | `too_many_clicks` | `medium` | Collapse credentials + mapping + preview into a single 4-step wizard. | `hypothesis` |
| `automation-workflow-create` | `automation` | tenant_school_admin,platform_operator | `shared` | `/automation/` | Author defines a workflow (trigger + actions) visually. | 4-5 | 3 | `usable_but_unclear` | `medium` | Add trigger-catalog typeahead and inline simulation. | `hypothesis` |
| `finance-generate-fees` | `finance` | tenant_school_admin | `tenant` | `/finance/fees/generate/` | Generate fee assignments for a class/term in one operation. | 3-4 | 3 | `usable_but_unclear` | `medium` | Add dry-run preview with affected-student count before commit. | `hypothesis` |
| `marketplace-install-app` | `marketplace` | tenant_school_admin | `tenant` | `/marketplace/` | Tenant admin installs a published app with scoped permissions. | 3-4 | 3 | `usable_but_unclear` | `medium` | Surface install-impact modal contents on the listing card itself. | `hypothesis` |
| `observability-incidents` | `observability` | platform_operator | `operator` | `/super/observability/incidents/` | Operator triages platform incidents with friction-tracking links. | 2-3 | 2 | `usable_but_unclear` | `medium` | Add per-incident 'next-action' chip linked to runbook. | `hypothesis` |
| `operator-platform-events` | `schools` | platform_operator | `operator` | `/super/platform-events/` | Review cross-tenant platform-level events for incident triage. | 2-3 | 2 | `usable_but_unclear` | `medium` | Add saved filters and next-action chips per event class. | `hypothesis` |
| `operator-tenant-self-offboard` | `schools` | platform_operator,tenant_school_admin | `shared` | `/super/schools/<id>/offboarding/` | Capture a structured tenant offboarding request with audit trail. | 3-5 | 3 | `usable_but_unclear` | `medium` | Simplify copy and add explicit data-retention next-action. | `hypothesis` |
| `parent-finance` | `portal` | parent | `tenant` | `/parent/finance/` | Parent reviews due invoices and either pays via PSP or captures cash receipt. | 2-3 | 2 | `usable_but_unclear` | `medium` | Add payment-method recommendation chip honoring tenant PSP capability. | `hypothesis` |
| `people-create-student` | `people` | tenant_school_admin | `tenant` | `/backend/people/students/create/` | Admin creates a student record. | 3-4 | 3 | `usable_but_unclear` | `medium` | Show CSV-import option above single-create form. | `hypothesis` |
| `people-create-teacher` | `people` | tenant_school_admin | `tenant` | `/backend/people/teachers/create/` | Admin creates a teacher record with invite. | 3-4 | 3 | `usable_but_unclear` | `medium` | Surface invite-email status badge inline. | `hypothesis` |
| `signature-requests` | `portal` | tenant_school_admin,parent | `tenant` | `/portal/signature-requests/` | Admin requests a signature; parent signs. | 3-4 | 3 | `usable_but_unclear` | `medium` | Add per-recipient status badge in list view. | `hypothesis` |
| `student-onboarding` | `portal` | student | `tenant` | `/student/onboarding/` | First-login student completes profile + photo + locale onboarding. | 3-5 | 3 | `usable_but_unclear` | `medium` | Auto-save partial progress; add 'skip and come back later' chip. | `hypothesis` |
| `studio-os-automation` | `studio_os` | tenant_school_admin,platform_operator | `shared` | `/studio/automation/` | Build and simulate automation flows (rollback supported). | 4-6 | 3 | `usable_but_unclear` | `medium` | Add workflow-health summary chip (paused/failing counts) per Studio OS v3.54 deferred. | `hypothesis` |
| `studio-os-control` | `studio_os` | platform_operator,tenant_school_admin | `shared` | `/studio/control/` | Observe governance posture and run AI-assisted cleanup or rollback. | 3-5 | 3 | `usable_but_unclear` | `medium` | Promote AI-cleanup CTA above audit list and add 'why this matters' chip. | `hypothesis` |
| `studio-os-experience` | `studio_os` | tenant_school_admin,platform_operator | `shared` | `/studio/experience/` | Compose tenant landing experience and compare variants before publish. | 4-6 | 3 | `usable_but_unclear` | `medium` | Expose primary publish action above the fold and add inline rollback chip. | `hypothesis` |
| `tenant-custom-domain` | `schools` | tenant_school_admin | `tenant` | `/siteconfig/domains/` | Bind a custom domain to the tenant via guided CNAME verification. | 4-6 | 3 | `usable_but_unclear` | `medium` | Add DNS-record copy chip and inline propagation check with retry timer. | `hypothesis` |
| `tenant-grading-scale-setup` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/grading-settings/` | Persist tenant grading scale bands used downstream by reports + evals. | 3-5 | 3 | `usable_but_unclear` | `medium` | Add example-school presets and preview against a sample mark. | `hypothesis` |
| `tenant-sync-center` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/sync-center/` | Trigger and observe tenant-scoped data sync jobs. | 2-3 | 2 | `usable_but_unclear` | `medium` | Surface last-success + failure-class summary above run button. | `hypothesis` |
| `requests-dashboard` | `requests` | tenant_school_admin | `tenant` | `/requests/` | Tenant admin triages incoming structured requests. | 1-2 | 1 | `missing_info_tags` | `low` | Tag each request by category and add 'next action' chip. | `hypothesis` |
| `sales-lead-capture` | `sales` | platform_operator | `operator` | `/sales/lead/create/` | Operator records a new sales lead. | 2-3 | 2 | `missing_info_tags` | `low` | Add lead-source and stage tags with quick-pick chips. | `hypothesis` |
| `school-events-calendar` | `school_events` | tenant_school_admin,teacher,parent,student | `shared` | `/events/` | Anyone views or files a school calendar event. | 1-2 | 1 | `missing_info_tags` | `low` | Tag events by audience/grade and add ICS subscribe chip. | `hypothesis` |
| `api-webhook-catalog` | `api` | developer_partner | `public` | `/api/v1/docs/` | Developer reads the OpenAPI/Redoc reference. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `automation-visual-workflow` | `automation` | tenant_school_admin | `tenant` | `/siteconfig/workflow-gallery/` | Pick a pre-baked workflow from the gallery. | 2-3 | 2 | `strong` | `low` | none | `hypothesis` |
| `events-console` | `events` | tenant_school_admin | `tenant` | `/domain-events/` | Tenant admin reviews domain events emitted by tenant ops. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `feedback-status` | `feedback` | tenant_school_admin,teacher,parent,student | `public` | `/status/` | Anyone observes platform status without auth. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `feedback-submit` | `feedback` | tenant_school_admin,teacher,parent,student | `shared` | `/feedback/submit/` | Any user submits feedback that auto-routes to support queue. | 2 | 1 | `strong` | `low` | none | `hypothesis` |
| `finance-access-request` | `finance` | tenant_school_admin | `tenant` | `/finance/access/request/` | Tenant user requests finance-module access with approver in loop. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `finance-invoice-list` | `finance` | tenant_school_admin,support_success | `tenant` | `/finance/invoices/` | List, filter, and open invoices for collection action. | 2-3 | 2 | `strong` | `low` | none | `hypothesis` |
| `finance-trial-balance` | `finance` | tenant_school_admin | `tenant` | `/finance/trial-balance/` | Observe period trial balance with drill-down. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `forums-new-topic` | `portal` | tenant_school_admin,teacher,parent,student | `tenant` | `/forums/new/` | User starts a new forum topic. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `help-kb-search` | `portal` | tenant_school_admin,teacher,parent,student | `shared` | `/kb/` | User finds an answer via ranked KB search. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `marketplace-publisher-dashboard` | `marketplace` | developer_partner | `public` | `/marketplace/publisher/dashboard/` | Publisher views own apps, installs, ratings, and revenue. | 1-2 | 1 | `strong` | `low` | none | `hypothesis` |
| `marketplace-publisher-signup` | `marketplace` | developer_partner | `public` | `/marketplace/publisher/signup/` | Onboard a third-party developer/publisher to the marketplace with verification. | 3-5 | 3 | `strong` | `low` | none | `hypothesis` |
| `migration-bundle-create` | `migration_cloud` | platform_operator | `operator` | `/super/migration/new/` | Start a new SIS migration bundle bound to a target tenant. | 3-4 | 3 | `strong` | `low` | none | `hypothesis` |
| `migration-health` | `migration_cloud` | platform_operator | `operator` | `/super/migration/health/` | Operator observes Migration Cloud SLO + delivery + scanner baselines. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `observability-friction` | `observability` | platform_operator,support_success | `operator` | `/super/observability/friction/` | Surface top-N tenant friction events with linked sessions. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `offline-sync-queue` | `portal` | teacher,tenant_school_admin | `tenant` | `/offline/sync-queue/` | User observes pending offline-queued actions waiting on sync. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `parent-contact-school` | `portal` | parent | `tenant` | `/parent/contact-school/` | Parent contacts the school with structured intake. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `parent-medal-case` | `portal` | parent | `tenant` | `/parent/medal-case/` | Parent celebrates verified student achievements. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `parent-performance` | `portal` | parent | `tenant` | `/parent/performance/` | Parent reviews student academic performance with term filter. | 1-2 | 1 | `strong` | `low` | none | `hypothesis` |
| `platform-runtime-click-measurement` | `platform_runtime` | platform_operator | `operator` | `/platform-runtime/click-measurement/` | Operator observes measured per-workflow step counts to drive Phase-2+ work. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `platform-runtime-rum` | `platform_runtime` | platform_operator | `operator` | `/platform-runtime/rum/` | Operator observes core-web-vitals + tenant-scoped RUM data. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `public-badge-verify` | `portal` | tenant_school_admin,developer_partner,parent,student | `public` | `/badge/verify/` | Anyone with a badge URL verifies authenticity. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `security-trust-hub` | `accounts` | tenant_school_admin | `tenant` | `/authentication/trust-hub/` | Tenant admin reviews tenant security posture. | 1-2 | 1 | `strong` | `low` | none | `hypothesis` |
| `student-portal-grades` | `portal` | student | `tenant` | `/student-portal/grades/` | Student observes own grades with term filter. | 1 | 1 | `strong` | `low` | none | `hypothesis` |
| `support-help-hub` | `portal` | tenant_school_admin,teacher,parent,student | `shared` | `/support/hub/` | Show role-aware help articles before opening a ticket. | 1-2 | 1 | `strong` | `low` | none | `hypothesis` |
| `support-request` | `portal` | tenant_school_admin,teacher,parent,student | `shared` | `/support/` | User opens support ticket after self-serve deflection failed. | 2-3 | 2 | `strong` | `low` | none | `hypothesis` |
| `teacher-leave` | `portal` | teacher | `tenant` | `/teacher/leave/` | Teacher files a leave request through HR loop. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `teacher-lesson-notes` | `portal` | teacher | `tenant` | `/teacher/lesson-notes/` | Teacher records lesson notes for today's class. | 2 | 2 | `strong` | `low` | none | `hypothesis` |
| `tenant-theme-builder` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/school-theme/` | Pick tenant brand color + logo + typography and preview live. | 3-4 | 3 | `strong` | `low` | none | `hypothesis` |
| `tenant-zero-ticket-hub` | `siteconfig` | tenant_school_admin | `tenant` | `/siteconfig/zero-ticket/` | Surface known tenant issues with self-serve fixes before opening a support ticket. | 2-3 | 2 | `strong` | `low` | none | `hypothesis` |
| `communication-announcement-create` | `communication` | tenant_school_admin,teacher | `tenant` | `/communication/announcement/create/` | Author composes and publishes a school announcement. | 3-4 | 3 | `usable_but_unclear` | `low` | Add audience-preview chip showing recipient counts before publish. | `hypothesis` |
| `help-kb-submit` | `portal` | platform_operator,support_success | `operator` | `/kb/article/submit/` | Author drafts a new KB article tagged to a workflow. | 3 | 3 | `usable_but_unclear` | `low` | Add workflow-tag picker and inline preview. | `hypothesis` |
| `people-applicant-create` | `people` | tenant_school_admin | `tenant` | `/backend/people/applicants/create/` | Admin captures applicant intake. | 3-4 | 3 | `usable_but_unclear` | `low` | Combine common fields between applicant and student create forms. | `hypothesis` |

