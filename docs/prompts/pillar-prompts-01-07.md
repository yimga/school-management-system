# Seven-Pillar Prompts + CTO Synthesis

**Pack:** `2026-05-20-orchestrator-v5`  
**Gear-up (mandatory before pillar work):** [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md), [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md), [`00-gear-up-v5-transformational.md`](00-gear-up-v5-transformational.md)

**Source plans:** [seven-pillar platform audit](.cursor/plans/seven-pillar_platform_audit_99bb91a1.plan.md), [9-agent moderator wave](.cursor/plans/9-agent_moderator_wave_11e58d68.plan.md)  
**Audit of record:** [`docs/PLATFORM_AUDIT_12_PILLARS_2026_05_17.md`](../PLATFORM_AUDIT_12_PILLARS_2026_05_17.md)

Paste the relevant pillar section with global rules + all three gear-up layers when an agent is mapped (see README).

---

## Prompt 1 — Design System & Dynamic Theme (P1)

**Agents:** 3, 8

**Role:** Principal Design System Architect for runmycampus.com.

**Paste bundle:**

- [`static/css/design-tokens.css`](../../static/css/design-tokens.css)
- [`static/js/theme-preference-bootstrap.js`](../../static/js/theme-preference-bootstrap.js)
- [`templates/partials/rmc_theme_meta.html`](../../templates/partials/rmc_theme_meta.html)
- [`static/css/dark-mode-safety-net.css`](../../static/css/dark-mode-safety-net.css) (first 120 lines)
- One shell head: [`templates/marketing/base_marketing.html`](../../templates/marketing/base_marketing.html) L1–35

**Run:** `scan_inline_style_off_token.py`, `scan_off_token_colors.py`, `scan_undefined_css_classes.py` (baseline **0**)

**Deliverables:** Visual bug table → [`docs/THEME_VISIBILITY_BURNDOWN.md`](../THEME_VISIBILITY_BURNDOWN.md) or [`docs/CSS_RETIREMENT_DOCKET.md`](../CSS_RETIREMENT_DOCKET.md); token schema → [`docs/THEME_CANONICAL_TOKENS.md`](../THEME_CANONICAL_TOKENS.md)

**Order rule:** token → meta → JS on `<html>` → shell → component

---

## Prompt 2 — UX Frontend & Accessibility (P2)

**Agent:** 8

**Per-surface widgets:** marketing nav + `/trust/`; manager cmdk/section-nav; tenant data-table or tour modal.

**CI extend:** [`.github/workflows/a11y-axe.yml`](../../.github/workflows/a11y-axe.yml), `pa11y-ci.yml`, `lighthouse-ci.yml` (+ manager URLs, `LHCI_URL`)

**Gaps:** manager.runmycampus.com in axe; 400% zoom on finance invoice + teacher grade grid.

---

## Prompt 3 — Multi-Tenant Backend & API (P3)

**Agents:** 2, 4

**Paste:** `config/settings.py`, [`apps/accounts/permissions.py`](../../apps/accounts/permissions.py), hot views, [`docs/generated/role_permission_matrix.json`](../generated/role_permission_matrix.json), `scan_tenant_queryset_safety.py` (baseline **0**)

**Scope IDs:** `school_id`, `Client.schema_name`, `district_id` — never client-only tenant params.

---

## Prompt 4 — Data Pipeline & Workflow Engine (P4)

**Agents:** 6, 9

**Paste:** [`apps/automation/workflow_trigger_catalog.py`](../../apps/automation/workflow_trigger_catalog.py), migration `0018`, [`apps/events/webhooks.py`](../../apps/events/webhooks.py), analytics tasks, Celery beat.

**Focus:** `offline_action_conflict` loop; webhook idempotency keys.

---

## Prompt 5 — FinTech & Transactional Ledger (P5)

**Agent:** 5

**Paste:** [`apps/finance/views_payments.py`](../../apps/finance/views_payments.py), [`apps/finance/models.py`](../../apps/finance/models.py), [`payment/`](../../payment/)

**Gate:** `scan_money_float.py` baseline **0**

---

## Prompt 6 — Cloud DevOps & Platform Reliability (P6)

**Agents:** 0, 1, Moderator

**Paste:** [`scripts/release/render_predeploy.sh`](../../scripts/release/render_predeploy.sh), [`docs/DEPLOY_PIPELINE_RUNBOOK.md`](../DEPLOY_PIPELINE_RUNBOOK.md), [`architectural-boundaries.yml`](../../.github/workflows/architectural-boundaries.yml), `verify_migration_files_tracked.py`

**Note:** Render bash predeploy — K8s sections N/A unless Dockerfile exists.

---

## Prompt 7 — Security & Privacy (P7)

**Agents:** 1, 2

**Paste:** OIDC/SAML/trust/GDPR views, `PASSWORD_HASHERS`, [`apps/compliance/`](../../apps/compliance/), [`docs/generated/security_exception_register.json`](../generated/security_exception_register.json)

**Plus:** document `pip_audit` CVE backlog honestly.

---

## Executive CTO Synthesis (Moderator, after Agent 9)

**Input:** All pillar + stage deliverables.

**Output (repo discipline only):**

1. **P0–P3 matrix** → SOT §11.4 rows (no parallel master plans)
2. Cross-architecture deps (token → SiteSettings → API serializers)
3. 2-week sprint DoD = named `verify_*` / `manage.py test` green
4. Guardrail table:

| Tool | Pillar |
|------|--------|
| `verify_migration_files_tracked.py` | P6 |
| `a11y-axe.yml` manager URLs | P2 |
| `scan_money_float.py` | P5 |
| `verify_ai_engine_room.py` | Stage 9 |
| `verify_five_pillar_platform_completion.py` | P3–P7 |

5. `python scripts/generate_system_closure_map.py --write`

**Verdict line for SOT:** CTO SYNTHESIS COMPLETE — P0–P3 BACKLOG IN §11.4


---

## REPORT BACK TO ORCHESTRATOR

Paste this block at the end of every worker session (max 40 lines body + verdict):

```text
STAGE: <N>
AGENT: <id>
GIT_SHA: <short>
SOT_BATCH_DRAFT: <131X if proposing>

A — Discovery: <what was inspected>
B — Gaps found: <count + top 3>
C — Fixes made: <summary>
D — Security/tenant: <PASS|FAIL + note>
E — UI/UX: <PASS|N/A + note>
F — Tests: <commands + OK/FAIL counts>
G — Verifiers: <list + PASS/FAIL>
H — Artifacts: <docs/generated/*.json paths>
I — SOT draft: <one-line verdict string only — Moderator commits>
J — Remaining gaps: <honest partials + EXTERNAL>
K — Files changed: <count + top paths>
L — Verdict: FAILURE | PARTIAL | READY — FOCUSED REPO SCOPE | READY — REPO SCOPE

RERUN_REQUIRED: yes|no
BLOCKERS: <none|list>
```

Moderator updates [`docs/generated/orchestrator_execution_matrix.json`](../generated/orchestrator_execution_matrix.json) after accepting a stage.
