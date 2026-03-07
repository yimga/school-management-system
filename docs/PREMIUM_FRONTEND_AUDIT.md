# Premium frontend audit — backlog, deferred, and four surfaces

This doc (1) confirms nothing material is left in backlog or deferred without tracking, (2) assesses the four **selected surfaces** (marketing, superadmin, workflow hub, dashboard manager) against a **premium frontend** standard, and (3) lists improvements and standards.

---

## 1. Backlog and deferred — status

### Backlog

| Source | Status | Notes |
|--------|--------|------|
| **MARKETING_PUBLIC_SURFACE_BACKLOG** | **Closed** | Waves 1–4 all `done`. No open `next` or `later` items. |
| **Waves 1–4** | Complete | Hero, CTAs, SEO, schema, funnel, A/B, geo/channel, buyer toolkit, trust ops. |
| **Marketing improvements plan** | Executed | Phases 1–8 (audit alignment, conversion, SEO, performance, analytics, content, add-ons, docs). |

### Deferred (all tracked)

Every deferred item is listed in **RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md** (“Deferred and optional items register”) and in **REMAINING_PLAN_AUDIT_GAPS.md**. Nothing is left untracked.

| Item | Type | Where tracked | Next step |
|------|------|----------------|-----------|
| **6.3 / 29.10** Tenant app billing (proration, invoice lines from ledger) | Deferred refinement | REMAINING_PLAN_AUDIT_GAPS.md | Optional: proration + invoice line generation. |
| **11.2** Tenant “Get blueprints” + pack versioning UI | Deferred refinement | REMAINING_PLAN_AUDIT_GAPS.md | Add tenant backend entry (e.g. Blueprint gallery). |
| **1.8** Secure app sandbox (CSP, origin checks) | Next | REMAINING_PLAN_AUDIT_GAPS.md | Implement per sandbox_hardening_checklist_1_8.md. |
| **26.5** UX rules (search/filter/export, autosave/draft) | Next | REMAINING_PLAN_AUDIT_GAPS.md, ux_rules_audit_26_5.md | Prioritise per audit table. |
| **Control plane maturity** | Next | REMAINING_PLAN_AUDIT_GAPS.md | Refine SLO/incident data, runbooks URL, support queue. |
| **Migration cloud** rollback / legacy cleaner / read-only legacy view | Deferred | Consolidated doc | Optional when productised. |
| **13.2** models.png (architecture) | Optional by decision | Consolidated doc | Add if desired. |

**Conclusion:** No open backlog items are unassigned. All deferred work is documented with a single tracking doc and clear next step.

---

## 2. Premium frontend standard (reference)

**Premium frontend** for the selected surfaces means:

- **Design system:** Consistent tokens (spacing, color, typography), semantic use of primary/accent and state colors (success, warning, error). See [THEME_COMPONENT_KITS.md](THEME_COMPONENT_KITS.md) and `static/css/design-tokens.css`.
- **Hierarchy:** Clear page title, eyebrow or section labels, and structured sections (hero → content → actions). No single flat card when the page is a “hub” or dashboard.
- **Polish:** Appropriate shadows, borders, and radius; responsive layout; accessible contrast (WCAG AA).
- **Surfaces in scope:** Marketing (public), Superadmin (manager), Workflow hub (tenant), Dashboard manager (tenant backend).

---

## 3. Assessment by surface

### 3.1 Marketing

| Criterion | Status | Notes |
|-----------|--------|------|
| Design system | **Meets** | Dedicated `marketing-home.css` with `--mkt-*` tokens, hero, sections, sticky CTA. |
| Hierarchy | **Meets** | Hero (headline, subheadline, Trusted for, CTAs) → sections (proof, modules, migration, testimonials, final CTA). |
| Polish | **Meets** | Gradients, shadows, radius, responsive; preconnect for analytics. |
| Standards | **Meets** | Aligns with world-class SaaS front; optional critical CSS/WebP documented. |

**Improvements (optional):** Critical CSS inline for hero LCP; WebP/AVIF for hero images; typography scale doc for marketing.

---

### 3.2 Superadmin (manager control plane)

| Criterion | Status | Notes |
|-----------|--------|------|
| Design system | **Meets** | `manager-control-plane.css` with `--cp-*` tokens (navy/gold, panels, chips, tables). |
| Hierarchy | **Meets** | Hero (eyebrow, title, copy, chips, north-star stat, actions) → section nav → queue, fleet health, footprint, tenant registry, readiness, risk. |
| Polish | **Meets** | Dark shell, gradients, cp-panel/cp-card grid, layout customization modal, responsive. |
| Standards | **Meets** | Control plane skeleton/base, manager login, error pages; distinct from tenant. |

**Improvements (optional):** SLO/incident runbooks refinement; optional dashboard export polish.

---

### 3.3 Workflow hub (tenant)

| Criterion | Status | Notes |
|-----------|--------|------|
| Design system | **Partially** | Uses `portal_base` + `professional-page` + generic card; no hub-specific tokens. |
| Hierarchy | **Gap** | Single card with two links (Approval hub, Flow gallery); no hub hero or section structure. |
| Polish | **Gap** | Minimal; feels like a placeholder. |

**Improvements (done in code):** Use hub premium shell: hub-hero (eyebrow + title + copy) + hub action cards (icon, title, description, CTA) so the page feels like a dedicated hub. See `static/css/hub-premium.css` and updated `workflow_hub.html`.

---

### 3.4 Dashboard manager (tenant backend + dashboard hub)

