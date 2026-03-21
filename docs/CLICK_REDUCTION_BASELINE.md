# Click reduction baseline (§0.3 Premium UX)

Measure key flows before/after UX passes. Target: fewer steps to complete admissions invoice pay, grade entry publish, district hub SSO health review, and advancement donor entry.

## Scripted path length (proxy until human re-measure)

From **backend dashboard** (`/authentication/backend/`), count URL hops to land on target (excluding Cmd+K = 1 action if palette used).

| Flow | Palette (Ctrl+K) | Quick link / grid | Manual nav estimate |
|------|------------------|-------------------|---------------------|
| Open district & LMS interop | 1 (intent) | 1 (quick link) | 3–5 |
| Open donors & gifts | 1 | 1 (welcome grid) | 4–6 |
| Publish term grades | 1 | 2 (Exams chip) | 3–5 |
| Parent pay invoice | 1 (parent dashboard entry) | N/A (parent role) | parent: 2–4 from portal home |

**Target:** palette/quick-link path ≤ 2 for staff-heavy flows above.

## Human-measured table (product owner)

| Flow | Baseline clicks | Target | Final | Owner |
|------|-----------------|--------|-------|-------|
| Parent pay invoice | _TBD_ | ≤ baseline − 2 | _TBD_ | Product |
| Teacher publish term grades | _TBD_ | ≤ baseline − 1 | _TBD_ | Product |
| District admin verify OneRoster | _TBD_ | ≤ baseline | Interop | Product |
| Staff record donor + gift | **2** (dashboard → donors → add → detail + gift) | ≤ 4 | _measure_ | Advancement |

**Enforcement:** Template audit §8.0.11; Cmd+K coverage in `get_studio_command_palette_entries`. Re-measure after each major UX release.

**Evidence:** [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
