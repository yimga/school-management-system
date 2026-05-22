# RunMyCampus Workflow How-To System (v3.59.x Phase 2 spec)

_Spec-of-record for the workflow-guidance system that landed in Phase 3 of the v3.59.x platform-wide workflow audit. Grounded in code-truth: this doc describes what the modules at [`apps/platform_runtime/workflow_registry.py`](../../apps/platform_runtime/workflow_registry.py), [`apps/platform_runtime/workflow_guidance.py`](../../apps/platform_runtime/workflow_guidance.py), the four scaffold templates under [`templates/components/`](../../templates/components/), and the [`rmc-workflow-guidance.css`](../../static/css/rmc-workflow-guidance.css) bundle actually do — not aspirational._

## 0. Why this exists

The original v3.59.x audit prompt treats every "how do I do this?" moment as a real product workflow, not just documentation. That means:

- Every workflow needs a single source of truth (the **registry**).
- Every workflow surface needs **context-aware guidance** (purpose, primary action, next-best action, blockers, completion state).
- Every workflow needs **information tags** that explain *what kind of step this is* (required / optional / blocks-launch / tenant-safe / platform-only / approval-required / etc.).
- AI assistance must be **route-aware** and **evidence-citing**, not generic.
- The system must be **tenant-safe**: platform-only workflows must never surface to tenant users; AI must never cross the tenant boundary.

This doc specifies the system. Phase 3 implemented it as in-process scaffolding (not yet wired into shells). Phase 4 wires it.

## 1. Workflow registry

**Module:** [`apps.platform_runtime.workflow_registry`](../../apps/platform_runtime/workflow_registry.py) (542 lines, in-process data, no DB model, no migration).

**Schema** — `WorkflowDefinition` dataclass (frozen):

| Field | Type | Purpose |
|---|---|---|
| `key` | `str` (kebab-case slug) | Stable identifier — never change after first ship |
| `title` | `str` | Human-readable name (e.g. "Connect SIS via Migration Cloud") |
| `audience` | `frozenset[str]` | Surface-kind labels from the 7-audience constant set: `operator`, `tenant-admin`, `teacher`, `parent`, `student`, `founder`, `public` |
| `module` | `str` | Owning app path (e.g. `apps/migration_cloud/`) |
| `route` | `str` | Entry-point URL pattern (e.g. `/super/migration/connectors/`) |
| `purpose` | `str` | One sentence — what this workflow accomplishes |
| `prerequisites` | `tuple[str, ...]` | Other workflow keys or condition labels that must be true first |
| `steps` | `tuple[WorkflowStep, ...]` | Ordered steps (each with `key`, `label`, `description`, `cta_label`, `cta_url_name`) |
| `success_state` | `str` | What "done" looks like (e.g. `receipt_emitted`, `tenant_provisioned`) |
| `required_permissions` | `tuple[str, ...]` | RBAC tokens from `role_registry` |
| `related_help_article` | `Optional[str]` | KB slug if a help article exists |
| `related_feedback_route` | `Optional[str]` | URL name in `apps.feedback` to capture feedback |
| `related_audit_event` | `Optional[str]` | Audit-event class name (e.g. `migration.maa.sign`) |
| `related_ai_context_key` | `Optional[str]` | Context key the AI gateway uses when responding |
| `external_blockers` | `tuple[str, ...]` | Externally-blocked items (counsel signoff, vendor write-paths) |

**Authoritative table:** the `WORKFLOWS: dict[str, WorkflowDefinition]` module-level constant. **Seed set today: 16 workflows** spanning Studio OS modes (5), Migration Cloud (3), parent portal (2), teacher (1), billing (1), marketplace (1), support/help (1), operator lifecycle (1), Studio OS hub navigation (1). Re-seed via the `rebuild_from_classification_matrix(...)` extension point when Phase 1's 112-workflow matrix is promoted into the registry.

**Why in-process, not DB:** matches existing patterns — `role_registry`, `wedge_line_registry`, `rmc_os_nav_registry` are all code-truth. Per-tenant overrides land in `SiteSettings.cockpit_payload` (v3.56.0 pattern) when the operator UI for editing workflow visibility ships in Phase 4+.

## 2. Workflow guidance service

**Module:** [`apps.platform_runtime.workflow_guidance`](../../apps/platform_runtime/workflow_guidance.py) (411 lines).

**Public surface:**

