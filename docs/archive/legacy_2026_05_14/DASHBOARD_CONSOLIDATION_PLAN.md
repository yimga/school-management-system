# Parent & Teacher Dashboard Refinement Plan

## Design Philosophy

**Goal:** A dashboard that is easy to use, even for someone who is 80. Clear, calm, and well-ordered.

**Principles:**
- **Simple, not sparse** – Enough information, no clutter. Each piece of data appears once, in the right place.
- **Clear flow** – Natural top-to-bottom, left-to-right reading. "What matters most" first.
- **Gentle and reassuring** – Comfortable spacing, soft colors, readable text. No cramping, no overwhelming density.
- **Structure stays** – We improve flow and feel. We don’t rebuild; we refine.
- **One thing, one place** – If the same metric appears in multiple places, pick the best home and remove the rest.

---

## Flow Pattern (Both Dashboards)

```
1. Welcome + primary action (Workflow link)
2. Snapshot (2–4 numbers: the essentials)
3. Main content (children / classes / assignments)
4. Supporting info (updates, threads, quick links)
5. Sidebar (only if needed; keep minimal)
```

**Rule:** Each section has a single purpose. No overlap.

---

## Parent Dashboard – Refined Plan

### Current Flow (What Exists)

1. Hero (welcome)
2. Workflow card
3. Summary tiles (Children, Attendance, Balance, Notifications)
4. Charts row (Completion, Finance, Trend)
5. Row of 3 cards (Attendance donut, Finance donut, At a glance)
6. Family Overview card
7. My Children section (child cards)
8. Class Updates, Class Threads, Certification, Activity Timeline
9. Insights section
10. Attendance Summary
11. Sidebar

**Problems:** Same metrics (attendance, finance, children) appear many times. Flow is unclear. Some sections repeat content (Class Updates vs Activity Timeline).

---

### Target Flow (Simple, Clear)

| Order | Section | Content | Rationale |
|-------|---------|---------|-----------|
| 1 | Welcome | Title + Workflow button | Clear starting point |
| 2 | Snapshot tiles | 4 tiles: Children, Attendance %, Balance, Notifications | One place for the main numbers |
| 3 | Charts | 2–3 small charts: Paid vs balance, 5-day trend (drop duplicate attendance chart) | Quick visual sense, no duplication |
| 4 | **My Children** (merged) | One block: compact summary row + per-child cards | Single place for family + per-child data |
| 5 | Updates & threads | Class Updates OR Activity Timeline (one, not both) + Class Threads | Supporting info, no repetition |
| 6 | Insights (optional) | 1–2 items max (e.g. Assignment completion) | Extra context only if needed |
| 7 | Certification | Only if GCE enabled | Situational block |
| 8 | Sidebar | Quick links, contact | Minimal, optional |

### What to Remove / Merge

| Remove or merge | Reason |
|-----------------|--------|
| **Family Overview card** | Merge into My Children; data is duplicated there |
| **Attendance donut card** | Already in snapshot tile + per-child cards |
| **Finance donut card** | Already in snapshot tile + Paid vs balance chart + per-child |
| **Completion status chart** (attendance) | Attendance already in snapshot; chart adds confusion |
| **At a glance card** | Overlaps with snapshot tiles |
| **Activity Timeline** | Same data as Class Updates; keep Class Updates only |
| **Attendance Summary section** | Same data as snapshot + per-child |
| **Insights** (most of it) | Keep 1–2 unique items; remove rest |

### What Stays (Single Source)

- **Snapshot tiles** – Children, Attendance, Balance, Notifications (one row)
- **2 charts** – Paid vs balance, 5-day trend (drop the third attendance chart)
- **My Children** – Merged with Family Overview; summary row + per-child cards with attendance, grade, finance
- **Class Updates** – One section; drop Activity Timeline
- **Class Threads** – Keep
- **Certification** – Keep if relevant

### Flow & Feel

- **Spacing** – Calm but not wasteful. Use `g-3`, `mb-3` for a balanced rhythm.
- **Typography** – Section titles: 1rem, semibold. Numbers: slightly larger. No tiny labels.
- **Colors** – Soft accents (green = good, amber = attention, red = urgent). Consistent across sections.
- **Cards** – One idea per card. Clear labels. No crowded blocks.
- **Order** – Most important (snapshot, children) first. Updates and extras after.

---

## Teacher Dashboard – Refined Plan

### Current Flow (What Exists)