| Criterion | Status | Notes |
|-----------|--------|------|
| Backend dashboard | **Meets** | `backend_base.html` + dashboard-auto-grid, layout controls, theme (dark/light), drag-and-drop; design tokens and spacing. |
| Dashboard hub entry | **Gap** | Single card + one CTA (“Configure dashboards by role”); no hub hero or multi-section layout. |

**Improvements (done in code):** Apply same hub premium shell to Dashboard hub: hub-hero + action card(s) so it aligns with workflow hub and feels premium. Dashboard configuration page already has table and form; keep that and elevate the hub entry page.

---

## 4. Summary and code standards

- **Backlog / deferred:** All closed or tracked; no untracked backlog.
- **Marketing:** Meets premium standard.
- **Superadmin:** Meets premium standard.
- **Workflow hub:** Upgraded with hub premium shell (hero + action cards).
- **Dashboard hub:** Upgraded with hub premium shell (hero + action cards).

**Code standards for these surfaces:**

1. Use semantic tokens (e.g. `--school-primary`, `--cp-accent`) and avoid raw hex in layout CSS where a token exists.
2. Hub pages (workflow hub, dashboard hub): use `.hub-page`, `.hub-hero`, `.hub-action-card` and load `hub-premium.css` so hierarchy and polish are consistent.
3. Contrast: aim for WCAG AA; use THEME_COMPONENT_KITS state colors for success/warning/error.
4. New marketing/superadmin/hub UI: follow existing patterns in `marketing-home.css`, `manager-control-plane.css`, and `hub-premium.css`.

---

## 5. Platform-wide premium feel (all pages)

So that **every** portal and backend page has a consistent high-end feel, the platform uses a single global content layer loaded for all tenant pages:

| Layer | File | Scope | Effect |
|-------|------|--------|--------|
| **Premium content** | `static/css/platform-premium-content.css` | `#main-content .page-wrap` (portal_base) | Cards: radius, shadow, border. Headings: hierarchy. Tables: thead styling, row hover. Alerts: radius and border. Forms: focus ring, spacing. Buttons: radius. List groups and empty states: polish. |

- **Loaded in:** [templates/portal_base.html](../templates/portal_base.html) (after portal-layout-professional.css) and [templates/base.html](../templates/base.html). Every page that extends `portal_base`, `backend_base`, or `base` receives this styling. Content is wrapped in `#main-content` and `.page-wrap` so the same selectors apply (portal_base has both; base has `main#main-content` and a `.page-wrap` div around `{% block content %}`).
- **base.html pages:** Error pages (404, 403, 500, 429), funnel dashboard, find_school, signup, verify, auth flows, and any other page extending `base` (e.g. compliance dashboard, profile, onboarding) now get the same premium cards, alerts, tables, and buttons. [base.html](../templates/base.html) also loads Bootstrap Icons and `platform-premium-content.css` so icons and premium styling are consistent.
- **Design tokens:** Uses `design-tokens.css` and `design-system-unified.css` (e.g. `--radius-md`, `--shadow-md`, `--school-primary`, `--admin-content-*`, `--portal-border`). No new tokens; everything stays themeable.
- **Surfaces not using portal_base/base content block:** Marketing landing uses `marketing_base` + `marketing-home.css` (its content is still inside base’s `.page-wrap` so card/alert rules can apply where classes match). Manager (superadmin) uses `control_plane_skeleton` + `manager-control-plane.css`. Auth login uses `base.html` with its own auth-hero. Admin uses Unfold. Each has a dedicated shell; the global layer covers all other content.

**Result:** All portal/backend content pages share one premium content standard (cards, tables, forms, headings, alerts) so the entire platform feels consistent and high-end.

---

## 6. Checklist — coverage and optional follow-ups

| Item | Status |
|------|--------|
| Backlog / deferred all tracked | Done — REMAINING_PLAN_AUDIT_GAPS + consolidated register. |
| Marketing premium | Done — marketing-home.css, sticky CTA, hero, preconnect. |
| Superadmin premium | Done — manager-control-plane.css, cp-hero, panels. |
| Workflow hub / Dashboard hub premium | Done — hub-premium.css, hero + action cards. |
| Platform-wide content (portal + base) | Done — platform-premium-content.css in portal_base and base; .page-wrap in base. |
| Bootstrap Icons on base pages | Done — base.html loads bootstrap-icons so 404, funnel, etc. show icons. |
| Error pages (404, 403, 500) | Covered — extend base, now inside .page-wrap, get premium cards/buttons. |
| Funnel dashboard, find_school, signup, auth | Covered — extend base, get premium layer. |
| Lighthouse/pa11y in CI | Documented in qa.md; add workflow when runner is ready. |
| Exit-intent / scroll lead capture | Optional — documented in plan; implement when needed. |
| ROI calculator, comparison PDF, newsletter | Optional add-ons — implement when productised. |
| Legal footer on all public pages | Done — base.html shows Privacy \| Terms \| Cookie when PUBLIC_BRAND_MODE (e.g. /pricing/, /product/, signup). |
| Marketing env vars documented | Done — .env.example includes MARKETING_CALENDLY_URL, MARKETING_DEMO_WEBHOOK_URL. |

**References:** [THEME_COMPONENT_KITS.md](THEME_COMPONENT_KITS.md), [REMAINING_PLAN_AUDIT_GAPS.md](architecture/REMAINING_PLAN_AUDIT_GAPS.md), [phase10_superadmin_vs_tenant_ui.md](architecture/phase10_superadmin_vs_tenant_ui.md), [MARKETING_PAGE_AUDIT.md](MARKETING_PAGE_AUDIT.md).
