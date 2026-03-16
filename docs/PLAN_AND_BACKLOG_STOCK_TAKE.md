# Plan and Backlog — Where We Stand

**Purpose:** Single snapshot of where the plan, backlog, and execution stand at this time. Update when reconciling or at major milestones. Authority: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md), [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md), [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md).

**Last updated:** 2026-03-16.

---

## 1. SOT §11 Phases (execution order)

| Phase | Status | Notes |
|-------|--------|--------|
| **Phase A — Hardening** | **DONE** | AI secret removal; public/exempt ledger + CI; raw SQL audit; exception reduction; Gilead purge (0155 + lint). |
| **Phase B — Settings dismantling** | **DONE** | Settings inventory; ownership reassignment (behavioral); shrink SiteSettings plan; bounded console (console_domains_hub); customizer/workflow_hub/report_library redirects. |
| **Phase C — Runtime/metadata law** | **DONE** | Runtime absolute (resolvers, precedence doc, contract tests); metadata catalog; lineage + inspector; contract tests in pre_deploy_gate. |
| **Phase D — Studio OS** | **DONE** | Shared shell; all five mode hubs (Experience, Automation, Output, Launch, Control) with rail + iframe; retire old tool identities (redirects in place). |
| **Phase E — Ecosystem productization** | **DONE** | Package engine (validate/preview/apply/rollback/promote); seed apps/packs (catalog minimums met); marketplace UX (Install/Apply/Preview/Rollback); ReportPack/DocumentPack in use. |
| **Phase F — UX and marketing authority** | **DONE** | Role-home engine; contextual actions; page archetypes; proof-rich marketing (proof_hero, why_switch, product_visualization_slides, fallbacks). |
| **Phase G — Docs truth** | **DONE** | Docs aligned with reality; ledgers; single completion ledger (docs_truth_ledger); SOT is execution plan. |
| **Phase H — Full codebase/UX verification** | **PARTIAL** | Automated: test_phase_h_ux_verification, phase_h_audit, phase_h_url_check, run_phase_h_verification.sh, pre_deploy_gate. Manual full pass and deploy visibility: N/A when prioritized (product 2026-03-12); PHASE_H_MANUAL_CHECKLIST + PHASE_H_EXECUTION_LOG. |

---

## 2. §12 Scoring gates

**All 11 gates MET** (no 9.5 claim until release sign-off).

| Gate | Status | Verification |
|------|--------|----------------|
| siteconfig materially decomposed | MET | lint_tenant_settings, lint_siteconfig_legacy_imports; domain_ownership §6 |
| SiteSettings not tenant-behavior truth | MET | Same; get_effective_site_settings runtime-first |
| runtime only legal behavior engine | MET | test_runtime_contract, runtime_precedence.md, runtime inspector |
| AI secrets safe | MET | lint_secret_exposure |
| public surfaces hardened | MET | public_endpoint_audit; four lints; webhooks 401 on invalid signature |
| Gilead residue gone | MET | Migration 0155; lint_gilead_residue |
| Studio OS replaces fragmented tools | MET | Five mode hubs; §4.1 completion gate |
| package engine production-grade | MET | apps/packages engine + tests; package_engine_ledger |
| marketplace/packs deeply productized | MET | MARKETPLACE_SEED_TARGETS; test_marketplace_catalog_minimums; generate_platform_inventory --check |
| docs truth no contradictions | MET | DOCS_TRUTH_AUDIT; key docs disclaim §12 |
| marketing front platform-grade | MET | MARKETING_FRONT_PLACEHOLDER; fallbacks; static/images/marketing/ |

Evidence: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §12.1. One-liner: `bash scripts/pre_deploy_gate.sh`.

---

## 3. PATH_TO_100 (summary)

| Phase | Scope | Status |
|-------|--------|--------|
| **Phase II** | §2.4, §3.2 (signature/replay, raw SQL, SiteSettings in tenant paths) | DONE — lints pass; allowlists; billing/finance webhooks 401. |
| **Phase III** | §6.1–§6.24 (app-by-app) | DONE or N/A per [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md). System config console, runtime tracing, pack provenance, Launch Studio, previews/compare/rollback, blueprint owner, registries, marketplace metadata, schools/accounts/portal/finance/academics/people/reports/automation/observability/api — all addressed. |
| **Phase IV** | §4.5, §5.1–§5.9 (toolset) | §4.5 select plan N/A until productized. §5.2 owner/expiry DONE (migration 0158). Rest N/A product 2026-03-12 per NA_REGISTER. |
| **Phase V** | §7 seeding, Phase H | §7 DONE (catalog minimums, marketplace UI). Phase H: automation in place; full manual/deploy visibility N/A when prioritized. |

Every unchecked item has either been implemented (and marked [x] in SOT) or documented N/A with owner/date in NA_REGISTER.

---

## 4. BACKLOG (where we stand)

| Area | Status | Notes |
|------|--------|--------|
| **Last reconciled** | Current | §2e rows 6, 7, 8, 13 done and dusted; CONTROL_PLANE §5.1 all DONE; OPERATING_DISCIPLINE_LAYERS 10.5.1–10.5.8 DONE; allowlist 0. manage.py check, lint_broad_except --strict, verify_operating_discipline_docs pass. |
| **?1 table (27 rows)** | Closed | Every unchecked item has status (DONE/PARTIAL/NOT DONE/BLOCKED) + closure note. |
| **?2.1 SiteSettings/ownership** | DONE | get_solo/load replaced in tenant paths; legacy paths (agreed scope) removed/redirected; completion gates MET. |
| **?2.4 Security/raw SQL/broad except** | DONE | Raw SQL in repos only; broad except §2e row 6 at allowlist 0; structured logging §2e row 7; signature/replay per public_endpoint_audit. |
| **?3–?4 Architecture / Studio OS** | DONE | Runtime universal; precedence; metadata lifecycle/lineage; all five Studio hubs. |
| **?5–?7 Toolset / marketplace / seed** | DONE | Catalog minimums; marketplace UI; Install/Apply/Preview/Rollback. |
| **?8–?12 Marketing / gates / docs** | DONE / PARTIAL | Page archetypes DONE; proof_hero + fallbacks DONE; **11 of 11 §12 gates MET.** No 9.5 claim until release sign-off. |
| **NEXT_50 steps 1–50** | **50 DONE** | All steps DONE. Step 6 (legacy path removal) DONE with product sign-off 2026-03-12. |

