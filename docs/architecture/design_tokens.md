# Design Tokens (Section 26.4, 29.8)

Single reference for RunMyCampus design tokens: CSS variables, density, navigation, and tenant branding. Align with WCAG 2.2 AA where applicable.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 26.4, 29.8; phase10_superadmin_vs_tenant_ui.md; section_28_data_architecture_and_provisioning.md § Brand vs site experience.

---

## 1. Tenant brand (site experience)

| Token / source | Description | Where set |
|----------------|-------------|-----------|
| `primary_color` | Primary brand color (buttons, links, accents) | School model; SiteSettings; super admin school edit |
| `accent_color` | Secondary/accent color | School; SiteSettings |
| `header_bg_color` | Header background | School / branding |
| `footer_bg_color` | Footer background | School / branding |
| `logo_url` | School logo URL | School model |
| ThemePack | Optional theme pack slug | Policy / SiteSettings |

**Injection:** `theme_root_variables` in backend_base (and tenant shells) inject CSS custom properties from School/siteconfig branding so templates and components use `var(--primary-color)` etc. Brand identity (name, logo, colors, typography, senders) is separate from site experience (portal theme, dashboard family, density, nav).

---

## 2. Shell and density

| Token / setting | Description | Values |
|-----------------|-------------|--------|
| **RESOLVED_BACKEND_CONSOLE_THEME** | Backend/superadmin theme | `dark` \| `light`; controls backend-dark-theme.css |
| Density | List/table density | High (superadmin), default (tenant), comfortable (portal) — via layout classes and spacing vars |
| `body_extra_class` | Shell identifier | e.g. `backend-shell`, `control-plane-shell` |

**Touchpoints:** `templates/backend_base.html`, `static/css/backend-dark-theme.css`, `static/css/manager-control-plane.css`. Superadmin: dark, high-density, operations-grade. Tenant: school-branded, role-centric.

---

## 3. Navigation and layout

- **Sidebar:** Role-based items from `portal_sidebar_items`; section grouping (e.g. Analytics & Reports, Admin Panel).
- **Dashboard family:** Dashboard template per role from dashboard_resolver; widgets and layout from TenantLayoutAssignment / policy.
- **Shell variants:** Public (marketing), manager (super), tenant (backend_base + portal_base).

---

## 4. CSS variables (theme engine)

Tenant theme overrides via Blueprint or School branding are applied as CSS custom properties so that:

- Buttons, links, and accents use `var(--primary-color)` (or equivalent).
- Header/footer use `var(--header-bg-color)`, `var(--footer-bg-color)`.
- Typography and spacing can be extended with tokens (e.g. `--font-family`, `--spacing-unit`) for future component library.

---

## 5. WCAG 2.2 AA alignment

- Contrast: Primary and accent colors should meet contrast requirements for text and UI components; document minimum contrast ratios in brand guidelines.
- Focus indicators: Visible focus styles for interactive elements (templates and global CSS).
- RTL: Policy `rtl` and language drive RTL layout where applicable (terminology from Blueprint).

---

## 6. Three density modes (target)

| Mode | Use case | Spacing / tables |
|------|----------|------------------|
| Compact | Superadmin, power users | Tighter padding; more rows per page |
| Default | Tenant backend | Standard list/table density |
| Comfortable | Portal, parent/student | Larger touch targets; readable |

Density can be driven by role or tenant setting and applied via body class or data attribute for CSS overrides.

---

## References

- policy_injection.md (branding, labels_map)
- phase10_superadmin_vs_tenant_ui.md (shells, dark theme, density)
- section_28_data_architecture_and_provisioning.md (brand vs site experience)
