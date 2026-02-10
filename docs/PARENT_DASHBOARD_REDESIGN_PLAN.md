# Parent Dashboard Redesign Plan (Single Consolidated Plan)

**Reference:** The provided parent dashboard images are the **benchmark**. The redesign must match that layout and style: card-based design, "Today at a Glance" (four cards), "My Children" cards with badges and three metrics (Attendance, Academics, Fees), right column (Direct Contact, Recent Announcements, Documents), soft gradients, rounded corners, theme tokens. **No room for mistakes:** no repeated data, no gaps or endless white space, dashboard kept to one to two screens with the sidebar as the hub for anything that does not fit.

---

## 1. Current state

| Area | Current implementation |
|------|------------------------|
| **Template** | [templates/parent/dashboard.html](templates/parent/dashboard.html) (~1800 lines), extends `portal_base.html` |
| **View** | [apps/portal/views.py](apps/portal/views.py) → `parent_dashboard()`; data from `parent_dashboard_widget_data()` |
| **Data** | `child_cards` (per-child: attendance, finance, badges, missing_work, etc.), `widget_data` (attendance, performance, finance, events, tasks), `class_announcements`, `class_threads`, `unread_messages_aggregate`, `widget_data.events` |
| **Hero** | Dashboard hero + summary tiles (Children, Attendance, Balance, Notifications, Setup) + inner stat row + My Workflow card |
| **Sections** | My Children (child cards + family summary bar), School Feed, Class Updates, Class Threads, sidebar (Direct Contact, Upcoming Events, Recent Announcements), charts row, Fees Due card, Latest transactions, Finance inbox |
| **Styling** | Inline CSS with hardcoded colors; no dedicated "Today at a Glance" row |

---

## 2. Design targets (from reference images)

- **Header:** "Welcome back, [Name]"; subtitle "Here's how your children are doing today." or "Here's a summary of your children's progress today."; profile area with avatar and **"Verified Parent"** badge (purple, theme primary).
- **Today at a Glance:** One row of **four cards**, each with icon, value, and soft gradient: (1) **Messages from School** (e.g. "3 Unread") – blue/purple, (2) **Items to Follow Up** (e.g. "1 Due Homework") – orange, (3) **Outstanding** (e.g. "$50.00 Due") – red/pink, (4) **Good** (e.g. "92% Attend") – green.
- **My Children:** One card per child: avatar, name, grade; **badges** (e.g. Attendance Award, Reading Star) as colored pills; **three metrics** – Attendance (Good / Needs Attention), Academics (On Track), Fees (Cleared / Pending); **"View details"** button (primary).
- **Right column:** **Direct Contact** (teacher avatar, name, role, "Message" button); **Recent Announcements** (title, snippet, date, arrow); **Documents** (list with icon and date).
- **Homework & Upcoming:** On dashboard only as a **short teaser** (e.g. next 3 items + "See all") if space allows without exceeding two screens; full list lives on Calendar/Homework page (sidebar).
- **Visual style:** Rounded cards, soft shadows, **theme tokens** only; subtle gradients; high contrast (dark text on light, white/light text on colored buttons and badges).

---

## 3. No repeated data: single source of truth

Each piece of information appears **once** on the dashboard.

| Data | Single location | Remove or do not add |
|------|-----------------|----------------------|
| Unread messages count | Today at a Glance – "Messages from School" card only | Hero badges, hero stat row, summary tile "Notifications", duplicate in child cards (aggregate only in Glance). |
| Items to follow up / missing work | Today at a Glance – "Items to Follow Up" card only | Hero status pills, any duplicate elsewhere. |
| Outstanding fees (aggregate) | Today at a Glance – "Outstanding" card only | Hero stat row, summary tile "Balance", **Fees Due** card, **family-summary-bar** balance cell. |
| Attendance (aggregate %) | Today at a Glance – "Good" card only | Hero stat row, summary tile "Attendance", **family-summary-bar** attendance cell. |
| Children count | Header or "My Children (2)" section title only | Summary tile "Children", family-summary-bar "Children" column. |
| Per-child attendance / academics / fees | **Only** inside each **My Children** card | Family-summary-bar; no duplicate aggregate on dashboard. |
| Upcoming events / homework | One short teaser on dashboard ("Next 3" + See all) **or** no list on dashboard; full list on Calendar/Homework page | Sidebar "Upcoming Events" as second full list; only one events source on dashboard. |
| Announcements | **One** block: Recent Announcements in **sidebar** (2–3 items + "See all") | Main-column "Class Updates"; no second announcements block. |

