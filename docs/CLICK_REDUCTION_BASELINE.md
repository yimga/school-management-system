# Click reduction baseline (§0.3 Premium UX)

Measure key flows before/after UX passes. Target: fewer steps to complete admissions invoice pay, grade entry publish, district hub SSO health review, and advancement donor entry.

## Repo closure (canonical)

**Phase I.5 and §8.0.3 treat the table below as the authoritative baseline/final pair:** “Baseline” = estimated manual sidebar/menu depth from backend home; “Final” = palette or one-tap quick-link depth after Wave 8 + manager palette work. Human spot-checks belong in [PREMIUM_UX_MANUAL_PASS_BR13.md](PREMIUM_UX_MANUAL_PASS_BR13.md) at release; they do not block marking this document **closed** in the SOT.

## Scripted path length (aligned with Final column)

From **backend dashboard** (`/authentication/backend/`), count discrete navigations to land on target (Ctrl+K + Enter = **1** action).

| Flow | Palette (Ctrl+K) | Quick link / grid | Manual nav (baseline est.) |
|------|------------------|-------------------|----------------------------|
| Open district & LMS interop | 1 (intent) | 1 (quick link) | 3–5 |
| Open donors & gifts | 1 | 1 (welcome grid) | 4–6 |
| Publish term grades | 1 | 2 (Exams chip) | 3–5 |
| Parent pay invoice | 1 (parent dashboard entry) | N/A (parent role) | 2–4 from portal home |

**Target:** palette/quick-link path ≤ 2 for staff-heavy flows above — **met** for the four staff/parent rows above.

## Measured table (repo-signed; BR-13 may refine)

| Flow | Baseline (manual est.) | Target | Final (canonical path) | Notes |
|------|------------------------|--------|-------------------------|-------|
| Parent pay invoice | 4 | ≤ 2 | **1** (portal home → pay flow via role home / palette where enabled) | Parent role; staff palette N/A |
| Teacher publish term grades | 5 | ≤ 4 | **1** (palette) or **2** (Exams chip) | Meets ≤ baseline − 1 |
| District admin verify OneRoster | 5 | ≤ 5 | **1** (palette) | Interop hub |
| Staff record donor + gift | 6 | ≤ 4 | **1** (palette) or **2** (welcome grid) | Advancement intents |

**Enforcement:** Template audit §8.0.11; Cmd+K coverage in `get_studio_command_palette_entries` / `BACKEND_COMMAND_PALETTE`. Re-validate scripted rows after each major UX release.

**Evidence:** [NORTH_STAR_WAVE8_CLOSURE.md](NORTH_STAR_WAVE8_CLOSURE.md).
