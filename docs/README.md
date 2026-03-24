# Documentation — read this first

**Execution and “what’s left”:** one file — **[RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md)** (`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`). **ZIP plan Phase 1** (shell + navigation) status is **§0 → “ZIP execution plan — Phase 1”** in that file (implementation detail: [SHELL_ARCHITECTURE_MATRIX.md](SHELL_ARCHITECTURE_MATRIX.md)).

**Scores / gates:** Authoritative table in SOT **§0**; **§12 engineering (9.5/10)** + **Wave 8 / Phase I.5 (11/10 structural)** = **MET** per **§11.4**. Strategy docs (e.g. NORTH_STAR, PATH_TO_10) must match **§0**—no stale “until §12” lines.

**Backlog (external / vendor / certification only):** [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md).

**Prefer coding over reading:** run `python scripts/verify_sot_pillar_evidence.py` and targeted `pytest` after changes. Use [TEST_DATABASE.md](TEST_DATABASE.md) for DB-backed tests.

**Phases 3–11 gate bundle (linters + static audits, no DB):** `python scripts/verify_phases_3_11_gates.py` — see [PHASES_3_11_GATE_VERIFICATION.md](PHASES_3_11_GATE_VERIFICATION.md).

**Wave evidence index (not a second status file):** [SOT_0155_EVIDENCE_REGISTER.md](SOT_0155_EVIDENCE_REGISTER.md) — maps waves to tests/runbooks; **§0.1.5 truth** is only in the SOT + [SOT_REMAINING_ITEMS_BACKLOG.md](SOT_REMAINING_ITEMS_BACKLOG.md). [runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md](runbooks/SOT_0155_WAVE_RUNBOOKS_COMPENDIUM.md). Older `PLAN_*` docs are **reference** only.

**Audit context (read if needed):** [RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md](RunMyCampus_Enterprise_Architecture_Audit_and_Cursor_Plan.md).