- `get_workflow(key: str) -> Optional[WorkflowDefinition]` — look up by key.
- `resolve_workflow_for_route(request) -> Optional[WorkflowDefinition]` — given a Django request, find which workflow's `route` matches `request.resolver_match.view_name` (or pattern).
- `is_visible_for(request, workflow) -> bool` — **3-layer visibility gate** (v3.56.0 pattern):
  1. **Host kind** — `request.public_host_kind` ∈ {`tenant`, `manager`, `marketing`, `docs`, `api`} matches one of the workflow's `audience` surface kinds.
  2. **Section enable flag** — `SiteSettings.cockpit_payload.workflow_guidance.<workflow_key>.enabled` (defaults `True`, can be disabled per-tenant by operator).
  3. **Per-page block override** — template can override with `{% block workflow_guidance %}{% endblock %}`.
- `tags_for(request, workflow) -> list[dict]` — returns the active tag set (from the 19-tag taxonomy), already filtered by visibility. **Platform-only tags are stripped on tenant hosts.**
- `next_action_for(request, workflow) -> Optional[dict]` — returns `{label, url, blocker, blocker_reason}`. Used by `workflow_next_action.html`.
- `help_panel_for(request, workflow) -> Optional[dict]` — returns the how-to-panel payload (purpose / before-you-start / common-blockers / what-happens-next / help-link / feedback-link).

## 3. Tag taxonomy (the 19 from the prompt + 1)

**Module constants in `workflow_registry`** (slug = constant value):

| Tag | Slug | When to surface |
|---|---|---|
| Required | `required` | This step must complete before the workflow can succeed. |
| Optional | `optional` | The user can skip and still complete. |
| Blocks Launch | `blocks-launch` | Surfaces on Studio OS Launch mode + workflow status strips when a launch blocker. |
| Needs Review | `needs-review` | A draft / staged change is waiting on approver. |
| Tenant Safe | `tenant-safe` | Confirms tenant-isolation posture for the workflow. |
| Platform Only | `platform-only` | Operator-only surface — **must never render to tenant** (enforced by `is_visible_for`). |
| Preview Available | `preview-available` | A `preview_url` exists; user can preview before applying. |
| Approval Required | `approval-required` | Touches an `ApprovalWorkflow` chain. |
| External Required | `external-required` | Blocked on counsel signoff / vendor / third party. |
| Manual Fallback | `manual-fallback` | A manual path exists when the automated path fails (e.g. cash receipts when PSP is offline). |
| AI Help Available | `ai-help-available` | `related_ai_context_key` is set and `services.ai_helpers` is wired in the owning app. |
| Data Quality Issue | `data-quality-issue` | Detected by registry validation; user must resolve before proceeding. |
| Billing Impact | `billing-impact` | Workflow touches billable usage / subscription tier. |
| Audit Logged | `audit-logged` | `related_audit_event` is set; this action will land in the audit log. |
| Reversible | `reversible` | A `rollback` / `undo` route exists. |
| Not Reversible | `not-reversible` | Destructive; no undo. Pair with **Approval Required** when possible. |
| Draft | `draft` | Resource exists but not published. |
| Published | `published` | Resource is live for the audience. |
| Missing Setup | `missing-setup` | Prerequisite workflow not yet complete. |
| Ready to Launch | `ready-to-launch` | All checks green; primary CTA is the launch button. |

**Visual contract** (lives in [`static/css/rmc-workflow-guidance.css`](../../static/css/rmc-workflow-guidance.css)):
- Each tag is an accessible chip with text label (never icon-only).
- Color is semantic via `var(--*)` tokens — no off-token literals.
- WCAG AA contrast (≥4.5:1) — enforced by `scan_color_contrast.py`.
- Dark/light parity — themes set on `[data-theme=...]`.
- No `position: sticky` + `overflow: hidden` combos (enforced by `scan_sticky_with_overflow_hidden.py`).

## 4. Reusable template components

Four scaffolded partials under [`templates/components/`](../../templates/components/):

| Partial | Purpose | Phase-4 wiring target |
|---|---|---|
| [`workflow_info_tag.html`](../../templates/components/workflow_info_tag.html) | Render one accessible tag chip from a `{key, label, variant}` dict | Above the hero on every workflow page |
| [`workflow_help_panel.html`](../../templates/components/workflow_help_panel.html) | Sidebar/drawer panel with purpose / before-you-start / common-blockers / what-happens-next / help-link / feedback-link | Right-rail or `{% block workflow_help %}` slot |
| [`workflow_next_action.html`](../../templates/components/workflow_next_action.html) | Primary-action + next-best-action + blocker-state strip | Top of workflow page, below hero |
| [`workflow_status_strip.html`](../../templates/components/workflow_status_strip.html) | Current step + completion state + owner badge | Under hero or in compact header |

