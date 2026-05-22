# Admin shell: overlay-not-replace decision

**Status:** Durable architectural decision · v3.58.0 onward · reaffirmed v3.59.x Wave D (2026-05-22)
**Owner:** Platform shell · operator surface
**Surface affected:** `/admin/` (Django admin) on the manager host

---

## TL;DR

The `/admin/` shell is rendered by [Django Unfold](https://github.com/unfoldadmin/django-unfold) — a third-party admin theme that owns the page skeleton (`#container`, topbar, navigation, change-list, change-form). RunMyCampus does **not** replace that DOM. Instead, every v8/200x design refinement lands as a CSS overlay scoped to `body[data-rmc-admin-shell="1"][data-rmc-nav-bridge-host="manager"]`, plus carefully placed `{% block %}` extensions in `templates/admin/base_site.html`.

This is a deliberate choice, not a workaround. This doc explains why, what's in scope for the overlay, and what's out of scope.

---

## Why overlay, not replace

1. **Unfold ships ongoing improvements.** Upstream releases bring CSP fixes, accessibility wins, dark-mode polish. Forking the DOM would force us to merge every upstream change by hand. Overlay CSS rides along automatically.
2. **Change-list, change-form, inlines, and search are deeply integrated.** Django admin uses `ModelAdmin`-driven template hierarchy with hundreds of templates and template-tags. Replacing the skeleton would mean re-implementing every admin behavior, then matching FERPA / audit-log / RBAC guarantees that already work today.
3. **The preview HTML is a flat mockup, not a hierarchical template.** `docs/generated/preview_app_shell_admin_v1_200x.html` is a one-shot visual reference. Production admin pages must remain composable Django templates with `{% load %}` / `{% block %}` / `{% include %}`. The preview is an aesthetic *destination*, not a structural source.
4. **Tenant-host admin must stay vanilla.** When an operator on the manager host views `/admin/`, they get the v8 200x luxury chrome. When a tenant school admin views their own `/admin/`, they get vanilla Unfold (no manager branding bleed). The overlay's `[data-rmc-nav-bridge-host="manager"]` scope is what makes that bifurcation cheap.

---

## What's in scope for the overlay

The following preview-parity wins ship as pure CSS overlay + minimal template block extensions:

- **Stat-card / KPI re-skin** — serif display number, uppercase mono eyebrow, indigo→emerald radial-glow `::after`, trend-delta pill (dormant until template emits the element). See [`static/css/admin-200x-shell-overlay.css`](../static/css/admin-200x-shell-overlay.css) §"KPI stat-card".
- **Model catalog cards glass treatment** — linear-gradient surface, 14px radius, hairline border, hover lift, dashed footer divider. Targets `.rmc-admin-catalog-model-card`. See [`static/css/admin-200x-shell-overlay.css`](../static/css/admin-200x-shell-overlay.css) §"Catalog cards".
- **LIVE activity ticker chrome** — sticky band at top of canvas-body, mirrors the manager+tenant ticker chrome via the same `templates/partials/cockpit/_activity_ticker.html` partial. Wired into `{% block branding %}` with `{% if is_manager_host %}` outer gate. CSS is self-contained because the canonical `manager-cockpit-v7.css` keyframes aren't linked from `base_site.html` — re-declaring identical `@keyframes` is safe (browsers de-dupe by name).
- **Token cascade** — admin overlay reads from `--cp-chrome-bg`, `--cp-glow-indigo`, `--cp-glow-emerald`, etc. via `var(--token, <hex-fallback>)` chains. Categorical `/* off-token-allow: <reason> */` markers on rgba fallbacks keep the off-token-colors scanner at baseline 0.
- **Reduced-motion safety** — every hover lift / pulse / marquee includes a `@media (prefers-reduced-motion: reduce)` block.

---

## What's intentionally NOT in scope

The preview's `.cp-*` cockpit grammar includes layout primitives that have no counterpart in Unfold's DOM:

- `.rmc-app-shell` 3-row × 2-col grid skeleton — Unfold uses `#container` with its own grid; retrofitting would mean DOM surgery on every admin page.
- `.cp-header` luxury hero — Unfold owns the topbar; we extend it via `templates/components/admin_nav_bridge.html` (tenant-aware nav swap) instead of replacing.
- `.cp-filters` left-rail filter chrome — Unfold uses a modal/toggle filter UX, deeply integrated with `ModelAdmin.list_filter`. Different paradigm, not just a re-skin.
- `.cp-sidecar` change-form audit trail — would require new context resolvers + DRF audit query + responsive grid surgery on every change-form. Audit data is already accessible via the dedicated `/super/migration/audit/` operator view; the change-form sidecar is duplicative.

These items are **closed**, not deferred. If the design team wants any of them, they should propose an alternative that respects Unfold's DOM contract or accept that we'd need to migrate off Unfold entirely (a multi-quarter effort).

---

## Adding a new admin overlay rule (checklist)

When extending the overlay, every new CSS rule MUST:

1. Be scoped to `body[data-rmc-admin-shell="1"][data-rmc-nav-bridge-host="manager"]` (or a sub-selector). No exceptions.
2. Use `var(--token, <fallback>)` for every color / shadow / radius / motion value.
3. Carry a categorical `/* off-token-allow: <reason> */` marker on every rgba/hex fallback.
4. Honor `@media (prefers-reduced-motion: reduce)` for any animation, transition, or hover lift.
5. Pass all 12 zero-tolerance scanners (off-token-colors, theme-locked-token-text, undefined-css-classes, horizontal-overflow-risk, sticky-with-overflow-hidden, theme-attribute-contract, pii-logging-smell, reveal-armed-invariants, inline-style-off-token, ai-gateway-boundary, tenant-queryset-safety, template-render-safety).

Template-side changes MUST:

1. Extend an existing Unfold block (`{% block branding %}`, `{% block content %}`, etc.). Don't rewrite the parent template.
2. Double-gate every preview element: outer `{% if is_manager_host %}` + inner `{% if cockpit.<section>.enabled %}` (the partial's self-gate).
3. Use `{% comment %}…{% endcomment %}` for any multi-line comment. Single-line `{# … #}` only.

---

## Historical context

- **v3.58.0 (2026-05-22)** — `admin-200x-shell-overlay.css` introduced; commented decision to overlay rather than replace recorded inline.
- **v3.58.7 (2026-05-22)** — `/admin/` duplicate-notebook bug fixed by removing cockpit partials from `admin/base_site.html` that had been injected as a misguided "make admin match manager landing" attempt. Confirmed the overlay-not-replace pattern.
- **v3.59.4 Wave A (2026-05-22)** — KPI stat-card re-skin + catalog cards glass treatment shipped as overlay extensions.
- **v3.59.5 Wave B (2026-05-22)** — LIVE activity ticker wired into `{% block branding %}` with double-gating; CSS self-contained.
- **v3.59.7 Wave D (2026-05-22)** — this document.

---

## See also

- [`static/css/admin-200x-shell-overlay.css`](../static/css/admin-200x-shell-overlay.css) — the overlay itself
- [`templates/admin/base_site.html`](../templates/admin/base_site.html) — block extensions on top of Unfold
- [`templates/components/admin_nav_bridge.html`](../templates/components/admin_nav_bridge.html) — tenant-aware nav swap
- [`docs/generated/preview_app_shell_admin_v1_200x.html`](generated/preview_app_shell_admin_v1_200x.html) — the design destination (aesthetic, not structural)
- `CLAUDE.md` §"Engineering best-practices for big jobs" — scoping rules for overlay work
