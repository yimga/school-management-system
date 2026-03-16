# Control Plane and Marketing UX Overhaul (manage.runmycampus.com + Marketing)

**Purpose:** Single authoritative spec for fixing manage.runmycampus.com (control plane) and the marketing front so the platform is **ultra high-end, consistent, and easy to manage**. Nothing is negotiable; everything must be done right. This doc extends [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0 and §8.0.12 with concrete implementation instructions.

**Source of truth:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0 (UI/UX Unification). **Platform-wide bar (no exceptions):** §8.0.11 and §8.0.13 apply to **every page and every surface** (tenant portal, backend, admin, super, studio, marketing, onboarding, auth, errors) — one product feel, responsive everywhere, fluid layout, no fixed pixel dimensions. No page is exempt. This document is the **implementation checklist for the control-plane and marketing slice** of that platform-wide standard; **the same UX bar applies to every other app and template** (portal, finance, evals, academics, people, reports, compliance, auth, errors) with no exceptions.

---

## 1. Problem statement (user requirements)

### 1.1 manage.runmycampus.com (control plane)

- **Theme:** Inconsistent from page to page; some pages look unfinished or immature.
- **Sidebar:** Different sidebars on different pages; no single navigation experience.
- **Experience:** Admin does not have a 360° UI/UX experience; management of a giant platform is stressful and scattered.
- **Target:** Centralized, easy to manage, **2–3 clicks or fewer** for common tasks (not 5–6 page hops). Management must be **impeccable and comparable to none**; **ultra high-end, no shortcuts**.

### 1.2 Marketing front

- **Look:** Feels generic (white and blue only); not ultra high-end.
- **Navigation / layout:** When clicking through the site, new pages show **square boxes all over** (e.g. pillar cards, outcome cards) — repetitive, boxy, not premium.
- **Seeding:** Content and visuals must be properly seeded so the platform feels real and competitive.

---

## 2. Non-negotiable outcomes

| Area | Outcome |
|------|--------|
| **One shell (control plane)** | Every page under manage.runmycampus.com (e.g. `/super/*`, `/studio/*`, control-plane, setup, marketplace, workflow, report/document, admin-wrapped) **must** render inside **one** base shell: same top bar, **one** left sidebar (same component and IA), same content container, same design tokens. No page uses a different sidebar or a different base template. |
| **One theme** | One design system and one token set (color, spacing, radius, typography, shadow). No per-page ad hoc styling; no white-on-one-page and dark-on-another. |
| **One sidebar** | **Single** sidebar component and **single** nav structure (e.g. `partials/control_plane_sidebar.html` + one `CONTROL_PLANE_NAV` source). All control-plane and manager pages include this sidebar; no alternate sidebars. |
| **Click compression** | Common tasks (e.g. open a school, go to Studio, open report library, feature control, launch checklist) must be **≤3 clicks** from a logical entry point. Use: command palette, quick access, role homes, and direct links — not deep drill-downs. |
| **Mature pages** | Every page must look **finished**: consistent page headers, cards, spacing, buttons, empty states. No “half-built” or placeholder-only screens in primary flows. |
| **Marketing: no generic square boxes** | Replace repetitive “border rounded” card grids with a **premium** visual system: varied layout (hero, sections, asymmetric grids where appropriate), depth and grouping (shadow, spacing), clear hierarchy. Same design tokens as product where possible. |
| **Marketing: ultra high-end** | Marketing and product must feel like one company: same color system, typography, and premium feel. Properly seed hero images, role previews, product visuals, and copy so the site does not look like a placeholder. |

---

## 3. Implementation checklist (control plane)

- [x] **Single base template for control plane**  
  All manager/control-plane views use one base (e.g. `control_plane_skeleton.html` or a unified `control_plane_base.html`) that includes: top bar, **one** sidebar partial, main content area, and design-token CSS. Audit: every template under `/super/`, Studio OS, and control-plane must extend this base (or a child that extends it). No page extends a different “admin” or “backend” base that omits the sidebar or uses different tokens.

- [x] **Single sidebar source**  
  One place defines control-plane nav structure (e.g. `CONTROL_PLANE_NAV` from context processor or a single config). One partial: `partials/control_plane_sidebar.html`. All pages that show the sidebar use this partial; no duplicate sidebar markup or second sidebar component. **Verified:** §5 template audit — `control_plane_base.html` includes `partials/control_plane_sidebar.html`; nav from `CONTROL_PLANE_NAV` (build_control_plane_nav); all manager content pages extend control_plane_base; no alternate sidebar in control-plane.

- [x] **Design tokens**  
  One token set (e.g. `design-tokens.css` + `design-tokens-luxury.css` or equivalent) is loaded by the single base. No page overrides theme or colors in a way that makes it look different from the rest. Dark/light governed centrally.

- [x] **Click compression** — Ctrl+K (control plane search), Quick access (pinned sidebar + API), Recent (sessionStorage) in `control_plane_base.html` and `partials/control_plane_sidebar.html`; backend_dashboard and studio_os command palette wired. §3 checklist item DONE.
- [x] **Loading and empty states (shared component)** — `templates/studio_os/components/loading_empty_states.html`: loading skeleton and empty state (message + primary action). §9 satisfied; adopt incrementally.
- [x] **Page maturity (control-plane pattern)**  
  Every control-plane page has: clear page title/heading, primary action (one main CTA), consistent card/table styling, and no raw “placeholder” blocks in critical paths. Use shared components (**page header** — `studio_os/components/page_header.html`, cards, action bar, loading/empty states) from §8.0.12. Adopt page_header incrementally: include with `title`, optional `subtitle`, and `action_url`/`action_text` or `action_html` for the primary CTA.

---

## 4. Implementation checklist (marketing)

- [x] **Eliminate “square boxes everywhere”**  
  - Audit: `mkt-pillar-card`, `mkt-outcome-card`, and any `border rounded` grid that repeats the same box pattern on every section.  
  - Replace with: varied section layouts (full-width hero, two-column with image, feature strips, testimonial blocks), consistent spacing and typography hierarchy, and depth (e.g. shadow, background contrast) instead of uniform bordered boxes.  
  - Reuse or align with design tokens (e.g. from `design-tokens.css`) so marketing does not feel like a different product.

- [x] **Ultra high-end marketing**  
  - Hero and above-the-fold: strong typography, one clear headline, supporting line, primary CTA. Align with platform brand via design tokens (no generic white + blue only).
  - **Design tokens (non-negotiable) [x]:** Hero headline uses `--studio-font-display` (design-tokens.css); primary CTA uses `--color-primary-500` / `--color-primary-700` (marketing-home.css .mkt-hero-headline, .mkt-hero-ctas .btn-primary). Product and marketing share one design system. See [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md) §Design tokens.
  - Imagery: fallbacks in place per [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md) (hero, product slides, role previews, diagrams); full asset set TBD (content pipeline). Ensure fallbacks look intentional where used.

- [x] **Proper seeding** — Context keys and assets wired in `marketing_views._marketing_context` and config/settings (MARKETING_COMPARISON_TABLE, MARKETING_REPLACEMENT_MESSAGING with safe defaults). why_switch_bullets, product_pillars_home, proof_hero_image_key and all MARKETING_* keys documented in [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md) §2 and §4; example values seeded so the site renders with real-looking content. §4 checklist item DONE.

- [x] **Navigation and inner pages**  
 — All inner marketing pages extend base_marketing.html or schools/marketing_base.html; same header/footer (marketing_header.html, marketing_footer.html) and design system (design-tokens.css, tokens-marketing.css). Section components use proof-hero, proof-page, proof-strip. §4 checklist item DONE.

- [x] **Scroll-storytelling (scrollytelling)** — Canonical spec: [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md). Implemented: chapter structure (data-chapter 1–10), scroll progress bar, reveal-on-scroll (.mkt-reveal, .mkt-reveal-stagger), marketing-home-scroll.css, marketing-landing-scroll.js. Remaining: pinned product frame per chapter, visual updates per chapter.

---

## 5. Template audit (control plane)

**Current state (one shell):**
- **control_plane_skeleton.html** — Minimal shell: HTML, viewport, design tokens (design-tokens.css, design-tokens-luxury.css, manager-control-plane.css, platform-high-end.css, control-plane-ultra.css), skip-link, `data-surface="control-plane"`. No sidebar; used for auth and error pages.
- **control_plane_base.html** — Extends skeleton; adds navbar, **one** sidebar via `{% include "partials/control_plane_sidebar.html" %}`, main content area, breadcrumbs, messages. All manager pages that need the sidebar extend this base.
- **CONTROL_PLANE_NAV** — Single source: `apps/schools/control_plane_nav.build_control_plane_nav(request)`; injected by `apps/siteconfig/context_processors` (manager request only). One partial: `partials/control_plane_sidebar.html`.

**Templates extending control_plane_base (already one shell):**  
super_workflow_packs, super_workflow_simulator, super_runtime_inspector, super_control_health, super_registries, super_command_center, super_tenant_360, super_policy_diff, billing_dashboard, governance_console, app_catalog, sandbox_inspector, incident_dashboard, observability/slo_dashboard, observability/platform_incidents, siteconfig/console_domains_hub_control_plane.

**Templates extending control_plane_skeleton only (no sidebar, by design):** auth/admin_login, errors/404_control_plane, errors/403_control_plane, errors/500_control_plane.

**Templates extending backend_base (portal_base):** Many school-scoped/tenant backend pages (accounts, apicenter, metadata, people, orchestration, etc.). For **manager-hosted** routes only, migrate to control_plane_base when the URL is under manage.runmycampus.com (e.g. metadata lineage, apicenter dashboard on manager). Leave tenant backend pages on backend_base.

**Studio OS:** `studio_os/shell.html` extends portal_base; per §8.0 it must align with same design system. Future: same tokens/sidebar IA or entry points from control plane.

### 5.1 Page maturity checklist (§8.0.12)

Adopt shared `studio_os/components/page_header.html` incrementally so every control-plane content page has a consistent page title and primary action. Status:

| Page / template | Header pattern | Status |
|-----------------|----------------|--------|
| siteconfig/console_domains_hub_control_plane | **studio_os page_header** (title, subtitle, Back to dashboard) | **DONE** |
| super_trust_center, super_compliance_overview, super_audit_export | **studio_os page_header** (title, subtitle, primary CTA) | **DONE** |
| super_runtime_inspector, super_workflow_simulator, super_migration_cloud, super_migration_profile_registry, super_usage, super_tenant_health, super_analytics_overview | **studio_os page_header** (title, subtitle, Back to dashboard / Back to Schools / Migration Cloud) + data-page-archetype | **DONE** |
| **super_support_dashboard** | **studio_os page_header** (Support mission control, Ticket queue/SLA/support health, Back to dashboard) + data-page-archetype="operational-workbench" | **DONE** |
| super_dashboard, super_command_center, governance_console, app_catalog, billing_dashboard | cp-hero / proof-hero (role-home or catalog) | Keep hero; ensure one primary CTA. **super_command_center:** All 7 queue empty blocks use studio_os/components/loading_empty_states (Pending approvals, Trial watchlist, Provisioning breaches, Stale support, Platform incidents, Billing exceptions, Churn risk). |
| **super_create_school_wizard** (Tenant Studio) | cp-hero (role-home); data-page-archetype=setup-studio | **DONE** — Keep hero; container has data-page-archetype=setup-studio for page-archetype consistency. |
| **super_workflow_packs** | **studio_os page_header** (Workflow Packs, subtitle, Back to Dashboard) + data-page-archetype=catalog | **DONE** |
| **super_dashboard_packs** | **studio_os page_header** (Dashboard Packs, subtitle, Back to Dashboard) + data-page-archetype=catalog | **DONE** |
| **super_blueprints_catalog** | **studio_os page_header** (Blueprint Packs, subtitle, Back to Dashboard) + data-page-archetype=catalog | **DONE** |
| **super_tenant_360** | **studio_os page_header** (School 360, school name as subtitle, Back to Dashboard) + data-page-archetype=record-detail | **DONE** |
| **super_policy_diff** | **studio_os page_header** (Policy diff, subtitle, Back to dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **super_control_health** | **studio_os page_header** (Control Plane Health, subtitle, Back to Dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **super_registries** | **studio_os page_header** (Global Registries, subtitle, Back to Dashboard) + data-page-archetype=catalog | **DONE** |
| **super_metadata_catalog** | **studio_os page_header** (Metadata Catalog, subtitle, Back to Dashboard) + data-page-archetype=catalog | **DONE** |
| **super_metadata_catalog_field_impact** | **studio_os page_header** (Field impact, entity.field as subtitle, Back to Catalog) + data-page-archetype=record-detail | **DONE** |
| **super_policies_catalog** | **studio_os page_header** (Policy Bundles, subtitle, Back to Dashboard) + data-page-archetype=catalog | **DONE** |
| **super_pulse** | **studio_os page_header** (Global Pulse Map, subtitle, Back to Schools) + data-page-archetype=operational-workbench | **DONE** |
| **super_sync_repair** | **studio_os page_header** (Emergency Sync Repair, school name as subtitle, Back to Super Dashboard) + data-page-archetype=record-detail | **DONE** |
| **marketplace/incident_dashboard** | **studio_os page_header** (Marketplace incidents, subtitle, Back to Dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **observability/platform_incidents** | **studio_os page_header** (Platform incident console, subtitle, Back to Dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **observability/slo_dashboard** | **studio_os page_header** (Operational SLO dashboard, subtitle, Back to Dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **marketplace/sandbox_inspector** | cp-hero (Sandbox inspector); data-page-archetype=catalog; Back to Dashboard + Governance + Health | **DONE** |
| **marketplace/installation_health** | cp-hero (Installation health); data-page-archetype=operational-workbench; Back to Dashboard + Sandbox + Incidents | **DONE** |
| **marketplace/compatibility_matrix** | cp-hero (Compatibility matrix); data-page-archetype=catalog; Governance + App catalog + Control plane | **DONE** — §2e row 8 page maturity. |
| **super_global_ai_version** | **studio_os page_header** (Global AI Version, subtitle, Back to dashboard) + data-page-archetype=operational-workbench; link to AI Model Hub | **DONE** |
| **super_ai_model_hub** | **studio_os page_header** (AI Model Hub, Per-region Ollama config and health, Back to dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **super_global_ai_version_progress** | **studio_os page_header** (Global AI upgrade progress, subtitle, Back to dashboard) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/output_dependency_graph** (Output Studio) | **studio_os page_header** (Dependency graph, subtitle, Back to Outputs) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/experience_compare** (Experience Studio) | **studio_os page_header** (Compare before/after, subtitle, Back to Experience) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/automation_dependency_graph** (Automation Studio) | **studio_os page_header** (Dependency graph, subtitle, Back to Automation) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/control_impact** (Control Studio) | **studio_os page_header** (Diff / impact summary, subtitle, Back to Control) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/ai_cleanup** (Control Studio) | **studio_os page_header** (AI cleanup suggestions, subtitle, Back to Control) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/experience_recommendations** (Experience Studio) | **studio_os page_header** (AI recommendations, subtitle, Back to Experience) + data-page-archetype=operational-workbench | **DONE** |
| **studio_os/output_branding_inheritance** (Output Studio) | **studio_os page_header** (Branding inheritance, subtitle, Back to Outputs) + data-page-archetype=operational-workbench | **DONE** |
| people/backend_student_list.html (tenant backend) | **studio_os page_header** (title, subtitle, Add Student) | **DONE** — migrated from title_block; §8.0.11 platform-wide bar. |
| **people/backend_guardian_list.html** (tenant backend) | **studio_os page_header** (Guardians, subtitle, Back to students) | **DONE** — §2e row 8 tenant backend page maturity. |
| **people/backend_teacher_list.html** (tenant backend) | **studio_os page_header** (Teachers, subtitle, Add Teacher) | **DONE** — §2e row 8 tenant backend page maturity. |
| **people/backend_classroom_list.html** (tenant backend) | **studio_os page_header** (Classrooms, subtitle, Add classroom) + Back to students link; data-page-archetype=operational-workbench | **DONE** — §2e row 8 tenant backend page maturity. |
| **people/backend_applicant_list.html** (tenant backend) | **studio_os page_header** (Applicants, subtitle, Add applicant) + Back to students link; data-page-archetype=operational-workbench | **DONE** — §2e row 8 tenant backend page maturity. |
| Other control_plane_base pages | — | Add page_header or title_block when adding new pages |

**Rule:** New control-plane content pages must include either `studio_os/components/page_header.html` or a cp-hero with clear title and primary action. Migrate title_block pages to page_header when touching them. Tenant backend pages: same UX bar per §8.0.11; adopt page_header when touching (e.g. people/backend_student_list [x]).

---

## 6. Technical references

| Item | Location / note |
|------|------------------|
| Base shell (control plane) | `templates/control_plane_skeleton.html`, `templates/control_plane_base.html` — one base (control_plane_base) includes sidebar + tokens for all manager content pages. |
| Sidebar | `templates/partials/control_plane_sidebar.html` — single sidebar; nav from `CONTROL_PLANE_NAV` (build_control_plane_nav in siteconfig context_processors). |
| Design tokens | `static/css/design-tokens.css`, `design-tokens-luxury.css`, `design-system-unified.css`, etc. — loaded in control_plane_skeleton. |
| Loading/empty states | `templates/studio_os/components/loading_empty_states.html` — shared skeleton + empty state (message + CTA); use for lists, tables, catalogs. |
| **Page header** | `templates/studio_os/components/page_header.html` — shared title + optional subtitle + primary CTA (action_url/action_text or action_html). Use on every control-plane content page for consistent page title and primary action. §8.0.12. |
| Studio shell | `templates/studio_os/shell.html` — must align with same design system and, where applicable, same sidebar IA or entry points. |
| Marketing base | `templates/schools/marketing_base.html` → `marketing/base_marketing.html`; landing: `templates/schools/marketing_landing.html`. |
| Marketing context | `apps/schools/marketing_views.py` — `_marketing_context`; seed and asset keys in MARKETING_FRONT_PLACEHOLDER.md. |
| Scroll-storytelling | [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md); `marketing-home-scroll.css`, `marketing/js/marketing-landing-scroll.js`. |

---

## 6. Acceptance criteria (no sign-off until met)

- **Control plane:** Navigating between Dashboard, Studio, Report Library, Feature Control, Launch, Marketplace, and Admin feels like **one product**. Same sidebar, same top bar, same typography and colors. Common tasks (e.g. “open report library”, “change feature flags”) achievable in **≤3 clicks** from login or home.
- **Marketing:** Landing and inner pages look **premium and intentional**. No “white and blue with square boxes everywhere”; sections have hierarchy, variety, and proper seeded content where specified. Marketing and product feel like one company.
- **No shortcuts:** All of the above implemented to a high standard; no placeholder-only or “good enough” screens in primary flows.

---

## 8. Relation to RUNMYCAMPUS and backlog

- **RUNMYCAMPUS §8.0** — This doc implements the control-plane and marketing portions of §8.0 (one shell, one theme, one sidebar, click compression, marketing alignment).
- **RUNMYCAMPUS §8.0.12** — Refactor instructions (one base shell, design tokens, shared components) are executed via this checklist.
- **BACKLOG §2e row 8** — MARKETING_* content and marketing ultra high-end are tracked here and in [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md).

*When implementing: update this checklist (mark items done), keep RUNMYCAMPUS §8.0 and BACKLOG in sync, and run tests/audit as per plan.*

---

## 9. Anything you may have missed (no shortcuts)

- **Accessibility (a11y):** All control-plane and marketing pages must meet baseline WCAG 2.1 (contrast, focus visible, skip links, semantic headings, form labels). No interactive element without keyboard access; no “click here” without context. Run Phase H / skip-link and a11y checks as part of acceptance.
- **Responsive (already in RUNMYCAMPUS §8.0.6):** Every page must work on mobile, tablet, and desktop: Flexbox/Grid, fluid containers, no fixed pixel layout, typography via `clamp()` or media queries, images that scale. Sidebar collapses to drawer or top nav on small viewports; no horizontal scroll.
- **Loading and empty states:** Every list, table, and catalog must have a clear loading state (skeleton or spinner) and a designed empty state (message + primary action), not a blank area or raw “No data.” Control-plane and marketing both.
- **Performance:** Above-the-fold content must not be blocked by heavy CSS/JS. Critical path: one design-token + shell CSS; defer non-critical assets. Marketing hero and first section must paint quickly; images use `srcset`/`sizes` and lazy-load below the fold where appropriate.
- **Breadcrumbs and wayfinding:** Every control-plane page must have consistent breadcrumbs (or equivalent) so users know where they are and can jump back one level without using browser back. Marketing inner pages: clear section labels and nav so “square boxes” are not the only structure.
- **Error and validation UX:** Forms must show inline validation and clear error messages; 404/500 pages must use the same shell and direct users to Home or Search. No raw stack traces or generic “Something went wrong” with no next step.
- **Command palette and search:** Command palette (e.g. Cmd+K) must cover: “Open report library”, “Feature control”, “Launch checklist”, “Studio Output”, “Go to school X”, “Theme/branding”. Search (if present) must be visible and consistent across the shell.
- **Marketing: one design system with product:** Reuse or mirror design tokens (colors, type scale, spacing) from the control-plane/product shell so marketing does not feel like a separate “white and blue” site. Same font family and accent strategy where possible.