**Concrete removals:** Hero inner stat row, all summary tiles, standalone Fees Due card, family-summary-bar, main-column Class Updates, sidebar Upcoming Events card (or replace with "See all" only). Charts row, Latest transactions card, Finance inbox card, Class Threads block, Certification block: remove from dashboard body (see section 5).

---

## 4. No gaps and white space

- Remove redundant sections when replacing (e.g. do not keep summary tiles and add Today at a Glance).
- One column flow on small screens; right column stacks below main; no empty columns.
- **Consistent spacing:** One token (e.g. `--dashboard-gap-md`) between sections and cards; no large margins that create stripes.
- **Compact empty states:** One short line ("No announcements" + link) instead of tall empty cards; optionally hide section when empty.
- No orphaned widgets; sidebar cards in one column with consistent gap.
- **Charts:** Do not place finance/attendance charts on the dashboard (they add length); link to Portal Stats or Insights via sidebar.

---

## 5. Short dashboard + sidebar as hub

**Target:** Dashboard fits in **one to two screens** (no long scroll). Everything that does not fit lives on **dedicated pages** reachable via the **sidebar** (menus/tabs).

### 5.1 What stays ON the dashboard (only)

| Section | Content | Limit |
|---------|---------|--------|
| Header | Title, welcome, subtitle, profile + Verified Parent badge | One row. |
| Today at a Glance | Four cards (Messages, Follow up, Outstanding, Good); each links to one page | One row. |
| My Children | One card per linked child | No family summary bar. If 3+ children: show e.g. 2 cards + "View all" to My Children/Workflow page, or compact horizontal scroll; **do not** stack many cards. |
| Sidebar (on dashboard) | Direct Contact (avatar + Message); Recent Announcements (2–3 items + "See all"); Documents (1–2 items or "Document library" link) | Three small cards max. |

**Optional (only if it does not push past two screens):** One compact row "Next 3" (homework/events) + "See all" to Calendar/Homework. If it would make the dashboard longer than two screens, omit it and use sidebar Calendar/Homework only.

### 5.2 What moves OFF the dashboard (sidebar → own pages)

| Content | Where it goes | Sidebar / nav |
|---------|----------------|---------------|
| Full Homework & Upcoming list | Calendar or "Homework & deadlines" page | Sidebar: "Calendar" or "Homework" |
| Full Announcements | Announcements page | Sidebar: "Announcements" |
| Documents (full list) | Document library / Reports page | Sidebar: "Documents" or "Report cards" |
| Finance (invoices, history, pay) | Existing Finance page | Sidebar: "Finance"; Glance "Outstanding" → same |
| Attendance / stats (charts, trend) | Portal Stats or Results page | Sidebar: "Attendance" / "Portal Stats"; Glance "Good" → same |
| Class Threads / Messages | Messages or Contact page | Sidebar: "Messages"; Glance "Messages from School" → same |
| Certification | Certification or Workflow page | Sidebar: "Certification" or "My Workflow" |
| Latest transactions | Finance page (history) | No widget on dashboard; link from Glance or sidebar Finance |
| Finance/attendance charts | Portal Stats or Insights page, or remove | Do not put on dashboard |
| Finance inbox / request notifications | Requests or Finance page | Sidebar or link from Glance |
| My Workflow (full) | Workflow page | Sidebar: "My Workflow"; optional slim CTA on dashboard or remove |

