# Four strategic moves — v3.27 (2026-05-18)

The four "load-bearing" investments that flip RunMyCampus from "well-built
internal platform" to "Salesforce / Shopify / AWS / Linux of EdTech."

Total new tests: **54 (54 passing)**. Total new models: **15** (5 + 5 + 2 + 0 + extensions).
Total new Celery tasks: **6**. Total new HTTP endpoints: **15**.

| Move | App(s) | Status |
|------|--------|--------|
| 1 — Marketplace = developer platform | `apps/marketplace/` | shipped |
| 2 — Real workflow engine | `apps/orchestration/`, `apps/automation/` | shipped |
| 3 — PDP + ABAC + field-level RLS | `apps/policies/`, `apps/metadata/` | shipped |
| 4 — Close the help-center loop | `apps/feedback/`, `apps/customersuccess/`, `apps/portal/` | shipped |

---

## Move 1 — Marketplace is a real developer platform

Migration: `apps/marketplace/migrations/0013_developer_platform_v2.py`.

**New models**

- `AppVersion` — semver release history per `MarketplaceApp` (channel, changelog,
  yank flag, publisher snapshot of manifest)
- `AppRating` — 1–5 stars + headline + body + verified-install flag +
  publisher reply, unique per `(app, school)`
- `WebhookEndpoint` — publisher-declared HTTPS endpoints per app
- `WebhookDelivery` — append-only delivery log with idempotency key, status
  machine `pending → in_flight → succeeded | failed → abandoned`, attempt count,
  signature, latency, response snippet, exponential-backoff `next_attempt_at`
- `PublisherSignupRequest` — self-serve publisher application with email
  verification token + reviewer fields
- `PublisherOrganization` extended with `verified_contact_email`, `website_url`,
  `support_email`

**New services**

- `apps/marketplace/publisher_signup.py` — submit / verify / approve / reject /
  email-verify chain
- `apps/marketplace/app_versions.py` — `publish_version`, `list_versions`,
  `latest_stable`, `resolve_install_version`, `yank_version`
- `apps/marketplace/webhooks.py` — `sign_payload`, `enqueue_event`,
  `deliver_once`, `deliver_due` with backoff `[30s, 2m, 10m, 30m, 2h, 6h]`,
  auto-disables endpoints at 20 consecutive failures
- `apps/marketplace/ratings.py` — `submit_rating`, `aggregate_for_app`,
  `publisher_reply`
- `apps/marketplace/partner_metrics.py` — installs / lifetime / churn / MRR /
  publisher_share / webhook health for partner dashboard

**New views (in `views_developer_platform.py`)**

- Public: `/marketplace/apps/<slug>/` (detail page with gallery + reviews +
  version history + install button)
- Public: `/marketplace/api/v1/catalog/` (search + facets JSON API; q, category,
  pricing, min_rating, sort=popular|newest|rating|name)
- Public: `/marketplace/publisher/signup/` (self-serve form + POST)
- Public: `/marketplace/publisher/verify-email/?token=…`
- Operator: `/super/marketplace/signups/` + decide endpoint
- Operator: `/super/marketplace/publisher/metrics.json`
- Operator: `/super/marketplace/publisher/webhooks/`

**Install path extended**: `install_app(..., target_version="2.1.0")` now resolves
through `AppVersion` and writes `installation.installed_version`. Tenant
install POST accepts a `target_version` param.

**Celery beat tasks added**

- `marketplace.webhook_deliver_due` — every 30s, drains 50 due deliveries

**Tests: 23** in `apps/marketplace/tests/test_developer_platform_v2.py`

---

## Move 2 — A real workflow engine

Migrations:
- `apps/orchestration/migrations/0002_workflow_engine_v2.py`
- `apps/automation/migrations/0019_workflow_versioning_v2.py`

**New models — apps/orchestration**

- `ProcessDefinitionVersion` — frozen snapshot of `ProcessDefinition` at publish
  time. Every `OrchestrationRun` now binds to a specific version via
  `definition_version` FK, so a re-deploy never disrupts in-flight runs.
