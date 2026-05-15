# Improvement guide: build for when data exists

**Principle:** We are still building; data is not present yet. Do not add or change things only because the app looks empty today. Every improvement should still be correct and valuable **when real data is present**.

---

## Do: improvements that hold up with real data

### 1. **Structure and consistency (always relevant)**

- **Page layout pattern:** Use the same header pattern (title + subtitle + primary action) everywhere. When you have 50 invoices or 20 students, the page still needs a clear header; this is not about empty state.
- **Card and spacing tokens:** Use design tokens for gaps and card style so that when lists and cards are full, spacing and hierarchy stay consistent. Prevents "some pages cramped, some loose" once data grows.
- **Button order and labels:** Primary action first, Cancel/Back second—same on every form. When users submit real payments or save real preferences, muscle memory and accessibility benefit.
- **Table styling:** Define how tables look (headers, alignment, hover, stripes) once. When 100 rows load, the table should still be readable and consistent with other list pages.
- **Form grouping:** Group related fields (e.g. "Student & amount" vs "Allocation lines") so that when the form is used daily with real data, it scans quickly. Not about empty state.

### 2. **Behaviour and logic (data-agnostic)**

- **Split allocation:** Client-side check that allocation sum equals total (plus server-side validation). Prevents wrong submissions whether it’s the first or thousandth payment.
- **Success/error messages:** Use `messages` (or toasts) on all POST flows so that when real actions succeed or fail, the user always gets feedback. Same for validation errors.
- **Loading state on submit:** Disable submit button and show spinner on POST. Prevents double submissions and gives feedback whether the list is empty or full.
- **Preferences bypass:** Allow parents/teachers/staff to open Preferences without "request access." Correct for zero users and for thousands.

### 3. **Performance and scalability (for when data exists)**

- **Queries:** Use `select_related` / `prefetch_related` where a view loads related objects (e.g. invoice + student + payments). When there are many invoices, this avoids N+1 and slow pages. Do this regardless of current row count.
- **Pagination or limits:** Where a list can grow large (invoices, payments, notifications), use pagination or a documented limit. Design for "when we have data," not for "empty list."
- **Indexes and filters:** Ensure models and list views are ready for filtering and sorting by date, status, etc. So when data exists, users can find what they need.

### 4. **Aesthetics that scale with content**

- **Typography scale:** Use a consistent scale (page title, section title, body, caption). When pages are full of content, hierarchy stays clear. Not about empty screens.
- **Focus and accessibility:** Consistent focus rings and labels. Matters more when there are many interactive elements and real users.
- **Theme/dark mode:** Cards, alerts, and tables use theme variables so that when every row is filled, colours and contrast stay correct. Same for light/dark.

### 5. **Security and correctness**

- **Permissions and module access:** Keep RBAC and bypass rules (e.g. preferences) correct. Unrelated to how much data exists.
- **Validation:** Server-side validation (e.g. allocation sum = total) and safe redirects. Required for real data and real users.
- **Tests:** Tests for critical flows (split allocation, preferences access) protect behaviour once real data and integrations exist.

---

## Avoid: changes only for "no data yet"

- **Fancy empty-state illustrations or long copy** just because lists are empty. When data exists, users rarely see them. Prefer a simple, reusable empty component and one short line (e.g. "No items yet" + one action). Don’t over-invest in empty-state-only design.
- **Adding features or UI only to "fill" empty dashboards.** If the real use case is "show N items when we have them," build for that; don’t add placeholders or fake content for the empty phase.
- **Optimising purely for empty lists** (e.g. special layout that only looks good with 0–3 items). Layout and components should work with 0, 10, and 100+ items.
- **Touching tables/lists only to "improve empty view."** Improve list UX for the state when rows exist (readability, sorting, actions); empty state can stay minimal.

---

## Rule of thumb

Before changing something, ask:

- **"When we have real data (invoices, students, payments, users), will this still be right and useful?"**
  - If **yes** → do it (structure, consistency, performance, messages, validation, tests, accessibility).
  - If **only useful while we have no data** → skip or keep it minimal (e.g. one simple empty message + one CTA).

This keeps the codebase ready for production without over-building for the current, data-light phase.
