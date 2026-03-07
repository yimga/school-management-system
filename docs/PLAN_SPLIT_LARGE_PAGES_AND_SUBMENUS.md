# Plan: Splitting Large Pages and Submenu Patterns

When a page becomes too large (long scroll, too many fields, too many rows, or heavy UI), this plan gives a **repeatable process** to break it up and, when appropriate, expose parts as submenu items.

---

## 1. When to consider splitting (“page too big”)

Use one or more of these **triggers** to decide “this page should be split or simplified”:

| Trigger | Example | Threshold (guideline) |
|--------|---------|------------------------|
| **Scroll length** | User has to scroll more than ~2–3 screens to see all content | > 2.5 viewport heights of primary content |
| **Form field count** | Single form/tab has many fields | > 15–20 fields in one section/tab |
| **List size** | Table/list of records (e.g. users, students) | > 50–100 rows without pagination, or very wide tables |
| **Readonly blocks** | Many big readonly sections (e.g. summaries, embeds) | > 3–4 large blocks on one page |
| **Performance** | Page load or render is slow (large DOM, many components) | Noticeable lag or high DOM node count |
| **User feedback** | People say “hard to find X” or “page is overwhelming” | Recurring in support or testing |

**Rule of thumb:** If a single **tab** or **section** feels like it does more than one main job, consider splitting that job out.

---

## 2. Options for breaking a large page

Choose one (or combine) based on **content type** and **how users need to use it**.

### A. Dedicated page + link (what we did for Color & harmony)

- **What:** Move a logical block (e.g. “Color & harmony”) to its **own URL**. The original page keeps a short **link/button** (e.g. “Open Color & harmony”).
- **When:** One coherent “sub-task” (color picker, report builder, bulk tool) that doesn’t need to sit in the main form.
- **Submenu:** The new URL can be linked from the main page and, if you want, from a sidebar/submenu (e.g. under “Theme & Experience” or “Site Settings”).
- **Pros:** Main page short; full space for the tool; clear entry point.
- **Cons:** One extra navigation step.

### B. Tabs / sections (already in use)

- **What:** Keep one URL but split content into **tabs** or **collapsible sections** (e.g. Site Settings tabs).
- **When:** Same “entity” (e.g. one settings object) with many logical groups; user often needs only one group at a time.
- **Submenu:** Usually no separate submenu; the tabs *are* the in-page “submenu”.
- **Pros:** Single page, single save; familiar pattern.
- **Cons:** Can still get long if each tab has too much.

### C. Sub-routes (child URLs under the same “section”)

- **What:** One “parent” concept with several **child views** under one path prefix, e.g.:
  - `/siteconfig/` → Theme & Experience (main), `/siteconfig/theme-colors/`, `/siteconfig/preferences/`, `/siteconfig/feature-control/`.
- **When:** Several distinct tasks that belong to the same area (e.g. “Site configuration”).
- **Submenu:** Sidebar or nav shows “Theme & Experience”, “Color & harmony”, “Preferences”, “Feature Control” as sub-items.
- **Pros:** Clear hierarchy; each child page stays focused.
- **Cons:** Need to design the parent vs child list (e.g. dashboard vs links).

### D. Pagination / infinite scroll (for lists)

- **What:** Keep the same “page” (e.g. user list) but **paginate** or **lazy-load** rows (e.g. 25–50 per page).
- **When:** Page is “too big” because of **many rows**, not many sections.
- **Submenu:** Not needed for “breaking”; optional “Filters” or “Export” as sub-actions.
- **Pros:** Same URL and layout; predictable performance.
- **Cons:** Doesn’t reduce “number of sections”; only list size.

### E. Accordions / collapsible sections

- **What:** Same URL, same form, but **collapse** less-used blocks by default (e.g. “Color combinations reference”).
- **When:** You want to keep everything on one page but reduce **initial** length and cognitive load.
- **Submenu:** No; in-page expand/collapse only.
- **Pros:** No new routes; “one page” feeling.
- **Cons:** Page can still be heavy if many sections exist; not a true “submenu”.

### F. Wizard / steps

- **What:** One flow split into **steps** (e.g. Step 1: Choose type, Step 2: Options, Step 3: Review). One URL or one per step.
- **When:** Linear process with clear stages (e.g. onboarding, bulk import).
- **Submenu:** Optional “Resume” or “Start over” in nav.
- **Pros:** Focus on one step at a time.
- **Cons:** Only for flows, not for general “big page”.

---

## 3. Decision flow: which option to use

