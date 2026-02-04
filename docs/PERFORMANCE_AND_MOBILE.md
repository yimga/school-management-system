# Performance and Mobile (Phase 12 Optional)

This document covers optional Phase 12 items: lazy loading, tap targets, and optional Lighthouse/smoke checks.

## Tap targets (44×44px)

- **CSS utility:** `.touch-target` in `static/css/design-system-unified.css`
- **When:** Applied automatically for `(hover: none) and (pointer: coarse)` so small buttons/links get `min-height: 44px` and `min-width: 44px` on touch devices.
- **Usage:** Add the class to critical action buttons or links that may be too small on mobile, e.g. table row actions, icon-only buttons in the header.
- **Sidebar:** Portal sidebar nav pills already use `min-height: 40px` and in touch media query `min-height: 44px` for `.nav-link.nav-pill`.

## Lazy loading

- **Images:** Use `loading="lazy"` on `<img>` for below-the-fold or gallery images. Decorative images can use `role="presentation"` and `alt=""`.
- **Lists:** For very long lists (e.g. student list, invoice list), consider “Load more” or pagination; the design system does not currently ship a dedicated “Load more” component—use existing pagination or add a button that appends the next page via JS/fetch.
- **If implementing “Load more”:** Keep page size reasonable (e.g. 25), store “expanded” state in session or URL, and ensure focus moves to the new content for accessibility.

## Optional Lighthouse / smoke checks

- **Performance:** Run Lighthouse (Chrome DevTools → Lighthouse) on key portal and backend pages (e.g. dashboard, login, one list view). Aim for acceptable LCP and CLS; fix obvious blockers (large render-blocking CSS, huge images).
- **Mobile:** Use “Mobile” device preset and touch simulation; verify tap targets and that no critical controls are obscured.
- **Smoke:** After major front-end changes, a quick manual pass: login, open dashboard, open one list (e.g. evaluations or invoices), and confirm no console errors and core actions work.

## Related

- **Accessibility:** See `docs/ACCESSIBILITY_WCAG.md` for focus, contrast, and keyboard.
- **Empty states and help:** See `docs/EMPTY_STATE_AND_HELP.md`.
