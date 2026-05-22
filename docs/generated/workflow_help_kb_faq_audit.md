# Phase 9 — Workflow Help / KB / FAQ Coverage Audit

- Doc: `workflow_help_kb_faq_audit`
- Phase: 9
- Generated: 2026-05-22
- Scope: Workflow-level help / KB / FAQ coverage across the RunMyCampus platform
- Source inputs: Phase 0 code-truth inventory, `apps/portal/urls_kb.py`, `config/manager_help_*.py`, `config/manager_kb_locale_families.py`, `templates/portal/`, `templates/feedback/`, `templates/apicenter/super/`, `templates/schools/partials/`, `templates/marketing/`, `templates/partials/help_*.html`, `docs/*.md` help-shaped artifacts
- Companion JSON: `docs/generated/workflow_help_kb_faq_audit.json`

## Verdict

`PHASE_9_HELP_KB_FAQ_AUDIT_READY` — 64 workflows audited across operator, school_admin, teacher, parent, and partner audiences. Spot-checks confirmed 5 "exists" claims plus 1 docs blocker file.

## Method

- Pulled the 50-app rollup from `docs/generated/platform_workflow_code_truth_inventory.json`. Phase 0 reports 4 apps with help templates (`feedback`, `portal`, `schools`, `apicenter`) and 20 apps with workflow-shaped templates but no nearby help.
- Read `apps/portal/urls_kb.py` (19 routes under `kb:` namespace covering FAQ list/detail/vote/submit, KB home/category/article/download-{odt,docx,pdf}/vote/comment/submit, Collabora office docs + WOPI, KB search, user contributions).
- Read `config/manager_help_center.py`, `config/manager_help_analytics.py`, `config/manager_help_engagement.py`, `config/manager_kb_locale_families.py` to understand the operator help front door, the analytics dashboard, the feature-center engage flow, and the KB locale-family ops surface.
- Globbed `templates/**/*help*.html`, `*faq*.html`, `kb_*.html`, `*guide*.html` to enumerate help-shaped surfaces.
- Spot-check verification (5 "exists" claims + 1 docs blocker file):
  1. `templates/portal/kb_home.html` — confirmed extends `portal_base`, has journal-text hero, skip-link, offline-read-cache key.
  2. `templates/portal/faq_list.html` — confirmed categories sidebar with vote endpoints.
  3. `templates/feedback/help_center.html` — confirmed `backend_base` shell, includes the engage strip, advisor character, persona quickstart partial.
  4. `templates/portal/support_help_hub.html` — confirmed `portal_base`, self-serve + tickets + contacts grid.
  5. `templates/apicenter/super/ai_center_kb_drafts.html` — confirmed moderation gate text: "Drafts require human review before tenant-visible publish."
  6. `docs/FAQ_KB_IMPLEMENTATION_GUIDE.md` — confirmed FAQ + KB model documentation including the DRAFT → PENDING → APPROVED/REJECTED moderation FSM.

## Scoring rules

- `ai_draft_capable: yes` only when the route emits structured evidence (signal bundle, friction event, failed AI session, observability metric) AND `services.ai_helpers` is wired in the responsible app (Phase 0 `has_apicenter_import: true`).
- `moderation_gate_present: yes` only when code reads draft → review → publish FSM (KBArticle.status, FAQ.status, HelpContentGapTask) or the template literally says drafts require review.

## KB router summary

| Property | Value |
| --- | --- |
| Namespace | `kb` |
| Mount points | `manager_urls.py:kb/`, `tenant_urls.py:kb/`, `urls.py:kb/` |
| Routes | 19 |
| Surfaces | operator + tenant + default |

## KB locale-families config

- Source: `config/manager_kb_locale_families.py`
- Operator URL name: `manager_kb_locale_families`
- Operations exposed: `set_group`, `mark_canonical`, `create_variant`, `seed_variants`, `publish_group`
- Variant targets constant: `apps.portal.kb_locale_ops.LOCALE_VARIANT_TARGETS`
- Cross-links to `manager_help_center` and `kb:kb_home`

