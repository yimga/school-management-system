# Plan and UI — How They Relate

**Purpose:** Clarify why "the pages" (Configuration Engine, Control Plane, Applications & sections) are the *result* of the plan, not a literal mirror of PATH_TO_100 or the phase docs.

---

## How the plan and UI connect

1. **The plan (SOT, PATH_TO_100, BACKLOG)** is the **execution backlog**: what to build, in what order, and what’s DONE/N/A. It drives *what we implement*.

2. **The UI you see** is the **product of that work**:
   - **Configuration Engine (admin index)** — "Applications & sections" and quick config (Site settings, Feature Control, Theme & Experience, Region Config) come from the plan’s bounded-console and Configuration Control Center work.
   - **Control Plane** — Dashboard, phase status (Phases A–G done, Phase H manual N/A), operator workstreams, and health come from §11 and the execution phases.
   - **Studio OS** — Experience, Automation, Output, Launch, Control hubs and rails come from the plan’s Studio OS and toolset remediation.

3. **So the pages *have* changed to reflect the plan** — they are the built outcome. The plan docs themselves (PATH_TO_100, NEXT_50_PHASES_*, etc.) are **tracking and prioritization**, not a separate "plan view" that replaces the app UI.

---

## Where to see "where we stand"

- **In the UI:** Control Plane dashboard shows phase status (A–G done, H manual N/A, gates). Configuration Engine index now has an "Execution status" card pointing to Control plane for phase summary.
- **In the repo:** Status and "where we stand" live **only** in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §11.4. [PLAN_AND_BACKLOG_STOCK_TAKE.md](PLAN_AND_BACKLOG_STOCK_TAKE.md) is a derived snapshot; [PHASES_1_TO_255_INDEX.md](PHASES_1_TO_255_INDEX.md) and NEXT_50_PHASES_* are reference indexes.

---

## If you want the UI to show more plan detail

- **Option A:** Add a "Plan status" or "Where we stand" page (e.g. under Control Plane) that renders a short summary from the stock take or from a small JSON/markdown file committed with the app.
- **Option B:** Keep the current approach: Control Plane shows phase summary; full detail stays in docs (PLAN_AND_BACKLOG_STOCK_TAKE, SOT §11–§12).

---

*Authority: RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md, PLAN_AND_BACKLOG_STOCK_TAKE.md.*