- `OrchestrationStepEvent` — append-only event log (`run_created`, `run_started`,
  `step_started`, `step_succeeded`, `step_failed`, `retry_scheduled`,
  `run_completed`, `run_failed`, `run_cancelled`, `compensation_*`). Monotonic
  `sequence_number` per run.
- `OrchestrationSLOMetric` — rolled-up per-definition window snapshot with
  `runs_total / runs_succeeded / runs_failed / runs_sla_breached / p50/p95/p99
  latency_ms / queue_depth_max / success_rate`

**New services**

- `apps/orchestration/versioning.py` — `publish_new_version`,
  `current_version_for`, `bind_run_to_current_version`
- `apps/orchestration/event_log.py` — `emit`, `events_for`, `project_status`
- `apps/orchestration/slo_aggregator.py` — `aggregate_recent_window` writes one
  metric row per definition per window
- `apps/orchestration/tasks.py` — Celery wrappers:
  - `orchestration.process_due_runs` — wraps the existing mgmt command;
    Celery retries on transient errors
  - `orchestration.trigger_runs_for_definition`
  - `orchestration.aggregate_slos`

**New public HTTP API — `apps/orchestration/api.py`**

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/orchestration/api/runs/` | list / create runs |
| GET | `/orchestration/api/runs/<id>/` | run detail + projection |
| GET | `/orchestration/api/runs/<id>/events/` | event log |
| POST | `/orchestration/api/runs/<id>/cancel/` | cancel |
| POST | `/orchestration/api/runs/<id>/retry/` | retry |
| GET | `/orchestration/api/slo/` | SLO snapshot per definition |

**New models — apps/automation**

- `WorkflowVersion` — visual-workflow snapshot at publish time (full
  `{nodes:[], edges:[]}` payload), `is_current` flag, monotonic version_number
- `WorkflowStepEvent` — visual workflow append-only events
  (`condition_evaluated`, `action_started`, `action_succeeded`, `action_failed`,
  `delay_scheduled`, `completed`, `failed`)
- `Workflow.current_version`, `WorkflowRunLog.workflow_version` FK extensions

**New service**

- `apps/automation/visual_workflow_versioning.py` —
  `publish_visual_workflow_version`, `current_version_for`,
  `bind_run_to_current_version`

**Celery beat tasks added**

- `orchestration.process_due_runs` — every 60s, limit 50
- `orchestration.aggregate_slos` — every 5 minutes, window 60 minutes

**Tests: 14** (11 orchestration + 3 automation visual versioning)

Honest carve-out: the existing `BaseOrchestrationRunner` subclasses don't yet
emit `OrchestrationStepEvent` rows internally; the foundation is in place but
each runner needs an `event_log.emit(...)` call at its step boundaries. Same
for `visual_executor` and `WorkflowStepEvent`. That's instrumentation work
for the follow-up wave.

---

## Move 3 — Policy Decision Point + ABAC + field-level RLS

Migrations:
- `apps/policies/migrations/0007_policyrule_policydecisionlog_and_more.py`
- `apps/metadata/migrations/0011_fieldcatalogentry_compliance_tags_and_more.py`

**New models — apps/policies**

- `PolicyRule` — typed rule with `effect (allow|deny)`, `subject_match`,
  `action_match`, `resource_match`, `conditions[]`, `priority`. Lower number =
  higher priority; first-matching rule wins. Scoped to a tenant or platform-wide.
- `PolicyDecisionLog` — append-only audit row per decision; carries
  `decision_reason` (the human-readable explanation), `matched_rule` FK,
  subject/action/resource snapshot.

**New service — `apps/policies/pdp.py` (the single PDP)**

```python
from apps.policies.pdp import decide, allowed, require, Decision

