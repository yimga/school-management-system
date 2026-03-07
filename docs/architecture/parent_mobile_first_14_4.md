# Parent Mobile-First (Section 14.4)

Parent portal should feel like a beautiful mobile-first app: viewport, touch targets, responsive layout.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 14.4; phase14_through_phase20.

---

## 1. Current state

- **portal_base.html** already includes `<meta name="viewport" content="width=device-width, initial-scale=1">`. All portal pages (including parent) extend it.
- **Parent routes:** e.g. `/portal/parent`, `/parent/dashboard`; templates under `templates/parent/` (e.g. feed.html, wallet.html) extend portal_base.
- **data-dashboard-page="parent"** is set by portal_base.js for parent paths, enabling role-specific CSS.

---

## 2. Recommendations

- **Touch targets:** Buttons and links on parent-facing pages should have min height/width ~44px for touch (Bootstrap btn and links are adequate; ensure no tiny icon-only controls without padding).
- **Responsive layout:** Use Bootstrap grid and responsive utilities; test parent feed and wallet on narrow viewports.
- **New parent pages:** Prefer single-column on mobile; place primary actions in thumb-friendly positions.

---

## 3. Implementation status

| Item | Status |
|------|--------|
| Viewport meta | Done (portal_base) |
| Parent templates extend portal_base | Done |
| Touch targets / responsive audit | Documented; apply to new/updated parent pages |