**Template removals from dashboard body:** Charts row, Latest transactions card, Finance inbox card (or one line + link), Class Updates (main column), Class Threads block, Certification block, full School Feed list. Sidebar on dashboard: only Direct Contact, Recent Announcements (2–3 + See all), Documents (1–2 + See all). All other entries (Finance, Calendar, Messages, My Workflow, Link a child, etc.) are **sidebar menu items** in the portal shell.

### 5.3 Sidebar as hub: ensure menus exist

- **Audit** [templates/partials/portal_sidebar.html](templates/partials/portal_sidebar.html): ensure parent role has **Parent Home**, **My Workflow**, **Finance**, **Calendar** (or Homework), **Messages** (or Contact), **Announcements**, **Documents** (or Report cards), **Link a child**, **Portal Stats** (if used). Add any missing item.
- Dashboard links (Glance cards, "View details", "See all") must point to these same pages.

### 5.4 Intuitive, easy to use, easy on the eye

- **Intuitive:** One place per concept (e.g. "How are my kids?" → My Children; "What do I need to do?" → Today at a Glance; "Where is everything about X?" → Sidebar → X page).
- **Easy to use:** Primary actions in Glance and child cards; everything else one click away in the sidebar; no long scroll to find actions.
- **Easy on the eye:** Limited sections, consistent spacing and typography (tokens), no dense tables or long lists on the dashboard, enough whitespace between the few blocks.
- **Professional:** Same design system as teacher portal; clear hierarchy; no redundant or duplicate content; compact empty states.

---

## 6. Professional, seamless, easy to use (checklist)

- **Consistent patterns:** One primary button style for "View details", "Message", "Pay Now"; all cards use same border-radius, shadow, spacing from tokens; section titles one size (`--dashboard-section-size`).
- **Loading/errors:** Per-card only (skeleton or short "Unable to load" + link); no full-page loader or full-width error banner unless critical.
- **Accessibility:** One `main`; section titles in `<h2>` with `aria-labelledby` where needed; keyboard-focusable Glance cards with visible `:focus-visible`; icons `aria-hidden="true"` where decorative; counts/status with `aria-label` or visible text; WCAG AA contrast.
- **No layout shift:** Reserve space for Today at a Glance row; stable grid for child cards (`minmax(280px, 1fr)`).
- **Predictable navigation:** Each Glance card → one destination; "View details" → same type of page for every child; sidebar "See all" → same pages as main links.
- **Consistent interactions:** Whole card clickable or one clear "View" link; primary for main action, outline for "See all" / "History".
- **Clear hierarchy:** One H1 (page title); section order: Header → Today at a Glance → My Children → (optional Next 3) → sidebar.
- **Mobile/touch:** Glance 2x2 or single column; tap targets ≥44px; sidebar stacks below main in same order.
- **Empty/first-time states:** No children → one friendly block + "Link a child" CTA; no events/announcements → one short line + link; first-time hint dismissible and stored.

---

## 7. Phased implementation (with all removals and rules)

### Phase 1: Theme tokens and shell

- In [templates/parent/dashboard.html](templates/parent/dashboard.html): replace inline `:root` overrides with **theme tokens** from [static/css/design-tokens.css](static/css/design-tokens.css) (`--school-primary`, `--school-accent`, `--admin-content-text`, `--admin-content-border`, `--dashboard-card-radius`, `--dashboard-card-shadow`); optional `--parent-glance-*` for card tints.
- Introduce `.parent-dashboard-shell` and namespaced section classes (`.parent-glance-*`, `.parent-children-*`, `.parent-sidebar-*`).
- **Deliverable:** Dashboard driven by tokens; ready for layout changes.

### Phase 2: Header and Today at a Glance

