# Parent Dashboard: ~40% Height Reduction Plan

**Goal:** Reduce the vertical height of the Parent Portal dashboard by ~40% while keeping all content and improving clarity. No removal of features.

---

## 1. Current height drivers (from top to bottom)

| Area | What adds height |
|------|-------------------|
| **Dashboard Stats bar** | `mb-3`, card padding `0.75rem`, label + badge row. |
| **Finance access banner** | Full-width alert, `mb-3`, two lines of text. |
| **Parent Portal header** | Large padding (`var(--dashboard-gap-md)` / `var(--dashboard-gap-lg)`), eyebrow + H1 + subtitle (3 lines), right column: stacked buttons + Switch child + Manage notifications (many rows). |
| **Gap below header** | `margin-bottom: var(--dashboard-gap-md)`. |
| **Today's Overview** | Section title with `mb-2`, grid of 4 cards with `min-height: 105px` and card padding. |
| **Gaps between sections** | `mb-3` / `mb-4` and row gutters. |

---

## 2. Plan (by area)

### 2.1 Dashboard Stats bar (portal_base.html + CSS)

- **Reduce block margin:** Change wrapper from `mb-3` to `mb-2` for parent dashboard only (e.g. `.dashboard-page-parent .mb-3` override or a parent-specific class on the stats wrapper).
- **Reduce card padding:** Override stat card padding from `0.75rem` to `0.5rem` on parent dashboard.
- **Optional:** Slightly smaller label font (e.g. `0.7rem` instead of `0.75rem`) so the row is one compact line.

**Estimated height saved:** ~15–20px.

---

### 2.2 Finance access banner

- **Single line when possible:** If `finance_access_banner.summary` is short (e.g. “No invoices recorded yet”), show one line: “Finance access is granted. No invoices recorded yet.” (or similar) so the banner is one line + optional CTA.
- **Reduce padding:** Use `py-2` instead of default alert padding; keep horizontal padding modest.
- **Reduce margin:** Use `mb-2` instead of `mb-3` for parent dashboard.

**Estimated height saved:** ~25–35px.

---

### 2.3 Parent Portal welcome header (main lever)

- **Tighter padding:** In `parent/dashboard.html` inline styles and/or `dashboard-premium-compact.css`, reduce header padding to ~`0.6rem 0.9rem` (from ~`0.95rem 1rem` and from base `var(--dashboard-gap-md)`/`var(--dashboard-gap-lg)`).
- **Smaller title:** Reduce H1 font size (e.g. `clamp(1.15rem, 1.8vw, 1.5rem)` instead of `1.45rem–2.05rem`).
- **One-line welcome:** Put eyebrow + welcome on one line, e.g. “Parent Portal — Welcome back, Parent One!” (or keep eyebrow above but reduce gap to `0.25rem`).
- **Subtitle:** Either one line with smaller font (e.g. `0.85rem`) or move “Here’s how your children are doing today.” next to the title on desktop (e.g. after a dash) to save a line.
- **Actions row (biggest win):** Keep all actions but in a **single horizontal row** with smaller controls:
  - Verified Parent pill + My Workflow + Contact School + Switch child (narrow select) + Manage notifications (+ WhatsApp if present) in one row; wrap to two rows only on small screens.
  - Use `btn-sm`, `form-select-sm`, and reduced vertical padding (e.g. `py-1` / `min-height: 32px`) so the action bar is ~36–40px tall instead of multiple stacked rows.
- **Header margin below:** Reduce `margin-bottom` from `var(--dashboard-gap-md)` (16px) to ~8–10px for parent.

**Estimated height saved:** ~80–120px.

---

### 2.4 Today's Overview section

- **Section title:** Use `mb-1` instead of `mb-2`; optionally smaller icon/text (e.g. `h6` already, ensure no extra line-height).
- **Cards:** Reduce `min-height` from `105px` to ~72–80px so they’re shorter; reduce internal padding (e.g. `padding: 0.5rem 0.65rem` instead of `var(--dashboard-gap-md)`).
- **Card content:** Keep icon + number + label but use slightly smaller font for the label (e.g. `small` or `0.8rem`) and minimal gap between number and label (`mb-0` or `gap: 0.15rem`).

**Estimated height saved:** ~35–50px.

---

### 2.5 Section spacing and container

