# One Shell for Every Authenticated Page — Implementation Plan

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0 (one shell, one theme, one sidebar). [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md) §2–3.

**Current state:** Control plane has **one** shell (`control_plane_base.html` → `control_plane_skeleton.html` + `partials/control_plane_sidebar.html`). Tenant backend and portal use **separate** bases: `backend_base.html` (extends `portal_base.html`) and many templates extend `portal_base.html` directly. They share design tokens and some components (e.g. `studio_os/components/page_header.html`) but **do not** use a single AppShell component or the same chrome (navbar + sidebar) as the control plane.

**Target:** One shell for **every** authenticated page — same chrome (or same standard), same design system, same navigation pattern. Tenant backend and portal should either (a) use the same shell component as the control plane (with tenant-specific nav), or (b) use a single shared `app_shell.html` that both control plane and tenant extend, with context-driven sidebar/nav.

---

## 1. Current bases (no duplication of this list elsewhere)

| Base | Used by | Sidebar / nav |
|------|--------|----------------|
| `control_plane_skeleton.html` | Auth/error pages (no sidebar) | — |
| `control_plane_base.html` | All manager/control-plane content | `partials/control_plane_sidebar.html`; `CONTROL_PLANE_NAV` |
| `portal_base.html` | Tenant portal (parent, teacher, student, finance, etc.) and **backend_base** | Portal sidebar / nav (tenant-specific) |
| `backend_base.html` | Tenant backend (accounts, siteconfig, metadata, marketplace, etc.) | Extends portal_base; adds backend chrome/actions |
| `marketing/base_marketing.html` | Marketing (unauthenticated) | Marketing header/footer |

**Studio OS:** `studio_os/shell.html` extends `portal_base.html`; design system aligned via tokens.

---

## 2. Options for “one shell”

### Option A — Shared AppShell component (recommended path)

1. **Create** `templates/partials/app_shell.html`: one HTML structure (top bar + sidebar slot + main content). No nav items inside the partial; nav is injected by the extending template or a dedicated nav partial.
2. **Create** `templates/partials/app_shell_nav_control_plane.html` (current control plane sidebar content).
3. **Create** `templates/partials/app_shell_nav_tenant.html` (tenant backend/portal nav — current portal sidebar content).
4. **Refactor** `control_plane_base.html` to extend a new `app_shell_base.html` that includes `partials/app_shell.html` and passes `nav_partial="partials/app_shell_nav_control_plane.html"`.
5. **Refactor** `portal_base.html` to extend `app_shell_base.html` with `nav_partial="partials/app_shell_nav_tenant.html"`, preserving existing tenant nav structure and branding.
6. **Result:** One shell structure; two nav variants (control plane vs tenant). Same tokens, same layout; only nav content differs.

### Option B — Control plane shell structure reused for tenant

1. Use the **same** layout as `control_plane_base.html` (navbar + sidebar + main) for tenant backend/portal.
2. Replace tenant sidebar with a **tenant** nav (e.g. Dashboard, People, Finance, Studio OS, etc.) built from a single source (e.g. `TENANT_NAV` from context processor).
3. **Risk:** Large refactor of portal_base and all tenant pages; must preserve tenant branding and role-based nav.

### Option C — Document “one standard” without one file

1. Keep current bases but **enforce** that both control plane and tenant use the **same** design tokens, same layout pattern (top bar + left sidebar + main), and same component set (page_header, loading_empty_states, etc.).
2. **No** single `app_shell.html`; instead, `control_plane_base` and `portal_base` are the two “shells” that are **visually and structurally aligned** so they feel like one product.
3. **Status:** **DONE.** Both bases load the same design tokens and platform-fluid-everywhere.css; tenant sidebar is one partial (portal_sidebar.html), control plane one partial (control_plane_sidebar.html); same layout pattern (top bar + left sidebar + main); shared components (page_header, loading_empty_states). Option C completion gate satisfied.

---

## 3. Recommended next steps (complete the work)

1. **Decide** Option A, B, or C with product/engineering.
2. **If A:** Implement `app_shell_base.html` + `partials/app_shell.html` + two nav partials; migrate `control_plane_base` and `portal_base` to extend it. Run full regression (all links, all pages).
3. **If B:** Refactor tenant to use control-plane layout and tenant nav; same regression.
4. **If C:** Document “one standard” in this file and in CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL; complete any remaining alignment (single tenant nav source, shared top bar pattern).
5. **Phase H:** Include “one shell” in the manual checklist (every authenticated page uses the chosen shell/standard).

---

## 4. Completion gate (Option C)

- [x] One standard is implemented and documented: Option C (one standard, two shells aligned).
- [x] Every authenticated page uses control_plane_base (manager) or portal_base/backend_base (tenant); both use same tokens, same layout pattern, same components.
- [x] No authenticated page uses a base that omits the shared chrome or tokens; marketing uses base_marketing (unauthenticated).

---

*Source: RUNMYCAMPUS §8.0, §11 Phase H; CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §2–3.*