- **Header:** Title "Parent Dashboard"; welcome "Welcome back, [first name]."; subtitle "Here's how your children are doing today."; right: profile + **Verified Parent** badge when `parent_verified` (purple, same style as teacher CBA Certified).
- **Today at a Glance:** One row of four cards: (1) Messages from School – `unread_messages_aggregate`, link to messages/contact, light blue/purple; (2) Items to Follow Up – `missing_work_count` or "1 Due Homework", link to workflow/results, light orange; (3) Outstanding – `widget_data.finance.balance`, link to parent finance, light red/pink; (4) Good – `widget_data.attendance.overall` (e.g. "92%"), light green. Each: icon, value, label, rounded corners, shadow, theme background.
- **Remove:** Hero **inner stat row**, **all summary tiles**, **standalone Fees Due** card. Do not keep them alongside Today at a Glance.
- **Deliverable:** Header and Glance match reference; all colors from tokens.

### Phase 3: My Children cards

- Section title "My Children" with optional icon and "Medal case" link.
- **Remove the family-summary-bar entirely.** Per-child metrics appear only in child cards.
- **Child card:** Avatar (or initials), name, grade; badges from `card.badges` as colored pills; **three metrics:** Attendance (Good if ≥ threshold else Needs Attention), Academics (On Track), Fees (Cleared / Pending / Outstanding); one **View details** button (primary) → e.g. `portal:parent_child_results` or child overview.
- If 3+ children: cap visible cards (e.g. 2) + "View all" to dedicated page or compact scroll; do not stack many cards.
- Styling: slight gradient per card, theme borders/shadows; responsive grid.
- **Deliverable:** My Children matches reference; no family bar; theme-only colors.

### Phase 4: Homework & Upcoming (teaser only) and events

- **On dashboard:** Either (a) one compact row "Next 3" items from `widget_data.events` (and merged sources) + "See all" to Calendar/Homework page, **or** (b) no homework list on dashboard at all (rely on sidebar Calendar/Homework). Choose (b) if (a) would exceed two screens.
- **Remove:** Full School Feed list from dashboard body; sidebar "Upcoming Events" as duplicate list (replace with "See all" link to Calendar/Homework if needed).
- Data: `widget_data.events` (merge `portal_upcoming_assessments` in view if needed). Each item: title, date, optional course; status colors from theme.
- **Deliverable:** At most one short "Next up" row on dashboard; full list only on sidebar-linked page.

### Phase 5: Right column – Direct Contact, Announcements, Documents

- **Direct Contact:** Homeroom teacher or generic "Contact school": avatar, name, role; **Message** button (primary) → `portal:parent_contact_school`. Optional view: pass `homeroom_teacher` from [apps/portal/views.py](apps/portal/views.py) if available.
- **Recent Announcements:** **Only** announcements block on dashboard. Use `class_announcements` (and optionally `portal_announcements` merged in view): 2–3 items max + "See all" to Announcements page. **Remove** main-column "Class Updates" section.
- **Documents:** 1–2 items or single "Document library" link; optional `parent_documents` from view. Compact empty state: one line + link if no documents.
- **Remove:** Main-column Class Updates; duplicate Upcoming Events card (or "See all" only). Compact empty states for all three sidebar cards.
- **Deliverable:** Sidebar has exactly Direct Contact, Recent Announcements (2–3 + See all), Documents (1–2 + See all); no second announcements or events list on dashboard.

### Phase 6: Polish, length cap, accessibility

- **Dashboard length:** One to two screens; all long lists and detail views live on dedicated pages linked from sidebar.
- **Layout density:** Consistent `--dashboard-gap-*` between all sections and cards; compact empty states; no full-width empty blocks.
- **Styling:** All cards from tokens; no hardcoded hex; optional subtle gradient on main background or Glance/child cards.
- **Typography:** Section titles bold, one size; subtitles muted; primary for main CTAs, outline for secondary.
- **Responsive:** Glance 4 cols → 2x2 or stack; My Children grid stacks on mobile; sidebar stacks below main.
- **A11y:** Landmarks, focus rings, labels, contrast (WCAG AA).
- **Deliverable:** Dashboard aligned with reference; short, scannable, accessible, professional.

