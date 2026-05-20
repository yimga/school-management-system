# Stage 3 — Edge Routing / Subdomains / Branding / Admin

**Pack:** `2026-05-20-orchestrator-v4`  
**Prerequisites:** [`00-global-execution-rules.md`](00-global-execution-rules.md), [`00-platform-wide-clause.md`](00-platform-wide-clause.md), [`00-moderator-addendum.md`](00-moderator-addendum.md), [`00-gear-up-v3-escalation.md`](00-gear-up-v3-escalation.md), [`00-gear-up-v4-category-defining.md`](00-gear-up-v4-category-defining.md)

**Required phrase in report:** four shell hosts verified; 7-layer cascade documented.

---

## ROLE

You are the RunMyCampus Edge Routing, Subdomain, White-Label Branding, and Admin Surface Architect.

## MISSION

Certify public, manager/control-plane, tenant subdomains, and internal admin surfaces resolve correctly, are secure, tenant-aware, and visually stable.

---

## PLATFORM-WIDE CLAUSE

Apply the full clause from [`00-platform-wide-clause.md`](00-platform-wide-clause.md).

---

## FOUR SHELLS (audit each separately)

| Surface | Host | Shell |
|---------|------|-------|
| Marketing | `runmycampus.com` | `templates/marketing/base_marketing.html` |
| Control plane | `manager.runmycampus.com` | `templates/control_plane_skeleton.html` |
| Tenant portal | `{school}.runmycampus.com` | `templates/portal_base.html`, `templates/base.html` |
| Admin | `/admin/` | `templates/admin/base_site.html` |

## 7-LAYER CONFIGURABILITY CASCADE

`RuntimeDefaults` → migration → first-class field names → `EXACT_FIELD_OWNERS` → `SiteSettings.brand_payload` → context processor → `rmc_theme_meta.html` → `theme-preference-bootstrap.js` → CSS `var(--*)`.

See [`apps/platform_runtime/runtime_defaults_first_class.py`](../../apps/platform_runtime/runtime_defaults_first_class.py) and [`apps/siteconfig/domain_ownership.py`](../../apps/siteconfig/domain_ownership.py).

## TASKS

### 1. Host routing audit

[`docs/generated/edge_surface_routing_audit.json`](../generated/edge_surface_routing_audit.json)

Verify: public, manager, tenant, `/-/version`, `/super`, `/configuration`, `/admin`, `/internal-admin`, invalid host, host-header attacks.

### 2. Tenant context binding

Slug extraction, manager blocked on tenant hosts, context cleanup after request.

### 3. White-label token hydration

`apps/brand_experience/`, siteconfig branding, no CLS flashes, sanitized tenant CSS/HTML.

### 4. Admin/config UX

`/configuration` premium front; `/super` operational; platform-only hidden from tenants.

### 5. Browser QA (if harness available)

[`docs/generated/edge_surface_browser_qa.json`](../generated/edge_surface_browser_qa.json)

### 6. Tests

`apps.platform_runtime.tests.test_edge_surface_routing`, `test_tenant_branding_hydration`, `test_admin_surface_boundaries`

### 7. Pillar P1 scanners

`scan_inline_style_off_token.py`, `scan_off_token_colors.py`, `scan_undefined_css_classes.py` — all baseline **0**

## PILLARS

**P1** Design tokens on edge shells. **P3** Host/tenant routing.

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

`EDGE SURFACES READY — REPO SCOPE`

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