## Coverage rollup

- Total workflows audited: **64**

### By help-article status

| Status | Count | % |
| --- | ---: | ---: |
| exists | 21 | 32.8% |
| draft | 5 | 7.8% |
| missing | 38 | 59.4% |
| unverified | 0 | 0.0% |

### By FAQ status

| Status | Count |
| --- | ---: |
| exists | 11 |
| candidate | 44 |
| missing | 9 |

### By priority

| Priority | Count |
| --- | ---: |
| p0 | 14 |
| p1 | 18 |
| p2 | 16 |
| p3 | 16 |

### Modality

| Attribute | yes | no |
| --- | ---: | ---: |
| AI-draft capable | 43 | 21 |
| Moderation gate present | 35 | 29 |

## Per-audience coverage

| Audience | Total | exists | draft | missing | exists % |
| --- | ---: | ---: | ---: | ---: | ---: |
| operator | 24 | 8 | 3 | 13 | 33.3% |
| school_admin | 30 | 9 | 2 | 19 | 30.0% |
| teacher | 4 | 0 | 0 | 4 | 0.0% |
| parent | 1 | 0 | 0 | 1 | 0.0% |
| student | 0 | 0 | 0 | 0 | n/a |
| partner | 5 | 4 | 0 | 1 | 80.0% |

The **teacher** and **parent** audiences have zero "exists" help articles. Every teacher-touching workflow surfaced (academics syllabus approval, evals grade approval, evals grade import, communication announcement create + narrative approve) lacks help. The single parent-tagged workflow (portal photo-upload) is missing as well. Phase 9 surfaces this as the largest equity gap.

The **partner** audience is healthiest at 80% because marketing KB / FAQ accordion already ship a public corpus.

## Top-20 draft-me-first priority list

| # | Workflow | Priority | AI-draft capable | Rationale |
| ---: | --- | --- | --- | --- |
| 1 | `operator-platform-runtime-blueprint-apply` | p0 | yes | 20+ blueprint templates without help; richest evidence base (403 tests + apicenter import); operator-facing irreversible action |
| 2 | `operator-platform-runtime-pack-rollback` | p0 | yes | High-stakes rollback; pairs with rank 1 |
| 3 | `tenant-evals-grade-approval` | p0 | no | Teacher audience at 0% coverage; grade approval directly affects students — human author |
| 4 | `tenant-evals-grade-import` | p0 | no | Two upload variants exist (v1 + v2) with zero help; common-blocker callouts needed |
| 5 | `tenant-customersuccess-guided-onboarding` | p0 | yes | Top of customer-journey funnel |
| 6 | `tenant-accounts-onboarding-wizard` | p0 | yes | Setup blockers cascade everywhere downstream |
| 7 | `tenant-accounts-mfa-setup` | p0 | no | Security-sensitive lockout flow — human author only |
| 8 | `tenant-finance-payment-readiness` | p0 | yes | Money path with AI-helpers wired (`apps/finance/ai_categorize.py`) |
| 9 | `tenant-compliance-erasure-request` | p0 | no | Legally load-bearing (DSAR); cross-link `docs/DSAR_RUNBOOK.md` |
| 10 | `tenant-reports-publish-term` | p0 | no | Irreversible term publish; pre-flight checklist |
| 11 | `tenant-migration-cloud-connector-import` | p0 | yes | Connector wizard with no help; cross-link `docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md` |
| 12 | `operator-schools-create-school-wizard` | p0 | yes | Tenant provisioning has zero operator help |
| 13 | `operator-schools-onboard-wizard` | p0 | yes | Operator-facing onboarding; AI-draft feasible |
| 14 | `tenant-accounts-migration-wizard` | p0 | yes | Migration cloud surface; cross-link operator dockets |
| 15 | `operator-help-analytics` | p1 | yes | Partial body exists; needs standalone "how to read these metrics" KB |
| 16 | `operator-kb-locale-families` | p1 | yes | Needs narrative for `seed_variants` vs `publish_group` |
| 17 | `operator-ai-review-queue` | p1 | yes | Reviewer runbook; promotes existing partial |
| 18 | `tenant-communication-announcement-create` | p1 | yes | 5 announcement templates with no help; teacher audience |
| 19 | `tenant-marketplace-publisher-signup` | p1 | yes | Partner-audience onramp |
| 20 | `operator-siteconfig-guided-configuration` | p1 | yes | siteconfig has the richest evidence base (320 tests) |

