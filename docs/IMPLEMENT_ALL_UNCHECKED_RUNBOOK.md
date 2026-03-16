# Implement All Unchecked SOT Items — Runbook

**Purpose:** Have an agent (or human) implement every remaining `[ ]` in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) without drifting, referencing other plans, and continuing across sessions until everything is either done or explicitly N/A. **Resumable:** Use [SOT_IMPLEMENTATION_SESSION_STATE.md](SOT_IMPLEMENTATION_SESSION_STATE.md) so each run continues from where the last one stopped.

**Authority:** SOT is the single source of truth. This runbook is the procedure only. Do not create new plan files; update only SOT, BACKLOG, docs_truth_ledger, NEXT_50, and N/A_BLOCKERS_AND_RESOLUTION when documenting N/A.

---

## 1. How to run (without interruption)

- **Single long run:** Start with "Implement everything unchecked per docs/IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md; do not stop until every [ ] is either [x] or documented N/A. Work section by section in order; after each phase run verification."
- **Resumable (recommended):** At the start of each run, read `docs/SOT_IMPLEMENTATION_SESSION_STATE.md`. Continue from the "Next section" listed there. At the end of each phase (or every N sections), update SOT_IMPLEMENTATION_SESSION_STATE.md with "Last completed: §X.Y; Next: §X.Y+1" and what was done. So the next run (or next session) continues without redoing work.

---

## 2. Order of work (do not skip)

Follow SOT §11.3 logical order:

| Phase | Sections | What to do |
|-------|----------|------------|
| **Phase II** | §2.4, §3.2 | Any remaining [ ] (signature/replay, raw SQL wrap, SiteSettings in tenant paths). Implement → [x]. If none left, skip. |
| **Phase III** | §6.1 → §6.24 | For each section, for each [ ]: (1) If implementable without product: implement, verify, mark [x] in SOT; (2) If N/A (product/design): ensure N/A is already in SOT and in N/A_BLOCKERS_AND_RESOLUTION; do "Unblock by" only if it’s script/test/doc and no product decision needed. |
| **Phase IV** | §4.5, §5.1 → §5.9 | Same rule: implement → [x], or confirm N/A and document. |
| **Phase V** | §7, §11 Phase H | §7: implement or N/A with owner/date. Phase H: run scripts (run_phase_h_verification.sh, pre_deploy_gate.sh); manual pass only when prioritized—document in SOT. |

---

## 3. For each unchecked `[ ]` (loop)

1. **Locate** the item in SOT (section and line).
2. **Classify:**
   - **Implementable now:** No product/design sign-off needed; you can code or run scripts. → Implement, run relevant tests/lint, then change `[ ]` to `[x]` in SOT and add a short "DONE: …" note if helpful.
   - **N/A (product/design):** Item says "N/A — product 2026-03-12" or similar. → Do **not** implement. Ensure N/A is recorded in SOT and, if needed, in [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md). Optionally do an "Unblock by" step from N/A_BLOCKERS that is purely technical (e.g. run a script, add one test).
   - **Blocked:** Dependency or blocker. → Mark BLOCKED in SOT with one line reason; add to N/A_BLOCKERS "Unblock by" if not already there.
3. **Reference other docs** when implementing:
   - [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) for implementation detail.
   - [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md) for "Unblock by" and concrete steps.
   - [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) §1 and §2e for closure and next steps.
   - [OPERATING_DISCIPLINE_LAYERS.md](OPERATING_DISCIPLINE_LAYERS.md), [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md), [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md) when the item references them.
4. **Verify:** After implementing a batch, run `bash scripts/run_phase_h_verification.sh` or `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` so nothing is broken.

---

## 4. Session state (resumable runs)

- **File:** `docs/SOT_IMPLEMENTATION_SESSION_STATE.md`
- **At start of run:** Read it. If "Next section" is set, start from that section; otherwise start from Phase II (§2.4).
- **At end of each phase (or every 2–3 sections):** Update the file:
  - `Last completed:` §X.Y (and one-line summary)
  - `Next section:` §X.Y+1 (or next phase)
  - `Date (UTC):` and optional `Done this session: [list]`

This way the next agent run (or new chat) can continue without redoing work and without you having to remember where you stopped.

---

## 5. Rules (do not break)

- **Single tracking:** Status and "what's left" stay in SOT only (§11.4). Do not add status to PATH_TO_100, PLAN_AND_BACKLOG_STOCK_TAKE, or other plan docs.
- **No new plan files:** Do not create new strategy/roadmap/remediation plan files. All updates go to SOT, BACKLOG, docs_truth_ledger, NEXT_50, N/A_BLOCKERS.
- **Visible after deploy:** Every [x] you add must be verifiable (UI, API, or doc/lint/test). Add a short note if not obvious.
- **Optionals = required:** SOT says optionals are required. If you leave something as N/A, it must have owner/date/reason; no silent deferral.

---

## 6. When "everything" is done

- Every `[ ]` in SOT is either `[x]` or has an explicit N/A (with owner/date) or BLOCKED (with reason).
- Run full gate once: `SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh` (and optionally with E2E when available).
- Update SOT §11.4 "What's left for 10/10" and "Last run" if needed.
- Update `docs/SOT_IMPLEMENTATION_SESSION_STATE.md`: set "Next section" to "All phases complete" and date.

---

*Cross-reference: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.3–11.4, [REDUNDANCY_AND_PLAN_INDEX.md](REDUNDANCY_AND_PLAN_INDEX.md), [N/A_BLOCKERS_AND_RESOLUTION.md](N/A_BLOCKERS_AND_RESOLUTION.md).*