All four follow:
- Django template syntax (verified by `audit_template_render_safety.py`).
- CSP-safe — no inline `<script>` (any inline scripts require `nonce="{{ csp_nonce }}"` enforced by `verify_csp_nonce_emission.py`).
- Use the `.rmc-workflow-*` class grammar (extends `static/css/rmc-class-grammar.css`).
- Are gated by `workflow_guidance.is_visible_for` before render (never rendered for the wrong audience).

## 5. Inline guidance contract

Every workflow page (Phase 4 wiring) exposes:

```
{% load workflow_guidance %}
{% workflow_resolve as wf %}
{% if wf and wf|is_visible_for:request %}
  {% include "components/workflow_status_strip.html" %}
  {% include "components/workflow_info_tag.html" with tags=wf|tags_for:request %}
  {% include "components/workflow_next_action.html" with action=wf|next_action_for:request %}
  {% include "components/workflow_help_panel.html" with panel=wf|help_panel_for:request %}
{% endif %}
```

Phase 4 will land the template tag library (`workflow_guidance` template tags) that exposes `is_visible_for` / `tags_for` / `next_action_for` / `help_panel_for` as filters.

## 6. AI integration rules

**Boundary:** all AI calls route through `services.ai_helpers` — NEVER `services.ai_gateway` directly. Enforced by `scripts/scan_ai_gateway_boundary.py` (CI baseline 0). The 4 allowlisted infra exceptions (`apps/portal/ai_provider.py`, `apps/portal/views_ai_gateway.py`, `apps/migration_cloud/ai_bridge.py`, `apps/platform_runtime/ai_providers.py`, `apps/siteconfig/management/commands/aggregate_ai_metrics.py`) are the only places that import the gateway directly.

**Contract** — when a workflow has `related_ai_context_key` set, AI guidance MUST:

1. Receive the workflow object (key, route, audience, current step) as structured context.
2. Receive `request.user.role` (via `role_registry`), `request.tenant`, `request.public_host_kind`.
3. Receive the readiness/blocker state for the current step.
4. Return an action object: `{label, url, evidence_id, blocker_reason?, workflow_key}`.
5. **NEVER** cross the tenant boundary — gateway calls always pass `tenant_id` (or hashed equivalent for metrics).
6. **NEVER** generate destructive actions — destructive intents return a confirmation-required action with `reversible: false` instead of executing.

When the gateway is offline or no `related_ai_context_key` is set, the system falls back to the **rules-based copilot rail** at `apps/studio_os/copilot_rail_service.py` — same 6-bucket structure, deterministic next-actions.

**DATA DEFAULTER posture:** when an AI call lacks context (no tenant, no role, no readiness state), the helper returns `{label: "Pick a starting point", url: workflow.route, evidence_id: null}` rather than fabricating.

**FEATURE CODESPACE DISCONNECT posture:** when the feature backing a workflow is genuinely absent (e.g. `WorkflowPack.is_active` field not present), helpers return `service_online=False` (the v3.39.0 + v3.54.0 pattern) so the UI can render an "unknown" chip instead of "0".

## 7. Cascade integration (the 7-layer pattern)

Workflow context is emitted following the existing platform cascade:

```
RuntimeDefaults typed column (apps/platform_runtime/runtime_defaults_first_class.py)
  → migration (none required — code-truth registry)
  → RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES (registry keys live here once promoted)
  → EXACT_FIELD_OWNERS map
  → SiteSettings.cockpit_payload.workflow_guidance (per-tenant override slot, v3.56.0 pattern)
  → context processor (apps/siteconfig/context_processors.py emits `workflow_guidance`)
  → meta-tag bridge (already present in templates/partials/rmc_theme_meta.html)
  → CSS custom property on <html> (set by theme-preference-bootstrap.js)
  → CSS rule that consumes it (rmc-workflow-guidance.css)
```

## 8. 3-layer visibility gate

Every workflow chip / panel / next-action element passes through:

1. **Host kind** — `request.public_host_kind` matches one of `workflow.audience` (operator-only on manager.runmycampus.com, tenant-side on tenant subdomains).
2. **Section enable flag** — `cockpit_payload.workflow_guidance.<key>.enabled` (default True; operator can per-tenant disable).
3. **Per-page block override** — template can shadow with `{% block workflow_guidance %}{% endblock %}` for special cases.

