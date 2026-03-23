# SOT backlog — internal closure + external-only open items

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.1.5  
**Updated:** 2026-03-23 — [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md) reconciled to **Repo / Ext** (no contradictory NOT MET rows vs SOT); [docs/README.md](README.md); queue stub [SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md](SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md).

**Policy:** All **repository-deliverable** work for the §0.1.5 / Wave 8 **internal** program is **closed** with tests, templates, and/or `verify_sot_pillar_evidence.py`. This file lists **only** items that **cannot** be completed inside this git repository (external vendors, app stores, audits, open-ended product depth).

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

| Item | Category | Notes |
|------|----------|--------|
| Native **iOS / Android** App Store / Play releases | External | Builds, signing, store listing |
| **SOC 2 Type II / ISO** certificate on file | External | Auditor + evidence room |
| **Clever / ClassLink native** vendor APIs | Blocked | Partnership; BR-11 substitutes in repo |
| **24/7 vendor NOC** / dedicated on-call bench | OPS | Staffing / contract |
| **Third-party WCAG** formal certification audit | COMPLIANCE | External auditor |
| **Z-reports / multi-register** full fiscal depth beyond POS exports | PRODUCT | Roadmap + accounting |
| **Full** SiteSettings **row-level** field decomposition | PRODUCT | Multi-sprint migration |
| **Production CWV / BI dashboards** (staffed ops proof for N10) | OPS | Not a repo-only artifact |

**Related:** [N16_SOC2_ISO_EXECUTION_PROGRAM.md](N16_SOC2_ISO_EXECUTION_PROGRAM.md), [TEST_DATABASE.md](TEST_DATABASE.md), `bash scripts/pre_deploy_gate.sh`

---

## Historical “recently closed” rows

Prior incremental closures (2026-03) are preserved in git history before this consolidation. See blame on this file.

---

## How to use

1. **New internal work:** open a scoped ticket → implement → test → add a row under **Internal — CLOSED** or extend evidence links.  
2. **External milestones:** track outside git; do not flip SOT `[x]` until the real milestone (e.g. certificate on file).  
3. Do **not** spawn duplicate strategy docs or new “plan / stock take / queue status” markdown files; extend the [single source of truth](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), **[docs/README.md](README.md)**, and this registry only.

**Related:** [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [PROGRAM_EXECUTION_REMAINING.md](PROGRAM_EXECUTION_REMAINING.md).
