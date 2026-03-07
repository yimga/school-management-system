# Other Foreseeable Improvements (Heads-Up)

Beyond the [drag-and-drop makeover](DRAG_AND_DROP_MAKEOVER_PLAN.md) and [parent/teacher dashboard improvements](DASHBOARD_IMPROVEMENTS_PARENT_TEACHER.md), here are other areas you might want to be aware of so you can plan or prioritize.

---

## 1. Performance & scale

- **Dashboard layout API:** GET/PUT per page load and on every save. Consider short-lived caching (e.g. 30–60s) for GET when many users hit the same role default, and debouncing PUT on rapid drags.
- **Widget data:** Parent/teacher widget data (attendance, finance, etc.) is already cached in services; keep an eye on cache keys and TTL as you add widgets or roles.
- **Static assets:** You use CDN for Bootstrap, Sortable, etc. Ensure critical CSS/JS for above-the-fold content is minimal so first paint stays fast; optional: preload key fonts/assets.
- **List pages:** Large tables (students, invoices, etc.) may need pagination, search, or lazy-loading if data grows; consider this before lists get very long.

---

## 2. Accessibility (a11y)

- **Customize layout:** Plan includes keyboard (focusable grip, arrow keys) and screen reader announcements; when you implement, test with one screen reader and keyboard-only.
- **Forms & errors:** Ensure required fields and validation errors are announced (aria-describedby, aria-invalid) and that focus moves to first error on submit where appropriate.
- **Contrast & theme:** You’ve improved theme visibility; periodic check with contrast tools (e.g. axe or WAVE) on new components keeps a11y from regressing.
- **Skip links:** You have “Skip to main content”; keep it and ensure target `id="main-content"` is present and visible on all main templates.

---

## 3. Mobile & touch

- **Drag-and-drop:** Plan suggests a list-based reorder fallback on small viewports; implementing that avoids fragile drag on touch.
- **Footer / sidebar:** Footer is already more compact; sidebar is offcanvas on mobile. Ensure tap targets (buttons, links) are at least ~44px and that offcanvas closes on route change or outside tap.
- **Tables:** Wide tables (e.g. finance, reports) may need horizontal scroll, card-style layout, or simplified columns on narrow screens.

---

## 4. Security & auth

- **Rate limiting:** Consider rate limits on login, password reset, and layout API (PUT) to reduce abuse; many deployments do this at reverse proxy or app level.
- **Session:** Ensure session cookie is HttpOnly, Secure where HTTPS is used, and SameSite appropriate for your domain setup.
- **RBAC:** You’ve tightened sidebar and dashboard visibility; keep permission checks on the **server** for every sensitive action (not only UI hiding).

---

## 5. Data & consistency

- **Single source for metrics:** You aligned parent top-bar attendance with the dashboard view; apply the same idea elsewhere (e.g. any “stats bar” vs “widget” that show the same metric).
- **Empty states:** Plan for “no data” everywhere (e.g. “No attendance records yet”, “No invoices”) so the UI never looks broken or ambiguous.
- **Defaults:** Role-aware “Reset to default” for layouts; same idea for other settings (e.g. preferences) so “reset” is predictable per role.

---

## 6. User experience (UX)

- **Onboarding:** First-time hints (e.g. “Customize layout”) and optional short tour for new parents/teachers can reduce “where do I…” support.
- **Notifications:** Central place (e.g. bell) and consistent pattern for success/error toasts (e.g. after “Layout saved”, form submit, payment) improves clarity.
- **Errors:** Friendly, actionable error pages (e.g. 404, 500) with a link back to dashboard or home reduce dead-ends.

---

## 7. Operations & compliance

- **Audit:** You have layout audit; consider what else should be logged (e.g. sensitive data access, role changes) for compliance.
- **Backups:** DB and any user-uploaded files; ensure backups and restore are tested.
- **Deploy:** You’ve documented “deploy from main”, “Clear build cache & deploy” on Render; keep that checklist updated when CI or static pipeline changes.

---

## 8. Documentation & maintainability

- **Runbooks:** Short runbooks for “reset user layout”, “clear dashboard cache”, “revert bad deploy” help future you or ops.
- **Env/config:** Document which env vars and feature flags affect dashboards, RBAC, and layout so new devs don’t miss them.
- **Deprecations:** If you ever retire the old “Drag & drop layout” checkbox or a legacy API, document the cutoff and migration path.

---

You don’t need to do all of this at once. Use it as a checklist: when you touch performance, a11y, mobile, security, or UX, refer back and tick off what you’ve addressed. The drag-and-drop and dashboard plans remain the main active improvements; this doc is the “other foreseeable improvements” to be aware of.
