# SOT backlog — internal closure + external-only open items

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.1.5  
**Updated:** 2026-04-24 — **PATH** [External program blockers](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#external-program-blockers-wopi-app-stores-soc2-or-iso-clever-live) + [Agent 2 off-repo execution](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#agent-2-off-repo-execution): Tier **2**/ **3** table, PMO **ticket stub**, Tier 2 **attack pattern**, Tier 3 **cadence**. **Backlog:** [Agent 2 PMO discipline](#agent-2-pmo-discipline-streams-1-5). Prior: batch **951** governance; batch **944** `release_readiness_check.sh`; 2026-03-23 [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md); [docs/README.md](README.md); [SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md](SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md).

**Policy:** All **repository-deliverable** work for the §0.1.5 / Wave 8 **internal** program is **closed** with tests, templates, and/or `verify_sot_pillar_evidence.py`. This file lists **only** items that **cannot** be completed inside this git repository (external vendors, app stores, audits, open-ended product depth).

**Do everything in one order:** **[PATH_TO_100_PERCENT_EXECUTION_PLAN.md — Single end-to-end goal checklist (merged)](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#single-end-to-end-goal-checklist-merged)** — that section pulls **A** (release gates), **B** (this file’s External + PATH blocker table), **C** ([Program tracks](#program-tracks-end-to-end-execution-steps)), **D** (PATH Phase II–V + SOT §11.4). This backlog is **supporting detail**, not a second master plan.

**Release readiness vs this backlog:** SOT §11.4 batches **918–920** pin **pytest** evidence for `release_readiness_check.sh` §5 only; **batch 944** records a full **`bash scripts/release_readiness_check.sh`** run. They do **not** close or replace the external rows below.

**Canonical blocker register:** **Tier 2** integrations (WOPI/Collabora, app stores, SOC2 or ISO, Clever live): owner **role**, **next concrete action**, **milestone / off-repo evidence**, and **named assignee** discipline—see **[PATH_TO_100_PERCENT_EXECUTION_PLAN.md — External program blockers](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#external-program-blockers-wopi-app-stores-soc2-or-iso-clever-live)** (**§ B** of the [merged checklist](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#single-end-to-end-goal-checklist-merged)). **Tier 3** program rows in PATH link **here** ([Program tracks](#program-tracks-end-to-end-execution-steps)) for phase detail. The **OPEN** index below stays a **short pointer**; do not duplicate the full PATH table.

**Verification commands (stub):** [SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md](SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md) — narrative status is **only** in the SOT §0.1.5 / §0.1.5.1.

---

## Internal — **CLOSED** (evidence in repo)

Shipped in code/tests/docs, including but not limited to:

| Area | Evidence |
|------|----------|
| Wave 4 POS (tenant ops) | `apps/schoolops/views_tenant_ops.py`; `?export=csv` / `?export=json` (`runmycampus.pos_sales_summary.v1`); `apps/schoolops/tests/test_tenant_ops_wave18_pos.py` |
| RESILIENT_EDGE / long forms | `form-draft-save.js` on parent/portal/finance/schoolops templates; `apps/portal/tests/test_resilient_edge_wiring.py`; `apps/finance/tests/test_finance_form_draft_templates.py` |
| UUID-safe tenants | `NorthStarUpcomingDeadlinesView`, marketplace blueprint session, `super_views_wedge` donor POST, `search_api` story enrich, `apps/schools/school_cli_resolution.py` + seed commands |
| N10 / performance | `scripts/check_performance_budgets.py`; SLO API `perf_gate`; `pre_deploy_gate.sh` |
| N24 operator hints | `templates/observability/platform_incidents.html` runbook paths; `docs/N24_OBSERVABILITY_AND_ONCALL.md` |
| N3 table semantics | `test_n3_misc_table_header_templates.py` (`<th scope>`); control-plane + finance templates |
| Parent portal N2 | `templates/parent/finance.html` full `{% trans %}`; `test_parent_finance_template_i18n.py`; link_child, contact_school, support_request, claim_invite, attendance_discipline, wizard |
| Pillar evidence | `python scripts/verify_sot_pillar_evidence.py` (paths include BR, N17–N24, Wave artifacts) |

**Regression bundle (run before release):**

```bash
python scripts/verify_sot_pillar_evidence.py
python -m pytest apps/portal/tests/
```

Optional broader: `apps/schools/tests/test_school_cli_resolution.py`, `apps/api/tests/test_internal_api_wave_smoke.py`, `apps/marketplace/tests/test_install_impact.py`, `apps/schoolops/tests/test_tenant_ops_wave18_pos.py`

**Not claimed as “infinite done”:** third-party WCAG **certification**, every marketing string polished, every form on earth, full multi-register/Z-report retail product — those are **program** tracks, not a single PR.

---

## External / organizational — **OPEN** (not completable in this repo alone)

**Index only:** Full **next action**, **milestone**, and **deferral** language lives in **[PATH — External program blockers](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#external-program-blockers-wopi-app-stores-soc2-or-iso-clever-live)**. Record **named individuals** (not roles alone) in PMO/wiki per PATH discipline.

| Item | Tier | Category | Owner role (PATH) | Next step (summary) | Milestone / evidence (off-repo) |
|------|------|----------|-------------------|---------------------|-----------------------------------|
| **WOPI / Collabora** (T4 live) | **2** | ATTACK infra | Platform Eng lead + Product | DNS → service; `curl` discovery **200**; WOPI smoke; [rollout checklist](execution/COLLABORA_PRODUCTION_ROLLOUT_CHECKLIST.md) | Checklist signed + discovery **200** logged (date, hostname) |
| Native **iOS / Android** store releases | **2** | Distribution | Product PM + Mobile release owner | Certs, CI build, listings, review submission | Live listing **or** **N/A** with sponsor + review-by date |
| **SOC 2 Type II / ISO** on file | **2** | Audit | Compliance lead + Exec sponsor | [N16](N16_SOC2_ISO_EXECUTION_PROGRAM.md) Phase A: scope, SOW, evidence room | Certificate/letter **on file** or audit end date booked |
| **Clever / ClassLink** production district | **2** | Partner | Partnerships + Eng integrations | `release_readiness_check.sh` §8 green + district prod creds + sign-off | First **prod** district live + named signatories |
| **24/7 NOC** | **3** | Program | Ops manager + Staffing | [Program tracks](#program-tracks-end-to-end-execution-steps) stream **1** — Phase **A** (service catalog) | Published catalog + alert map (dated) |
| **WCAG formal cert** | **3** | Program | Product + Compliance | Stream **2** — Phase **A** (scope + auditor) | Signed scope + auditor named |
| **Z-reports / multi-register** | **3** | Program | Product + Finance | Stream **3** — Phase **A** (BRD) | Signed BRD + data dictionary |
| **SiteSettings row decomposition** | **3** | Program | Platform engineering lead | Stream **4** — Phase **A** (inventory) | No-drift memo (staging, verifier output) |
| **Prod CWV + BI proof** | **3** | Program | Eng + Analytics + Exec sponsor | Stream **5** — Phase **A** (RUM dashboard) | Live prod dashboard + 30–90d review scheduled |

**Related:** [N16_SOC2_ISO_EXECUTION_PROGRAM.md](N16_SOC2_ISO_EXECUTION_PROGRAM.md), [TEST_DATABASE.md](TEST_DATABASE.md), `bash scripts/pre_deploy_gate.sh`

---

## Program tracks — end-to-end execution steps

**Discipline:** These streams run in **parallel programs** (months–quarters). Complete phases in order **per stream**; dependencies between streams are called out. **Exit criteria** are explicit; do not mark the SOT or this table “MET” from repo-only work where the criterion says **external** or **production staffed**.

**PATH § C / Tier 3:** Streams **1–5** below correspond to the five **Tier 3** rows in [PATH — External program blockers](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#external-program-blockers-wopi-app-stores-soc2-or-iso-clever-live). **Phase A** of each stream is the **authoritative next step** for that row; **named assignee** and **dated evidence** live in PMO/wiki, not in git.

**Repo touchpoints (examples):** [N24_OBSERVABILITY_AND_ONCALL.md](N24_OBSERVABILITY_AND_ONCALL.md), [ACCESSIBILITY_WCAG.md](ACCESSIBILITY_WCAG.md), [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md), [RUM_HOOK.md](RUM_HOOK.md), `scripts/check_performance_budgets.py`, `scripts/pre_deploy_gate.sh`, `apps/schoolops/` (POS / tenant ops exports).

### Agent 2 PMO discipline (streams 1-5)

**Charter (off-repo):** Same governance family as SOT §11.4 batch **951**, but **execution-focused**—milestones, vendors, infra routing, compliance artifacts **outside** the repo. **Does not** own §11.4 **code** batches unless a tiny config hook is required.

**For each stream 1–5:**

1. Maintain **one program epic** (or board column) per stream; **role owner** = PATH Tier 3 **Owner (role)** for that row.
2. **Active phase** = usually **A** until exit criterion met; then advance **B → C → D** in order.
3. **Every phase ticket** must include: **Named assignee** (individual), **Target date**, **Definition of done** = verbatim **Exit criterion** from the phase table below, **Evidence URL** when closed (wiki page, signed doc, dashboard link).
4. **Dependencies:** Call out vendor/auditor/legal in ticket; link to PATH [Agent 2 off-repo execution](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#agent-2-off-repo-execution) for Tier **2** parallel work (WOPI, stores, SOC2, Clever) that may block a stream.

**Cadence:** Agent 2 reviews **Tier 2** PATH rows weekly for stalled DNS, auditor kickoff, district sign-off; reviews **Tier 3** stream boards **monthly** with PATH owners.

### 1. 24/7 NOC (vendor or internal operations)

| Phase | Steps | Owner | Exit criterion |
|-------|--------|--------|----------------|
| **A. Baseline** | Inventory production **health URLs**, SLO dashboard, alert sources; map to [RUNBOOKS_INDEX.md](RUNBOOKS_INDEX.md) + [N24_OBSERVABILITY_AND_ONCALL.md](N24_OBSERVABILITY_AND_ONCALL.md). | Platform ops | Single **service catalog** doc: what is monitored, where alerts go. |
| **B. Tooling** | Contract with metrics/traces/logs vendor (or internal stack); wire **paging** (PagerDuty/Opsgenie/etc.); define **severity** + escalation matrix. | Ops + Security | **Test page** from non-prod + one **live** P1 drill with recorded outcome. |
| **C. Coverage** | 24/7 **rotation** (minimum two tiers); handoff checklist; runbook links in incident template. | Staffing / vendor | Roster published; **gap policy** when primary unavailable. |
| **D. Steady state** | Quarterly game day; post-incident reviews; update runbooks. | Ops lead | **Evidence:** dated review record (wiki/ticket), not git. |

### 2. Third-party WCAG certification (formal audit)

| Phase | Steps | Owner | Exit criterion |
|-------|--------|--------|----------------|
| **A. Scope** | Pick **WCAG target** (e.g. 2.1 AA), **URL/conformance scope** (tenant vs marketing vs app shell), auditor RFP or MSAs. | Product + Compliance | Signed **audit scope** document. |
| **B. Remediation backlog** | Automated scans + manual audit findings → **prioritized** tickets; fix in releases; re-test critical paths. | Engineering | **Zero** open **blocking** findings in auditor’s retest scope (or documented exceptions). |
| **C. Formal attestation** | Auditor issues **VPAT/ACR** or equivalent; legal/comms review. | Compliance | **Certificate or letter on file** (external artifact). |
| **D. Sustain** | Regression policy: a11y checks in CI where possible; periodic rescan. | Engineering | **Policy doc** + owner; repo: extend [ACCESSIBILITY_WCAG.md](ACCESSIBILITY_WCAG.md) as implementation summary only. |

### 3. Z-reports / multi-register fiscal depth (product + accounting)

| Phase | Steps | Owner | Exit criterion |
|-------|--------|--------|----------------|
| **A. Jurisdiction & registers** | Define **register** model (device, location, tax authority); which **Z-report / X-report** variants; export formats. | Product + Finance | **Signed BRD** or equivalent; data dictionary. |
| **B. Data model** | Migrations for registers, shifts, settlements; immutability rules; link to existing POS/sales flows (`schoolops` / finance). | Engineering | **Migrations + tests**; rollback plan. |
| **C. Reports & exports** | Implement Z/X (or jurisdiction equivalent), audit trail, **CSV/PDF** per regulator; staff UI. | Engineering | **UAT** with finance sign-off on sample period. |
| **D. Ops** | Training, cutover, support runbook; optional external accountant review. | Ops + Product | **Go-live record** + first production period reconciled. |

### 4. Full SiteSettings row-level decomposition (multi-sprint migration)

| Phase | Steps | Owner | Exit criterion |
|-------|--------|--------|----------------|
| **A. Inventory** | Refresh `domain_ownership`, [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md) Phase B table; run `python scripts/generate_platform_inventory.py --check`, `scripts/verify_siteconfig_decomposition_depth.py`. | Platform engineering | **No drift:** inventory + Phase B contract match repo gates. |
| **B. Field moves** | Per domain: add typed tables/columns, **resolver-first** reads, dual-write or backfill, then cut reads, then drop facade column. | Engineering + DBA | **Ordered** per [RESOLVER_MIGRATE_DELETE_ORDERING.md](RESOLVER_MIGRATE_DELETE_ORDERING.md). |
| **C. Per-environment** | `migrate` + `scripts/verify_phase_b_execution.py` on **staging then prod**; record in release runbook. | Operator | **Hostname + date + verify output** stored outside git. |
| **D. Done definition** | `SiteSettings` matches **slim contract**; remaining references only allowlisted platform paths. | Product + Eng | Gates green: `pre_deploy_gate.sh`, `verify_phase_5_siteconfig.py`, tenant lints per SOT. |

### 5. Production CWV + BI proof (staffed operations)

| Phase | Steps | Owner | Exit criterion |
|-------|--------|--------|----------------|
| **A. Instrument** | Production **RUM** (see [RUM_HOOK.md](RUM_HOOK.md)); CrUX or vendor RUM dashboards; tag releases. | Engineering | **Dashboard URL** with prod traffic (not localhost). |
| **B. Budgets** | Adopt `scripts/check_performance_budgets.py` / perf_gate in **release train**; Core Web Vitals **thresholds** agreed with product. | Ops + Product | **Failing build blocks release** or explicit waiver process. |
| **C. BI layer** | Semantic model for **revenue/usage/SLA**; dashboards for exec + ops; data freshness SLO. | Analytics + Ops | **Subscribed** dashboards + **on-call** knows where to look. |
| **D. Proof** | 30–90 day **production window** report: CWV trend + BI KPIs + incident count; review with leadership. | Exec sponsor | **Signed review** or board-ready one-pager (external record). |

---

## Historical “recently closed” rows

Prior incremental closures (2026-03) are preserved in git history before this consolidation. See blame on this file.

---

## How to use

1. **New internal work:** open a scoped ticket → implement → test → add a row under **Internal — CLOSED** or extend evidence links.  
2. **External milestones:** track outside git; do not flip SOT `[x]` until the real milestone (e.g. certificate on file).  
3. Do **not** spawn duplicate strategy docs or new “plan / stock take / queue status” markdown files; extend the [single source of truth](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), **[docs/README.md](README.md)**, and this registry only.  
4. **Multi-quarter product/ops streams** (NOC, WCAG cert, fiscal depth, SiteSettings decomposition, prod CWV/BI): follow **[Program tracks (end-to-end execution steps)](#program-tracks-end-to-end-execution-steps)**; sync dates and owners in your PMO/wiki—**not** by inventing new repo-only “done” flags.

**Related:** [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [PROGRAM_EXECUTION_REMAINING.md](PROGRAM_EXECUTION_REMAINING.md). **In-product + automation:** [BACKLOG_UNLOCK_AUTOMATION.md](BACKLOG_UNLOCK_AUTOMATION.md) (`super:backlog_unlock_center`, `evaluate_backlog_unlocks`).
