# What’s Not Done — and How to Start

**Authority:** Program status and “what’s left” live in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) **At a glance**, **§11.4**, and **§12** — not in this file. The SOT **§6** app ledger is **[x]** at the **repo behavioral** bar; **§7** seeding is **MET**; **Phase H** is **automated + manual per release** (BR-13). This doc explains **how to pull the next slice** without treating old per-app `[ ]` lists as open spine failures.

**N/A register:** Items formally deferred with owner/date: [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md). Unblock paths: [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md).

**Doc cross-check:** SOT §11.3-style discipline — after changes, update **§11.4** + [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) (A–F) when you ship a slice; keep [docs_truth_ledger.md](docs_truth_ledger.md) aligned. Every change should be **visible after deployment** (UI, API, or documented behavior); see SOT §11.3.

**Runtime-first / Phase 6:** SOT **§3.2** is **[x]** — evidence: `registry_snapshots.py`, runtime inspector, `resolver_registry.py`, contract tests. Map: [PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md](PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md).

**Reconciliation (§5 spine, Phase B, §11.4 depth):** In the SOT, **§5.1–§5.9** toolset actions are **`[x]`** (repository spine). **Phase 5 ZIP** is **COMPLETE**. **Phase B** physical migration: **Batch 0 COMPLETE**; **Batches 1+** in [SITECONFIG_OWNERSHIP_MIGRATION.md](SITECONFIG_OWNERSHIP_MIGRATION.md). **§5.x / §11.4 “full product” depth** ships as **scoped slices** with tests + autonomous log — not as unchecked §5 checkboxes. If anything here conflicts with the SOT, **the SOT wins**.

---

## 1. What still moves (after gates are MET)

### §4.5 Launch Studio — select plan
- **N/A** until multi-plan checkout is productized; document in N/A register when applicable.

### §11.4 — product depth (the real “not done” queue)
Ongoing work is **depth and polish**, not reopening §12. Examples (non-exhaustive — pick from SOT §11.4, [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md), [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md)):
- **siteconfig / ownership:** Phase B batches; bounded consoles; legacy path removal per sign-off.
- **platform_runtime / observability:** Tracing, tenant health surfaces, structured logging expansion.
- **People / 360 / reports / automation / communication / analytics:** Richer UX, packs, graphs, simulation, governance — as sequenced slices.
- **marketplace / api / interop:** Metadata, trust markers, endpoint classification, integration workbench.
- **Premium maturity blockers** in SOT **§0** table (shell triad, Gilead residue, raw SQL/endpoints, AI scatter) — tighten with ledgers + lints, logged in §11.4.

### §7 Ecosystem seeding
- **MET** at repo gate ([MARKETPLACE_SEED_TARGETS.md](MARKETPLACE_SEED_TARGETS.md), `generate_platform_inventory.py --check`, catalog tests). **Optional:** refresh counts or add SKUs when product expands — update SOT/targets if thresholds change.

### Phase H (manual)
- **Per release:** run automated Phase H suite + `phase_h_audit`; execute manual pass per [PHASE_H_UX_VERIFICATION.md](PHASE_H_UX_VERIFICATION.md) / [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md). Not a one-time “three open checkboxes.”

---

## 2. How to start (execution order)

### Use the existing plan files
- **Slice-level actions (Implement / N/A):** [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) — aligns with SOT **§6** as **depth** reference; do not use its tables as a second global status dashboard.
- **Order:** After **Phase II** deepen/verify items, pull **§11.4** themes in priority order (one app or one vertical at a time). **Phase I** wedges are **DONE** (SOT §11).

### Suggested starting sequence
1. **One high-signal §11.4 slice** — e.g. schools raw SQL / control-plane hardening ([raw_sql_audit.md](raw_sql_audit.md), [public_endpoint_audit.md](public_endpoint_audit.md)) or one Phase B batch from SITECONFIG_OWNERSHIP_MIGRATION.
2. **One toolset slice** — e.g. feature-control depth ([feature_control_ledger.md](feature_control_ledger.md)) if the queue calls for it.
3. **Phase H slice for this release** — `python scripts/phase_h_audit.py --verbose`; fix one category; run `python manage.py test apps.accounts.tests.test_phase_h_ux_verification` (or full gate via `scripts/run_phase_h_verification.sh`).

### Concrete “start today” checklist
- [ ] Read SOT **§11.4** and pick **one** scoped slice.
- [ ] Open [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) for the matching **Action** rows (if any).
- [ ] Implement; add evidence to [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md); update SOT §11.4 prose if the queue shifts.
- [ ] Run `bash scripts/pre_deploy_gate.sh` (or `SKIP_VISUAL_QA=1` for a tight loop).

### Where things live

| Need to… | Use |
|----------|-----|
| See **program status** and **what’s left** | SOT **At a glance**, **§11.4**, **§12** |
| See **slice-level** Implement / N/A steps | [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) |
| See deferred items with owner/date | [NA_REGISTER_PATH_TO_100.md](NA_REGISTER_PATH_TO_100.md) |
| Phase H verification | [PHASE_H_UX_VERIFICATION.md](PHASE_H_UX_VERIFICATION.md), `scripts/phase_h_audit.py`, `scripts/run_phase_h_verification.sh` |
| Raw SQL / public endpoints / feature control | [raw_sql_audit.md](raw_sql_audit.md), [public_endpoint_audit.md](public_endpoint_audit.md), [feature_control_ledger.md](feature_control_ledger.md) |
| Unblock any N/A item | [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) |
| Release sign-off | [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), [launch_studio_checklist.md](launch_studio_checklist.md) §4 staging |

---

*Cross-reference: SOT §11.2, §11.4, PATH_TO_100_PERCENT_EXECUTION_PLAN.md, NA_REGISTER_PATH_TO_100.md.*
