# Documentation — read this first

**Execution and “what’s left”:** one file — **[RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md)**. Start with **At a glance** and **§11.4** (release + depth queue); **§12** = engineering gate checklist.

**End-to-end goal (one merged order):** [PATH_TO_100_PERCENT_EXECUTION_PLAN.md — Single end-to-end goal checklist (merged)](PATH_TO_100_PERCENT_EXECUTION_PLAN.md#single-end-to-end-goal-checklist-merged) — release gates **A** → external blockers **B** → program tracks **C** → repo depth **D**.

**How to start a slice:** [WHATS_NOT_DONE_AND_HOW_TO_START.md](WHATS_NOT_DONE_AND_HOW_TO_START.md) (coordinates with §11.4; not a second status home). **Implement/N/A row detail:** [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md).

**ZIP / shell:** Phases **1, 3, 5** are **COMPLETE** in SOT **§0** (summary table). Implementation detail: [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md), [docs/phase_checklists/](phase_checklists/).

**Scores / gates:** **§0** (tiers), **§12** (checkboxes), **§11.4** (what’s left). Strategy docs must match **§0**—no stale “until §12” lines if §12 is MET.

**Backlog (external / vendor / certification only):** [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md).

**Prefer coding over reading:** run `python scripts/verify_sot_pillar_evidence.py` and targeted `pytest` after changes. Use [TEST_DATABASE.md](TEST_DATABASE.md) for DB-backed tests.

**Phases 3–11 gate bundle (linters + static audits, no DB):** `python scripts/verify_phases_3_11_gates.py` — see [PHASES_3_11_GATE_VERIFICATION.md](PHASES_3_11_GATE_VERIFICATION.md).

**Gate-map maintenance (contributors):** canonical appendix rows live in [gate_map_appendix_config.json](gate_map_appendix_config.json); regenerate/check with `python scripts/generate_gate_map_appendix.py --write` / `--check`.

**Wave evidence index (not a second status file):** [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md) — maps waves to tests/runbooks; **§0.1.5 truth** is only in the SOT + [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md). [runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md). Older `PLAN_*` docs are **reference** only.

**Audit context (read if needed):** [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md).