1. Hero
2. Workflow card
3. Charts (Marks completion, Marks donut)
4. Row of 3 cards (Attendance, Completion, At a glance)
5. Assignments block (Progress & assignments + table)
6. Schedule, Certification
7. teacher_dashboard_widgets (Completion, Tasks, Finance, Attendance, Lowest completion, Communications, Upcoming, Quick actions)

**Problems:** Attendance and completion repeat. At a glance repeats other cards. teacher_dashboard_widgets duplicates main content. Assignments shown twice (glance + table).

---

### Target Flow (Simple, Clear)

| Order | Section | Content | Rationale |
|-------|---------|---------|-----------|
| 1 | Welcome | Title + Workflow button | Clear start |
| 2 | Snapshot row | 3 cards: Attendance, Marks completion, Next action | One row for core metrics |
| 3 | Charts | 2 charts: Marks by class, Entered vs pending | Visual overview, no extra text blocks |
| 4 | **Assignments** | One block: progress list + compact table | Single place for class/assignment data |
| 5 | Supporting | Lowest completion (actionable), Schedule, Finance/Leave (if needed) | Extra context, not duplicated |
| 6 | Certification | Only if GCE enabled | Situational |

### What to Remove / Merge

| Remove or merge | Reason |
|-----------------|--------|
| **At a glance card** | Repeats snapshot data |
| **teacher_dashboard_widgets** – Completion, Tasks, Attendance | Already in main snapshot row |
| **Duplicate "Progress & assignments"** | Merge into one assignments block |
| **Placeholder sparkline** in Schedule | Use real data or remove |
| **Extra Finance card** (if in widgets) | Keep once – in main row or sidebar |

### What Stays (Single Source)

- **Snapshot row** – Attendance, Marks completion, Pending evals (or next action)
- **2 charts** – Marks by class, Entered vs pending
- **Assignments** – One combined block (list + table)
- **Lowest completion** – Unique, actionable list
- **Schedule** – Today/upcoming (real data only)
- **Finance & leave** – One card
- **Certification** – If relevant

### Flow & Feel

- Same as parent: calm spacing, clear hierarchy, soft accents.
- One metric = one place.
- Primary action (Enter marks, View marks) visible and easy to tap.

---

## Implementation Checklist (Refined)

### Phase 1: Parent – Clean Duplication

- [ ] Merge Family Overview into My Children; remove Family Overview card
- [ ] Remove: Attendance donut card, Finance donut card, At a glance card
- [ ] Remove: Completion status chart (attendance); keep Paid vs balance + 5-day trend
- [ ] Remove: Activity Timeline (keep Class Updates)
- [ ] Remove: Attendance Summary section
- [ ] Trim Insights to 1–2 items
- [ ] Ensure My Children has: summary row + per-child cards (attendance, grade, finance) with clear labels

### Phase 2: Parent – Flow & Feel

- [ ] Order: Welcome → Snapshot → Charts → My Children → Updates → Threads → Insights (minimal) → Certification
- [ ] Apply consistent spacing (`g-3`, `mb-3`)
- [ ] Section titles: 1rem, semibold
- [ ] Soft accent colors on numbers (success/warning/danger)
- [ ] Check contrast and font size for readability (e.g. ≥14px body, ≥16px for important numbers)

### Phase 3: Teacher – Clean Duplication

- [ ] Remove: At a glance card
- [ ] Remove from teacher_dashboard_widgets: Completion status, Pending tasks, Attendance snapshot (duplicates of main row)
- [ ] Merge: Assignments block into one (progress list + table)
- [ ] Remove placeholder sparkline or replace with real data
- [ ] Keep: Lowest completion, Communications, Upcoming, Quick actions (if unique); merge or trim if overlapping

### Phase 4: Teacher – Flow & Feel

- [ ] Order: Welcome → Snapshot → Charts → Assignments → Supporting → Certification
- [ ] Same spacing and typography as parent
- [ ] Clear primary actions (Enter marks, View marks)
- [ ] Readability check for older users

### Phase 5: Shared Polish

- [ ] Shared CSS: `.dashboard-clear` – consistent spacing, typography, accent colors
- [ ] Ensure buttons and links have adequate touch targets (min 44px)
- [ ] Optional: `prefers-reduced-motion` for animations
- [ ] Test with a simple "does this make sense?" walkthrough

---

## Success Criteria

1. **One number, one place** – No metric repeated across multiple sections
2. **Natural flow** – Top to bottom, most important first
3. **Readable** – Comfortable font sizes, clear labels, good contrast
4. **Calm** – Balanced spacing, soft colors, no visual noise
5. **Simple** – An 80-year-old can understand what they see and what to do next
6. **Well crafted** – Consistent, purposeful, no orphaned or redundant elements