If any gate returns False, the workflow guidance does not render. **Platform-only workflows on tenant hosts: gate 1 short-circuits.** This is the same model the cockpit context uses.

## 9. Tests Phase 3 should have shipped (deferred to Phase 11)

- `apps.platform_runtime.tests.test_workflow_registry` — registry well-formed, no duplicate keys, all audiences valid, all tag references resolve
- `apps.platform_runtime.tests.test_workflow_info_tags` — taxonomy ↔ CSS class names align; no off-token literals
- `apps.platform_runtime.tests.test_workflow_guidance_contracts` — visibility gate, tenant-safety, next-action shape
- `apps.platform_runtime.tests.test_operator_workflow_contracts` — operator-only workflows return False from `is_visible_for` on tenant hosts
- `apps.platform_runtime.tests.test_tenant_workflow_contracts` — tenant-safe workflows visible on tenant hosts
- `apps.studio_os.tests.test_studio_os_workflow_guidance` — Studio OS mode workflows resolve correctly
- `apps.apicenter.tests.test_ai_workflow_assistant` — AI bridge respects evidence-id contract
- `apps.feedback.tests.test_workflow_feedback_help_links` — `related_feedback_route` resolves
- `apps.migration_cloud.tests.test_migration_workflow_guidance` — migration workflows expose audit events
- `apps.billing.tests.test_billing_workflow_guidance` — billing workflows carry `billing-impact` tag
- `apps.compliance.tests.test_compliance_workflow_guidance` — compliance workflows carry `audit-logged` tag

## 10. Phase 4 wiring plan (next wave)

Wire the four components into representative pages:

| Page | Workflow key | Components to land |
|---|---|---|
| `templates/studio_os/modes/output.html` | `studio-os-output` | Adds `_mode_hero` include (mode_label='Outputs') + status_strip + next_action + info_tag + help_panel (closes OP-1 from Phase 7 audit) |
| `templates/migration_cloud/connector/_wizard_base.html` | `migration-cloud-connect-sis` | status_strip + info_tag + help_panel |
| `templates/portal/parent_dashboard.html` | `parent-portal-pay-invoice` | next_action + info_tag (manual-fallback, billing-impact) |

Phase 4 does NOT attempt to wire all 16 seeded workflows — that's an explicit follow-up wave. The proof-of-concept demonstrates the shape; broader rollout is by-workflow over multiple waves.

## 11. Honest deferrals

- **Operator UI** for editing `SiteSettings.cockpit_payload.workflow_guidance.<key>.enabled` per-tenant — Phase 5/6 audit recommendation, not Phase 3 scope.
- **Per-tenant override migration** — when the operator UI lands, a migration adds `cockpit_payload.workflow_guidance` to the existing JSON column; no new column needed.
- **Promoting Phase 1's 112-workflow matrix into the registry** — `rebuild_from_classification_matrix(...)` extension point exists; promotion is operator review work (each workflow needs hand-verified audience + step list + permissions).
- **Tests** (the 11 modules listed in §9) — Phase 11.
- **E2E browser QA** — Phase 12 needs `tests/e2e/workflow-guidance.spec.js`.

## 12. Verification expectations

When Phase 4 wiring lands, these gates MUST stay green:

| Gate | Why it matters here |
|---|---|
| `audit_template_render_safety.py` (baseline 0) | New component templates must be clean |
| `scan_off_token_colors.py` (baseline 0) | `rmc-workflow-guidance.css` must not introduce off-token literals |
| `scan_pii_logging_smell.py` (baseline 0) | Guidance service must not log workflow context fields containing PII |
| `scan_ai_gateway_boundary.py` (baseline 0) | AI calls in guidance helpers must go through `services.ai_helpers` |
| `scan_csp_nonce_emission.py` (baseline 0) | Any inline scripts get `nonce` |
| `scan_tenant_queryset_safety.py` (baseline 0) | Workflow registry has no DB queries; if guidance helpers ever add them, they must be tenant-scoped |
| `verify_service_worker_version.py` | Bump on the wave that ships the Phase 4 wiring |
| `scan_sticky_with_overflow_hidden.py` (baseline 0) | Components must not introduce sticky+clip traps |

---

**This spec describes what Phase 3 actually landed.** No aspirational features. Phase 4+ work is explicitly marked as deferred.
