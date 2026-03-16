# SOT implementation session state (resumable runs)

**Purpose:** So an agent (or human) can continue "implement all unchecked" from where the last run stopped. Read this at **start** of a run; update it at **end** of each phase or every few sections.

**Runbook:** [IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md](IMPLEMENT_ALL_UNCHECKED_RUNBOOK.md)

---

## Current state

| Field | Value |
|-------|--------|
| **Last completed** | (none — start from Phase II §2.4) |
| **Next section** | §2.4 (Phase II) |
| **Date (UTC)** | — |
| **Done this session** | (none yet) |

---

## How to use

- **When starting a run:** If "Next section" is set, begin from that section. Otherwise start from Phase II (§2.4).
- **When finishing a phase (or every 2–3 sections):** Update "Last completed" to the section you just finished, "Next section" to the next one, "Date" to now, and "Done this session" to a short list of what was implemented or documented.
- **When all phases are done:** Set "Next section" to `All phases complete` and the date.

Do not delete this file; it is the resumability state for the SOT implementation run.