---

## 8. Data and view changes (minimal)

- **View:** Most data exists (`child_cards`, `widget_data`, `class_announcements`, `unread_messages_aggregate`, `parent_verified`, `widget_data.events`).
- **Optional:** Pass `homeroom_teacher` for Direct Contact; pass `parent_documents` for Documents card; merge `class_announcements` and `portal_announcements` for single Recent Announcements list; merge `portal_upcoming_assessments` into events for Homework/Calendar page.
- **Template-only:** Phases 1–4 and 6 in [templates/parent/dashboard.html](templates/parent/dashboard.html) (and optional [static/css/parent-dashboard.css](static/css/parent-dashboard.css)); Phase 5 may need one or two new context variables.

---

## 9. File checklist

| File | Changes |
|------|--------|
| [templates/parent/dashboard.html](templates/parent/dashboard.html) | Header, Today at a Glance, My Children (no family bar), optional Next 3 row, sidebar (Direct Contact, Announcements, Documents); remove hero stat row, summary tiles, Fees Due card, family-summary-bar, charts row, Latest transactions, Finance inbox, Class Updates, Class Threads, Certification, full School Feed; token-based CSS; responsive; compact empty states. |
| [templates/partials/portal_sidebar.html](templates/partials/portal_sidebar.html) | Audit and add parent items: Parent Home, My Workflow, Finance, Calendar/Homework, Messages, Announcements, Documents, Link a child, Portal Stats. |
| [static/css/design-tokens.css](static/css/design-tokens.css) | Optional: `--parent-glance-*` for card backgrounds. |
| [apps/portal/views.py](apps/portal/views.py) | Optional: `homeroom_teacher`, `parent_documents`; merge announcements/events if needed. |
| New: [static/css/parent-dashboard.css](static/css/parent-dashboard.css) | Optional: extract parent-dashboard-only styles. |

---

## 10. Order of work

1. **Phase 1** – Tokens and shell.
2. **Phase 2** – Header + Today at a Glance; remove hero stat row, summary tiles, Fees Due card.
3. **Phase 3** – My Children cards; remove family-summary-bar; cap children if 3+.
4. **Phase 4** – At most one short "Next 3" row or no homework on dashboard; remove full School Feed and duplicate Upcoming Events.
5. **Phase 5** – Sidebar: Direct Contact, Recent Announcements (2–3 + See all), Documents (1–2 + See all); remove Class Updates and duplicate events; compact empty states.
6. **Phase 6** – Polish, length cap, spacing, a11y, responsive.

---

## 11. Summary (reference: images; no room for mistakes)

| Requirement | How it is met |
|-------------|----------------|
| **Reference images** | Layout and style match: Today at a Glance (4 cards), My Children (cards with badges + 3 metrics + View details), right column (Direct Contact, Announcements, Documents), soft gradients, rounded cards, theme tokens. |
| **No repeated data** | Single source of truth per metric; hero stat row, summary tiles, Fees Due card, family-summary-bar, duplicate events and announcements removed. |
| **No gaps / white space** | Redundant sections removed; consistent spacing tokens; compact empty states; no orphaned widgets; no charts on dashboard. |
| **Short dashboard** | One to two screens only. On dashboard: Header, Glance (4), My Children (cards only, cap if 3+), optional Next 3, sidebar (3 cards). Full lists, charts, finance history, threads, certification → sidebar pages. |
| **Sidebar as hub** | Audit portal_sidebar for parent; all "See all" and Glance links go to same sidebar-linked pages. |
| **Professional** | Consistent patterns, tokens, a11y, no layout shift, predictable nav, clear hierarchy. |
| **Easy to use / easy on the eye** | One number per metric; per-child cards with only three status lines + View details; 44px tap targets; limited sections and whitespace; scannable, not overwhelming. |

This document is the **single source of truth** for the parent dashboard redesign. Implement in order; verify each phase against the reference images and the tables above so there is no room for mistakes.