## Preserve list (already strong)

- `tenant-kb-browse-published-article` — mature KB shell with download/vote/comment
- `tenant-kb-search` — zero-result feed wired to help-analytics
- `tenant-faq-browse` — categories sidebar + vote endpoints
- `tenant-faq-submit` — DRAFT → PENDING → APPROVED moderation FSM
- `tenant-support-help-hub` — strong portal_base front door
- `operator-help-center` — discover/engage/operate/govern grouping
- `operator-ai-center-kb-drafts` — moderation gate template ("Drafts require human review before tenant-visible publish.")
- `operator-ai-center-faq-candidates` — sibling of KB drafts
- `operator-feature-center` — customer-voice funnel
- `operator-voice-of-customer` — cross-tenant feedback triage
- `marketing-public-kb` — public sovereign KB
- `tenant-help-contextual-drawer` — embedded help pattern
- `tenant-help-module-inline-assistant` — moderated inline AI assistant

## Cross-references

- KB locale families config: `config/manager_kb_locale_families.py`
- KB locale targets constant: `apps.portal.kb_locale_ops.LOCALE_VARIANT_TARGETS`
- Manager help center: `config/manager_help_center.py` -> `templates/schools/partials/manager_help_center_body.html`
- Manager help analytics: `config/manager_help_analytics.py` -> `templates/schools/partials/manager_help_analytics_body.html`
  - Depends on `apps.portal.help_north_star.build_north_star_bundle`, `apps.feedback.models.HelpContentGapTask`, `apps.portal.help_content_gaps.{assign_content_gap, create_kb_draft_from_content_gap}`
- Manager help engagement: `config/manager_help_engagement.py` -> feature center + contact us
  - Depends on `apps.feedback.models.FeatureRequest`, `apps.feedback.services.{submit_feature_request, support_entry_points, generate_you_said_we_did_items}`
- AI draft pipeline source: `apps/portal/help_content_gaps.create_kb_draft_from_content_gap`
- AI draft moderation template: `templates/apicenter/super/ai_center_kb_drafts.html`

### Existing docs that capture blockers

| Doc | What it covers |
| --- | --- |
| `docs/FAQ_KB_IMPLEMENTATION_GUIDE.md` | FAQ+KB schema, DRAFT->PENDING->APPROVED/REJECTED workflow |
| `docs/FAQS_COMPREHENSIVE.md` | platform-wide FAQ master list |
| `docs/HELP_CENTER_LOCALE_CORPUS_RUNBOOK.md` | locale corpus build/refresh procedure |
| `docs/HELP_CENTER_PARENT_STUDENT_POLICY.md` | what parent/student help may surface vs gate |
| `docs/EMBEDDED_HELP_AND_EMPTY_STATES.md` | inline-help drawer / proactive nudge pattern |
| `docs/EMPTY_STATE_AND_HELP.md` | empty state copy patterns |
| `docs/KB_IMPORT_GUIDE.md` | bulk KB article import |
| `docs/OFFLINE_HELP_APPLIANCE.md` | offline help cache + appliance contract |
| `docs/AI_SURFACES_FAQ.md` | AI surfaces customer-facing FAQ |

## Constraints observed

- no product code changes (audit only)
- read-only filesystem walk
- stdlib only for any helper
- no new help content written
- no commits, no SOT updates
- no emojis
- 5 "exists" claims spot-checked plus 1 docs blocker file
