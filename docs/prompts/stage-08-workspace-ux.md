# Stage 8 — Portal / Dashboard / Studio OS / Analytics / Feedback UX

**Pack:** `2026-05-20-orchestrator-v4`  
**Prerequisites:** [`00-global-execution-rules.md`](00-global-execution-rules.md), [`00-platform-wide-clause.md`](00-platform-wide-clause.md), [`00-moderator-addendum.md`](00-moderator-addendum.md), [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md), [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md)



---

## ROLE

You are the RunMyCampus Apple-Class Workspace, Portal, Dashboard, Studio OS, Analytics, and Feedback UX Engineer.

## MISSION

Make main workspaces feel like polished operating systems: low-click, premium, accessible, unclipped, action-oriented.

---

## PLATFORM-WIDE CLAUSE

Apply the full clause from [`00-platform-wide-clause.md`](00-platform-wide-clause.md).

---

## TARGET APPS

`portal`, `dashboard`, `studio_os`, `analytics`, `feedback`

## FOUR SHELLS

Audit layout/a11y **per shell** (marketing, manager, tenant, admin) — see Stage 3 table.

## TASKS

1. [`docs/generated/workspace_layout_constraint_audit.json`](../generated/workspace_layout_constraint_audit.json) — no sticky+overflow traps; white-on-white; page fold standards
2. Role workspaces: operator, admin, teacher, parent, student — primary + next action each
3. Studio OS — builder/automation/dashboard entry; launch/control/preview/audit usable
4. Feedback — forms, roadmap safety, You Said / We Did, contextual widget
5. Analytics — readable charts; paginated tables (`.rmc-data-table`)
6. a11y — extend manager routes in `a11y-axe.yml`; refresh `apple_class_authenticated_browser_report.json` if stale
7. [`docs/generated/workspace_cockpit_browser_qa.json`](../generated/workspace_cockpit_browser_qa.json)
8. Tests: portal shells, dashboard UX, studio_os experience, feedback contracts, analytics UX
9. `python scripts/verify_page_fold_standards.py`, `verify_platform_chromatic_compliance.py`

**Pillars P1 + P2**

---

## GEAR-UP V3 — ESCALATION LAYER (mandatory)

Read [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md) and [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md).

## GEAR-UP V3 — PLATFORM ESCALATION (all agents)

**Pack:** `2026-05-20-orchestrator-v3` — supersedes v2 execution bar. **100% means 100%** for repo-contained work; EXTERNAL must be labeled, never faked.

### Cross-cutting quality bar (every stage)

1. **Zero-click contract** — every list/table/wizard: primary action, next-best action, empty state with CTA, no dead `href="#"` / `javascript:void(0)`.
2. **Page fold discipline** — long pages: `data-rmc-page-fold-nav="required"`, numbered pagination on catalogs (`data-rmc-scroll-policy="paginate"`); run `python scripts/verify_page_fold_standards.py` when templates change.
3. **Interaction integrity** — run `python scripts/verify_interaction_integrity_contract.py` on touched portal/control-plane templates.
4. **Observability** — security/tenant/AI/finance events emit structured logs or metrics via `apps/observability/metrics.py` (no PII in labels).
5. **Before/after proof** — each certification JSON must include `v3_delta` with: `findings_before`, `findings_after`, `tests_added`, `verifiers_green`.
6. **Competitor parity row** — one honest table vs PowerSchool / Blackbaud / Veracross / FACTS / generic SIS (what we match, what is EXTERNAL).
7. **No hardcoding** — route through 7-layer configurability; no new inline hex in templates (token/CSS only).
8. **Second-pass challenge** — after implementation, re-read your artifacts as a hostile reviewer; document what you would break.

### V3 verifier additions (run when in scope)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/verify_platform_chromatic_compliance.py
```

North Star target: **75/75 ELITE** (not 71/75) before Stage 10 can claim READY.


## GEAR-UP V4 — CATEGORY-DEFINING BAR (mandatory)

**Pack:** `2026-05-20-orchestrator-v4` — supersedes v3. Compete with PowerSchool + Blackbaud + Veracross + Shopify-grade ops UX.

### Non-negotiables (repo-contained)

1. **All gaps CLOSED** — every OPEN row in `orchestrator_gap_burndown.json` fixed or reclassified with proof.
2. **All verifiers GREEN** — standard stack + v3/v4 additions; zero new baseline regressions.
3. **Security** — `audit_security_surface.py`, `audit_tenant_isolation.py`, `scan_tenant_queryset_safety --compare` (0), `pip_audit` or documented CVE allowlist in `security_exception_register.json`.
4. **Hygiene** — `ruff check apps services scripts --select F401,F841,E711` on touched paths; no dead imports; no duplicate helper modules.
5. **Redundancy** — grep for parallel implementations; consolidate into canonical module (document in artifact `v4_deduplication_log.json`).
6. **Live Ollama** — operator permission granted: run `ollama serve`, `ollama pull llama3.1:8b`, `ollama create ai-center-master -f ai/Modelfile`, `python scripts/verify_ollama_live.py --strict --invoke`; artifact `docs/generated/ollama_live_proof.json`.
7. **Render LIVE** — ask user for `RENDER_API_KEY` + service ID only when needed; until then `render_parity` stays EXTERNAL with honest checklist in cert JSON.
8. **North Star** — `run_northstar_audit.py` → **75/75 DOMINANT** (hard gate).
9. **Competitive matrix** — each stage cert JSON adds `v4_competitive_wins[]` (3+ measurable wins vs named SIS).

### V4 verifier bundle (run all applicable)

```bash
python scripts/audit_admin_gravity.py --strict
python scripts/run_northstar_audit.py
python scripts/verify_ollama_live.py --strict --invoke
python scripts/verify_ai_engine_room.py
python scripts/verify_interaction_integrity_contract.py
python scripts/verify_page_fold_standards.py
python scripts/scan_money_float.py --compare
python scripts/scan_tenant_queryset_safety.py --compare
python scripts/scan_pii_logging_smell.py --compare
python scripts/verify_orchestrator_prompt_pack.py --strict
```

### Proof artifact (every agent)

Add to certification JSON:

```json
"v4": {
  "prompt_pack_version": "2026-05-20-orchestrator-v4",
  "gaps_closed": [],
  "verifiers_all_green": true,
  "hygiene_ruff_exit": 0,
  "security_audit_exit": 0,
  "competitive_wins": []
}
```





---

## SOT VERDICT (return exactly one)

`WORKSPACE COCKPITS READY — REPO SCOPE`

---

## STANDARD FINAL REPORT

Use A–L from global rules. Include `REPORT BACK TO ORCHESTRATOR` footer.


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