- **Between header and Today’s Overview:** Already reduced via header `margin-bottom` (above).
- **Between Today’s Overview and Workflow / next sections:** Use `mb-2` instead of `mb-3`/`mb-4` for `.parent-glance-section` and sibling sections on parent dashboard.
- **Container:** Reduce `padding-top` / `padding-bottom` of `.parent-dashboard .container-lg` from `1rem` to `0.6rem` for parent only.

**Estimated height saved:** ~20–30px.

---

### 2.6 Optional improvements (same height or small savings)

- **Dashboard Stats:** If the parent context sends the same 4 stats (Children, Attendance, Balance, Notifications), ensure the stat cards don’t have a redundant “Dashboard Stats” title that could be merged into the first card or made smaller.
- **Workflow strip:** Slightly tighter card-body padding (e.g. `0.75rem 0.9rem`) and margin-top/margin-bottom to align with the new density.
- **Accessibility:** After compacting, ensure touch targets remain ≥44px where possible (e.g. primary buttons); use `min-height` on buttons/selects rather than only padding.

---

## 3. Implementation order

1. **CSS overrides (parent-only)**  
   Add or extend a block in `dashboard-premium-compact.css` (or a small `parent-dashboard-compact.css` loaded after it) scoped to `body[data-dashboard-page="parent"]` / `.dashboard-page-parent`:
   - Dashboard Stats wrapper + stat card padding/margin.
   - Finance banner padding/margin.
   - Parent header: padding, H1 size, subtitle size, `.dashboard-title` gap, `.dashboard-actions` single row + smaller controls + margin-bottom.
   - Today’s Overview: section title margin, glance card min-height and padding.
   - Container and section margins.

2. **Template tweaks (parent/dashboard.html)**  
   - Optional: combine finance_access_banner text into one line when summary is one short sentence.
   - Optional: single-line welcome (e.g. eyebrow + title in one line with smaller eyebrow).
   - Ensure header actions stay in one flex row with wrap; no extra divs that force stacking.

3. **Portal_base (Dashboard Stats)**  
   - Optional: add a class to the stats wrapper when `request.resolver_match.url_name == 'parent_dashboard'` (or similar) so only the parent dashboard gets the compact stats bar; or use `.dashboard-page-parent` in CSS to target the existing `.mb-3` and stat card styles.

4. **Design tokens**  
   - Optionally define `--dashboard-gap-md-compact: 10px` and `--dashboard-gap-sm-compact: 6px` and use them only for parent dashboard to avoid affecting teacher/backend.

---

## 4. Rough height budget (target ~40% reduction)

Assume initial “above the fold” content height ~700–900px (stats + banner + header + Today’s Overview).  
Target reduction: **~280–360px**.

| Lever | Estimated saving |
|-------|-------------------|
| Dashboard Stats | 15–20px |
| Finance banner | 25–35px |
| Header (padding + title + actions + margin) | 80–120px |
| Today’s Overview (title + cards) | 35–50px |
| Section/container spacing | 20–30px |
| **Total** | **~175–255px** |

To reach **~40%**, add:
- Further reduction in header (e.g. remove subtitle line or fold into title; or two-row actions with smaller gaps).
- Slightly more aggressive card min-heights and padding across the first two sections.

Re-measure after implementation and iterate once (e.g. reduce header or glance cards a bit more) if the target is not yet met.

---

## 5. Files to touch

| File | Changes |
|------|--------|
| `templates/parent/dashboard.html` | Optional one-line finance text; optional single-line welcome; ensure actions structure (single row). Inline style tweaks if not moved to CSS. |
| `templates/portal_base.html` | Optional: add `.dashboard-page-parent` or parent-specific class to stats block for scoped CSS. |
| `static/css/dashboard-premium-compact.css` | Main compact overrides for parent (stats, banner, header, glance section, spacing). |
| Optional: `static/css/parent-dashboard-compact.css` | New file with parent-only compact rules; load after premium-compact in `parent/dashboard.html` extrastyle. |
| `static/css/design-tokens.css` | Optional: `--dashboard-gap-*-compact` for parent. |

---

## 6. Summary

- **No content removed:** All stats, finance banner, welcome text, actions (Verified Parent, My Workflow, Contact School, Switch child, Manage notifications, WhatsApp), and Today’s Overview cards stay.
- **~40% height cut** comes from: smaller padding/margins, one compact welcome line (or two with less gap), single-row actions with smaller controls, shorter glance cards and section spacing.
- **Improvements:** Clearer visual hierarchy (one row of actions), consistent compact density, and optional one-line finance message for less clutter.

Implement in the order above; measure after step 1–2 and then tune header and glance section if more reduction is needed.