---

## 5. NA_REGISTER (N/A items)

- **Phase III (§6):** §6.6 absorb ownership N/A (product); §6.7 preview/sandbox, §6.8 hard registry + marketplace, §6.9 registry UI, §6.10 previews/trust/scope N/A; §6.11–§6.24 remaining items N/A product 2026-03-12 where not already DONE.
- **Phase IV (§5):** §4.5 select plan N/A until productized; §5.1 move ownership/unify, §5.3–§5.9 (Report Platform, Document & Compliance, Design Studio, Workflows, AI/API, System Config full reclass/preview) N/A product 2026-03-12. §5.2 owner/expiry **DONE** (migration 0158).
- **Phase V:** §7 DONE; Phase H full manual/deploy visibility/full suite N/A when prioritized (automation in place).

Unblock: [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md).

---

## 6. Docs truth ledger

- **Role:** Single canonical completion ledger; every roadmap/audit item → DONE / PARTIAL / NOT DONE / DEPRECATED / BLOCKED.
- **Status:** In force. §2e rows 6, 7, 8, 13 done and dusted. Last reconciled with BACKLOG (completion audit; 54 smoke+Phase H URL, 94 targeted hardening OK).
- **Cross-check:** When marking items [x] in SOT or N/A, update docs_truth_ledger and BACKLOG as needed.

---

## 7. Logical phases (1–105 and beyond)

| Batches | Doc | Status |
|---------|-----|--------|
| 1–15 | NEXT_15_PHASES_COMPLETION | Policy diff link, academics tests, report/document pack filter, Portal→Output, registry UI, feature control ledger, Launch/Phase H/docs. |
| 16–30 | NEXT_15_PHASES_16_30 | Reports theme/policy doc, marketplace metadata doc; policies/reports/Launch/Phase H/observability/API Center. |
| 31–45 | NEXT_15_PHASES_31_45 | Report dependency + sample-data; endpoint classification + contract tests; Phase H execution log. |
| 46–60 | NEXT_15_PHASES_46_60 | UX acceptance + responsive reference; bounded consoles inventory. |
| 61–75 | NEXT_15_PHASES_61_75 | §6.6 previews/compare/rollback [x]; absorb N/A; Report Platform/style/§6.24/Phase H/feature control; pre_deploy_gate run. |
| 76–90 | NEXT_15_PHASES_76_90 | Ownership/legacy; Student360/reports/automation/communication/analytics/observability N/A; master index; release/BACKLOG/docs sync. |
| 91–105 | NEXT_15_PHASES_91_105 | II.1/II.2/IV.28/portal/finance; E2E/smoke/onboarding; Studio OS gates DONE; §7/Phase H/REDUNDANCY/trust/doc cross-check. |
| 106–155 | NEXT_50_PHASES_106_155 | Next 50 logical phases (106–155; see doc). |
| 156–205 | NEXT_50_PHASES_156_205 | Next 50 logical phases (156–205; E2E/inventory/Phase H/staging; product triggers; §8.0/quality/gates; siteconfig/legacy; governance/release/sync). |

**Master index:** [PHASES_1_TO_205_INDEX.md](PHASES_1_TO_205_INDEX.md) (covers 1–205; [PHASES_1_TO_155_INDEX.md](PHASES_1_TO_155_INDEX.md), [PHASES_1_TO_120_INDEX.md](PHASES_1_TO_120_INDEX.md), [PHASES_1_TO_105_INDEX.md](PHASES_1_TO_105_INDEX.md) for shorter ranges).

---

## 8. Remaining / when prioritized

- **Phase H full manual pass:** Run PHASE_H_MANUAL_CHECKLIST on deploy; fill PHASE_H_EXECUTION_LOG. Automated slice already in place.
- **Staging sign-off (Step 34):** Run 10-point launch checklist in staging per launch_studio_checklist.md §4; add row to RELEASE_CHECKLIST.
- **N/A items:** Implement when product unblocks; see NA_REGISTER and N/A_BLOCKERS_AND_RESOLUTION. When implemented, mark [x] in SOT and update NA_REGISTER.

---

## 9. Key verification commands

- **Gate:** `bash scripts/pre_deploy_gate.sh`
- **Record gate:** `bash scripts/record_pre_deploy_gate_output.sh`
- **Phase H:** `python scripts/phase_h_audit.py`; `python scripts/phase_h_audit.py --live`; `python scripts/phase_h_url_check.py`; `bash scripts/run_phase_h_verification.sh`
- **Lints:** lint_tenant_settings --check-get-solo-only; lint_csrf_exempt_usage; lint_allow_any_usage; lint_raw_sql_usage; lint_broad_except --strict; lint_secret_exposure; lint_gilead_residue

See [VERIFICATION_GATES_INDEX.md](VERIFICATION_GATES_INDEX.md) for full list.

---

*Source: RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md, PATH_TO_100_PERCENT_EXECUTION_PLAN.md, BACKLOG_AND_DEFERRED_CLOSURE.md, NA_REGISTER_PATH_TO_100.md, docs_truth_ledger.md. Update this stock take when reconciling.*