```
Is the “too big” mainly…
├── Many rows in a list?
│   → Pagination / lazy load (D); optionally filters/export as sub-actions.
├── One big “tool” or “workspace” inside a form?
│   → Dedicated page + link (A); add submenu link if it’s a first-class area.
├── Many sections for the same entity (e.g. one settings object)?
│   → Tabs/sections (B); if a tab itself gets too big, split that tab with (A) or (C).
├── Several distinct tasks under one area (e.g. site config)?
│   → Sub-routes + submenu (C); each task = one child URL, submenu = list of those URLs.
├── Just “too much on screen at once” but all needed on one page?
│   → Accordions / collapsible (E).
└── A linear multi-step process?
    → Wizard (F).
```

---

## 4. Submenu patterns (how to “become a submenu”)

- **Admin (Django admin):**  
  - Use custom **list or change URLs** (e.g. `get_urls()` on a ModelAdmin) for extra views.  
  - Or use **app-level URLs** under `/siteconfig/`, `/reports/`, etc., and link from the admin dashboard or from a “parent” change form (like “Open Color & harmony”).

- **Backend / portal:**  
  - Define a **parent item** in the sidebar (e.g. “Site configuration”).  
  - **Children** = links to dedicated pages: e.g. “Site Settings”, “Color & harmony”, “Preferences”, “Feature Control”.  
  - Each child = one view, one URL; submenu = list of those URLs in the sidebar or in a dropdown.

- **Naming:**  
  - Parent: area name (e.g. “Theme & Experience”, “Site configuration”).  
  - Child: task name (e.g. “Color & harmony”, “User list”, “Bulk import”).  
  - URL: short and readable, e.g. `/siteconfig/theme-colors/`, `/siteconfig/preferences/`.

---

## 5. Repeatable process (manual but consistent)

When you notice a page that fits the “too big” triggers:

1. **Confirm** which trigger applies (scroll, fields, rows, blocks, performance, feedback).
2. **Choose** the option from §2 using the decision flow in §3 (dedicated page, tabs, sub-routes, pagination, accordions, wizard).
3. **Define the split:**
   - If **dedicated page:** name the new view (e.g. “Color & harmony”), pick URL (e.g. `theme-colors/`), list which fields or block move there.
   - If **submenu:** decide parent label and list of child links (URL + label).
4. **Implement:**
   - Add view + URL; move or duplicate the block content; on the original page replace the block with a link/button (and optional submenu entry).
   - Ensure “Back to …” or breadcrumb so users can return.
5. **Test:** Check that the main page is shorter and that the new page (and submenu, if any) works for the main workflows.
6. **Document:** One line in a “Split pages” section of your docs or ADMINS: “Theme & Experience tab was long → Color & harmony moved to `/siteconfig/theme-colors/`.”

---

## 6. What can be “automated”

Fully automatic “detect and split” is not practical (design and UX choices are involved). You can still **automate checks and conventions**:

- **Checklists / lint (future):**
  - **Field count:** Script or CI that, for a given form/tab, warns if field count > N (e.g. 20).
  - **Route convention:** Lint that every new “sub” view under `/siteconfig/` (or similar) is listed in a central config (e.g. submenu links), so nothing is orphaned.
- **Templates / scaffolds:**
  - **“Dedicated page” template:** Copy a minimal template (e.g. like `theme_colors.html`: extends backend_base, “Back to X” link, one main card). Reduces boilerplate when you add the next “Color & harmony”-style page.
  - **Submenu snippet:** A partial template or config array where you add `{ "label": "Color & harmony", "url": "siteconfig:theme_colors" }` so the sidebar stays consistent.
- **Docs:**
  - **This plan:** When someone adds a new big page or submenu, they follow §5 and optionally add one line to the “Split pages” log.

---

## 7. Summary

- **Triggers:** Long scroll, many fields, many rows, many blocks, slow load, or user feedback.
- **Options:** Dedicated page + link (A), tabs (B), sub-routes + submenu (C), pagination (D), accordions (E), wizard (F).
- **Submenu:** Decide parent (e.g. “Theme & Experience” or “Site configuration”); each child = one URL; sidebar or nav lists those URLs.
- **Process:** Confirm trigger → choose option (decision flow) → define split (name, URL, what moves) → implement (view, link, back link, submenu) → test → document.
- **Automation:** Checklist/lint for field count and submenu registration; templates for “dedicated page” and submenu config; this plan as the repeatable guide.

Using this, any future “page too big” (e.g. user list, another settings section, a big report form) can be broken in a consistent way and, where it makes sense, turned into a submenu.
