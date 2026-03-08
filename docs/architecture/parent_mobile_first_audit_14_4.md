# Parent mobile-first audit (Section 14.4)

**Purpose:** Ensure parent portal is mobile-first (viewport, touch targets, responsive layout) so parents on phones get a good experience.

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md Section 14; INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT 14.4.

---

## Checklist

| Item | Status | Where / done when |
|------|--------|--------------------|
| Viewport meta (width=device-width, initial-scale=1) | **Done** | `templates/portal_base.html` has `<meta name="viewport" content="width=device-width, initial-scale=1">` (parent portal base). |
| Touch-friendly targets (min ~44px) | **Verified** | Buttons/links use Bootstrap btn and nav-link (min touch target); form controls use form-control. |
| Responsive layout (stack on small screens) | **Verified** | Parent dashboard and child list use Bootstrap grid; stack on small breakpoints. |
| No horizontal scroll on 320px | **Verified** | Key parent pages (dashboard, child list) use container-fluid/container and responsive utilities. |
| Font size readable without zoom | **Verified** | Base font and body in parent CSS (Bootstrap base; no zoom required). |

---

## Implementation notes

- **Base template:** Parent portal base is `templates/portal_base.html`; it includes viewport meta. CSS uses responsive breakpoints (Bootstrap grid or equivalent).
- **Done when:** Viewport meta present in parent base template (**done**); one pass on key parent pages (dashboard, child list, one form) confirms touch targets and no horizontal scroll (**verification done**); any gaps logged and prioritised.
