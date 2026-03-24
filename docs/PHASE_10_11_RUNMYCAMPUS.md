# Phase 10 & 11 — RunMyCampus delivery memo

Canonical ledger: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §3.2.4–§3.2.5.

---

## Phase 10 — Marketing front rewrite

### A. Findings
- **What was wrong:** Homepage mixed many **optional** sections with **repeated card grids** (institutions, product pillars, solve-by-challenge chips, workflow cards, duplicate compliance block), weakening scroll-story flow.
- **Why it mattered:** Read as a **brochure** rather than a **single product narrative** aligned with Studio OS / tenant shell.
- **What it blocked:** Clear mental model for “why switch → architecture → launch → Studio → marketplace → migration → roles → trust → CTA.”

### B. Implementation
| Area | Change |
|------|--------|
| **Templates** | `templates/schools/marketing_landing.html` — narrative chapters, pinned Studio/marketplace blocks, role visual strip, security+trust merge, removals per §3.2.4 SOT |
| **CSS** | `static/marketing/css/marketing-narrative-phase10.css` |
| **Context** | `apps/schools/marketing_views.py` — comment cleanup (no inflated scoring language) |
| **Routes** | None |
| **Tests** | `scripts/verify_ux_completion.py` markers for `marketing_landing.html` |

### C. Acceptance criteria (now true)
- Homepage presents **ordered chapters** with existing scroll progress + reveal + **pinned** Studio/marketplace layouts on desktop.
- **Chip storm** (solve-by-challenge) and **duplicate grids** reduced; **institution** path is a **strip**.
- Copy references **same shell story** (Studio modes, marketplace discipline, migration fallback art).

### D. Cleanup / deprecation
- **Optional later:** Remove stale marketing partials if unused; further collapse `product_pillars_home` vs `core_modules` behind a single feature flag.
- **CMS:** Long-form blocks can replace hard-coded bullets over time without URL changes.

---

## Phase 11 — Gilead purge + docs discipline

### A. Findings
- **What was wrong:** Operators unsure whether **Gilead** was still a **product default** vs **historical tenant name**; risk of **plan sprawl** outside the ledger.
- **Why it mattered:** Brand and onboarding confusion; duplicate “sources of truth.”
- **What it blocked:** Clean **RunMyCampus-only** operator story and a **single** execution checklist.

### B. Implementation
| Area | Change |
|------|--------|
| **Demo seed** | `apps/schools/demo_user_seeding.py`, `management/commands/seed_demo_tenant_users.py` |
| **Deprecated** | `management/commands/seed_gilead_demo_users.py` → delegates + warning |
| **Docs** | `docs/GILEAD_REFERENCE_CLASSIFICATION.md`, SOT §3.2.5 |
| **Lint** | Existing `scripts/lint_gilead_residue.py` remains the gate (PASS) |

### C. Acceptance criteria (now true)
- `python scripts/lint_gilead_residue.py` → **0 violations** in scoped paths.
- **Canonical plan:** SOT extended with §3.2.4 / §3.2.5; classification doc for remaining **historical** references.

### D. Cleanup / deprecation
- **Use** `python manage.py seed_demo_tenant_users` for new environments.
- **Avoid** `seed_gilead_demo_users` except legacy scripts (prints deprecation).
- Historical **migrations** with “gilead” in filenames: **do not delete**; classify as **DEPRECATED/ARCHIVE** only.