d = decide(
    {"user_id": user.pk, "role": "TEACHER", "school_id": str(school.pk)},
    "read",
    {"entity": "student", "field": "ssn", "sensitivity_tier": "secret",
     "compliance_tags": ["pii", "ferpa"]},
    school=school,
)
# d.effect ∈ {"allow", "deny", "implicit_deny"}
# d.reason — human-readable explanation
# d.matched_rule_id — None when implicit-deny
```

`require(...)` raises `PermissionDenied` with the reason; `allowed(...)`
returns a bool. Every call writes a `PolicyDecisionLog` row.

**Rule DSL**

- `subject_match`: `{"role": "TEACHER"}` or `{"role_any": [...]}` or `{"user_id": 42}`
- `action_match`: `{"actions": ["read", "export"]}` (`"*"` matches anything)
- `resource_match`: `{"entity": "student"}` plus `field`, `compliance_tag`,
  `sensitivity_tier_at_or_above`
- `conditions`: list of `{"attr": "dotted.path", "op": "eq|ne|lt|lte|gt|gte|in|contains", "value": ...}`

**FieldCatalogEntry extensions**

- `sensitivity_tier ∈ {public, internal, restricted, confidential, secret}`
- `compliance_tags: list[str]` (e.g. `["pii", "ferpa", "gdpr_special"]`)
- `dlp_redaction_strategy ∈ {null, mask, hash, tokenize}`

**Field-level RLS via DLP — `apps/policies/dlp.py`**

- `redact_record(record, entity="student", subject=..., school=...)` — returns a
  copy of the dict with disallowed fields rewritten per their redaction strategy.
- `redact_iterable(rows, entity=..., subject=..., school=...)` — vectorized.

The PDP is consulted per field (no log entries for the field-level checks to
keep volume manageable). Public-tier fields pass through unconditionally.

**Tests: 11** in `apps/policies/tests/test_pdp_abac_dlp.py`. Covers
implicit-deny default, allow-rule role matching, priority ordering, wildcard
actions, condition predicates, audit row writing, `require()` raising
`PermissionDenied`, sensitivity-tier matching, and the three redaction
strategies (`mask`, `hash`, `null`).

---

## Move 4 — Close the help-center loop

**New signal handlers — `apps/feedback/signals.py`**

- `_email_submitters_on_release` — fires on `ReleaseNote.post_save`. Emails the
  union of (FeatureRequest submitters, FeedbackVote voters) for every related
  request when `notify_submitters=True`.
- `_email_submitter_on_state_change` — emails the submitter when a
  `FeedbackSubmission` transitions (uses an `updated_at − created_at > 1s`
  heuristic to skip the create-time signal).

Wired in `apps/feedback/apps.py::FeedbackConfig.ready()`.

**KB ranked search — `apps/portal/kb_search.py`**

- Backend-aware: Postgres `SearchVector + SearchRank` when available; otherwise
  Python-side TF-weighted scoring (title × 4 + summary × 2 + content × 1).
- `kb_search` view in `apps/portal/views_kb.py` now consults this ranker;
  legacy icontains fallback retained when the ranker yields nothing.

**Public status page**

- `/status/` — HTML page with last 30 days of `ReleaseNote` rows, top-voted
  `FeatureRequest` items, recent `AppAuditLog` incidents (7 day window).
- `/status/api/` — same data as JSON for monitoring tools.
- Public, no auth required.

**Tenant health dashboard**

- `/tenant-health/` — tenant-visible HTML page showing current
  `TenantHealthScore`, score history, open `TenantRiskAlert`s, and
  `TenantInterventionSuggestion`s.

**AutoTicketRule actually runs**

- `apps/customersuccess/auto_ticket_runner.py::run_all_rules()` — iterates
  active `AutoTicketRule` rows, evaluates the trigger
  (`HEALTH_BELOW`, `RISK_ALERT_RED`), and writes a `FeedbackSubmission`
  tagged `["auto_ticket_rule", "auto_ticket"]`.
- Wrapped in Celery task `customersuccess.run_auto_ticket_rules` and scheduled
  every 10 minutes.

**Vote button on roadmap**

- `templates/feedback/school_roadmap.html` — each `RoadmapItem` card now
  shows a vote-up button linked to the first associated `FeatureRequest`, with
  weighted_score + vote_count beside it.

**Tests: 6** in `apps/feedback/tests/test_helpcenter_loop_v4.py`. Covers
notification signal on release, no-email when flag is off, AutoTicketRule
firing on health threshold, KB ranker relevance ordering, public status
JSON.

---

## URL surface added

| Path | Move | Auth |
|---|---|---|
| `/marketplace/apps/<slug>/` | 1 | public |
| `/marketplace/api/v1/catalog/` | 1 | public |
| `/marketplace/publisher/signup/` | 1 | public |
| `/marketplace/publisher/verify-email/` | 1 | public |
| `/super/marketplace/signups/` | 1 | operator |
| `/super/marketplace/signups/<id>/decide/` | 1 | operator |
| `/super/marketplace/publisher/metrics.json` | 1 | publisher |
| `/super/marketplace/publisher/webhooks/` | 1 | publisher |
| `/orchestration/api/runs/` | 2 | session |
| `/orchestration/api/runs/<id>/{,events,cancel,retry}/` | 2 | session |
| `/orchestration/api/slo/` | 2 | session |
| `/status/` | 4 | public |
| `/status/api/` | 4 | public |
| `/tenant-health/` | 4 | session |

## Celery beat schedule entries added

| Task | Schedule |
|---|---|
| `orchestration.process_due_runs` | every 60s |
| `orchestration.aggregate_slos` | every 5 minutes |
| `marketplace.webhook_deliver_due` | every 30s |
| `customersuccess.run_auto_ticket_rules` | every 10 minutes |

## SW version

`sms-v3.27.0-four-strategic-moves-2026-05-18`.

---

# v3.27.2 polish wave (2026-05-18)

Follow-up wave addressing the explicit polish + risky items. **68 tests total** (was 57). All hygiene scanners exit 0.

## Polish (customer-visible)

**P1 — Ratings submission endpoint + form** — `apps.marketplace.views_developer_platform.submit_rating_view`
- POST `/marketplace/apps/<slug>/rate/` accepts `stars` (1–5) + `headline` + `body`
- Form embedded on `public_app_detail.html` for authenticated tenant users
- Returns JSON for AJAX callers; redirects otherwise
- `publisher_reply_view` lets publishers respond to a rating they own

**P2 — Webhook endpoint CRUD UI** — `webhook_endpoints_view`, `webhook_endpoint_edit_view`
- GET `/super/marketplace/publisher/apps/<slug>/webhooks/` lists endpoints with topics, failures, last-success
- POST creates with auto-generated HMAC secret via `webhooks.new_secret()`
- Actions: `toggle` (enable/disable), `rotate_secret`, `delete`
- Template: `templates/marketplace/webhook_endpoints.html`

**P3 — AppVersion publish UI** — `app_versions_view`
- GET `/super/marketplace/publisher/apps/<slug>/versions/` shows version history + publish form
- POST publishes a new semver with channel (stable/beta/alpha) + changelog
- Invalid semver bounces back with `messages.error`
- Template: `templates/marketplace/app_versions.html`

**P4 — Tenant catalog rewired to consume `/marketplace/api/v1/catalog/`**
- `templates/marketplace/tenant_app_catalog.html` ships a JS-progressive-enhancement bar
- Search input (debounced 220ms) + facets (pricing, sort, min_rating)
- Fetches `/marketplace/api/v1/catalog/` and re-renders the grid client-side
- On API failure restores the server-rendered grid (no degraded experience)
- Inline `<script>` carries `nonce="{{ csp_nonce }}"` per the zero-tolerance CSP gate

## Risky items, taken on safest path

**R1 — PDP runtime enforcement, advisory-first** — `apps/policies/enforcement.py`
- New `pdp_advisory(action, resource_kind)` decorator — calls `decide()` at request time, writes a `PolicyDecisionLog`, never blocks
- New `pdp_enforce(action, resource_kind)` decorator — same plus `raise PermissionDenied` on deny/implicit_deny
- Site-wide mode controlled by `settings.POLICY_PDP_ENFORCEMENT_MODE`:
  - `"off"` — both decorators short-circuit
  - `"advisory"` (default) — both decorators log; never raise
  - `"enforce"` — `pdp_enforce` blocks; `pdp_advisory` still only logs
- **Rollout pattern**: ship with `advisory` everywhere; collect a week of `PolicyDecisionLog` rows; backfill rules until the would-be-deny rate is zero on legitimate paths; flip the env var to `enforce`. Single config change, no code change.
- Test coverage: 4 tests in `apps/policies/tests/test_enforcement_decorators.py`

**R2 — DRF JWT alongside Session on orchestration API** — `apps/orchestration/auth_helpers.py`
- New `accept_session_or_jwt` decorator on all `/orchestration/api/...` views
- If `request.user.is_anonymous` and `Authorization: Bearer <jwt>` is present, hydrate via SimpleJWT (already in `INSTALLED_APPS`)
- Returns `401 {"error":"authentication_required"}` if neither auth path produces an authenticated user
- Session callers continue to work unchanged; third parties get a token via the existing `/api/auth/token/` endpoint
- No new credential storage — token issuance reuses the project's SimpleJWT config

## "Just execution" items

**E5 — Dead-stub audit** — verdict: nothing to delete
- `apps/migration_cloud/tier3.py::stage_rollout_plan` is functional (writes to `bundle.size_summary` JSON); the memory entry calling it a "stub" pre-dated the implementation
- The "Phase 10 synchronous management-command runner" is now superseded by `apps/orchestration/tasks.py` + `OrchestrationStepEvent` event log (v3.27 Move 2)
- No orphan code to remove

**E6 — LMSAssignment** — already shipped: `apps/academics/models_lms.py::LMSAssignment` (line 46) + `LMSSubmission` (line 152) exist and are wired
**E7 — OneRoster + LTI 1.3 adapters** — already shipped:
- `apps/interop/oneroster/{adapter,auth_resolution,constants,webhook_dispatch}.py`
- `apps/interop/lti/adapter.py`
**E9 — Blueprint rollback** — already shipped: `apps/platform_runtime/blueprint_rollback.py::rollback_blueprint_installation`

**E8 — Declarative tenant-override loader** (newly shipped):
- `apps/policies/declarative_overrides.py::apply_overrides_dict(payload, prune=False)`
- `apply_overrides_file(path)` accepts JSON (always) or YAML (when PyYAML installed)
- Schema:
  ```json
  {
    "version": 1,
    "overrides": [
      {"school": "gilead-tech-high", "policy_key": "admissions.numbering", "value": {...}}
    ]
  }
  ```
- Idempotent: re-applying the same file is a no-op (creates / updates / unchanged / pruned counts in `ApplyResult`)
- New mgmt command: `python manage.py apply_tenant_overrides path/to/file.json [--prune] [--json]`
- 6 tests in `apps/policies/tests/test_declarative_overrides.py`

## Test counts

| Suite | Count |
|---|---|
| `apps/marketplace/tests/test_developer_platform_v2.py` | 23 |
| `apps/orchestration/tests/test_workflow_engine_v2.py` | 11 |
| `apps/orchestration/tests/test_runner_instrumentation_v2.py` | 3 |
| `apps/automation/tests/test_visual_workflow_versioning_v2.py` | 3 |
| `apps/policies/tests/test_pdp_abac_dlp.py` | 11 |
| `apps/policies/tests/test_enforcement_decorators.py` | 4 |
| `apps/policies/tests/test_declarative_overrides.py` | 6 |
| `apps/feedback/tests/test_helpcenter_loop_v4.py` | 6 |
| **Total** | **68** |

## SW version (this wave)

`sms-v3.27.2-strategic-moves-polish-2026-05-18`.

## Hygiene

All 6 hygiene scanners exit 0 (print, bare-except, assert-in-production, money-float, role-strings unchanged, magic-numbers unchanged). CSP nonce baseline holds — inline script in `tenant_app_catalog.html` carries `nonce="{{ csp_nonce }}"`.

