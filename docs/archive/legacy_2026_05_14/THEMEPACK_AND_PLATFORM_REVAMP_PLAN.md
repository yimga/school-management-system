# ThemePack & Platform Revamp Plan

## Overview
Revamp ThemePacks and platform UI to be **professional, school-focused, classy, creative, and easy to read**. Support all theme modes: **dark, light, system, high contrast**. Remove watermark/background images platform-wide. Improve sidebars.

---

## 1. ThemePack Revamp

### Goals
- **Professional**: Clean typography, organized hierarchy, suitable for education institutions
- **School-focused**: Inspired by LMS dashboards (Kiaalap, EduAdmin), Soft UI, AdminLTE, Material Dashboard
- **Classy & creative**: Distinct palettes without being overwhelming
- **Readable**: WCAG AA/AAA contrast, friendly fonts, adequate spacing
- **Mode support**: Each pack defines variants for light, dark, system (auto), high-contrast

### Theme Mode Matrix
| Mode | Description | Implementation |
|------|-------------|----------------|
| **Light** | Default light background, dark text | `palette.portal` / `palette.admin_dashboard` (light vars) |
| **Dark** | Dark background, light text | `palette.portal_dark` / `palette.admin_dashboard_dark` |
| **System** | Follows OS `prefers-color-scheme` | JS/runtime selection of light vs dark |
| **High contrast** | WCAG AAA, strong borders, minimal gradients | Dedicated high-contrast palette keys |

### Proposed School-Focused ThemePacks

| Pack | Slug | Primary | Accent | Use Case |
|------|------|---------|--------|----------|
| **Gilead Academic** | `academic-slate` | #475569 | #0ea5e9 | Neutral, professional, K-12 |
| **Campus Blue** | `campus-blue` | #2563eb | #38bdf8 | Trust, calm, institutional |
| **Forest Academy** | `forest-academy` | #059669 | #34d399 | Nature, growth, learning |
| **Sunset Study** | `sunset-study` | #d97706 | #fbbf24 | Warm, energetic, creative |
| **Midnight Scholar** | `midnight-scholar` | #3b82f6 | #818cf8 | Dark, focused, analytics |
| **Snow White** | `snow-white` | #0c4a6e | #0ea5e9 | Cool, clean, minimal |
| **Sand Classroom** | `sand-classroom` | #b45309 | #fde68a | Warm light, low glare |
| **Indigo Lecture** | `indigo-lecture` | #4f46e5 | #818cf8 | Modern, tech-forward |
| **High Contrast Light** | `high-contrast-light` | #000 | #0066cc | Accessibility |
| **High Contrast Dark** | `high-contrast-dark` | #60a5fa | #93c5fd | Accessibility |

### Palette Schema (Extended)
Each ThemePack palette supports:
```json
{
  "portal": { /* light mode portal colors */ },
  "portal_dark": { /* dark mode portal colors */ },
  "admin_dashboard": { /* admin/backend light */ },
  "admin_dashboard_dark": { /* admin/backend dark */ },
  "high_contrast_light": { /* WCAG AAA light */ },
  "high_contrast_dark": { /* WCAG AAA dark */ }
}
```

---

## 2. Watermark & Background Image Removal

### Locations to Update
| File | Change |
|------|--------|
| `templates/base.html` | Already disabled `.app-container::before` logo. Remove `SITE_BACKGROUND_URL` from `body` background. |
| `templates/portal_base.html` | Replace `SITE_BACKGROUND_URL` body background with solid gradient. |
| `templates/auth/login.html` | Replace `SITE_BACKGROUND_URL` with solid color. |
| `templates/admin/index.html` | Remove `SITE_ADMIN_BACKGROUND_URL` from body `background-image`. |
| `templates/reports/term_report_cameroon.html` | Remove `body::before` logo background. |
| `templates/reports/annual_report_cameroon.html` | Same. |
| `templates/components/logo_watermark.html` | Delete file (no longer included). |

### Sidebar Backgrounds
- **Portal sidebar**: Use solid `var(--portal-surface)` or theme surface color; no background images.
- **Admin sidebar**: Unfold default; ensure no logo/watermark in sidebar area.

---

## 3. Sidebar Improvements

### Admin Sidebar (`/admin`)
- **Typography**: Slightly larger, clearer section titles
- **Spacing**: More padding between app groups
- **Active state**: Stronger left-border accent, clear contrast
- **Icons**: Consistent Material Symbols sizing
- **Collapsed mode**: Ensure labels hide cleanly, icons remain centered
- **Scroll**: Thin scrollbar, smooth scroll behavior

### Portal Sidebar
- **Visual hierarchy**: Clear section titles, adequate spacing
- **Nav pills**: Hover/active states using theme primary
- **Avatar/header**: Clean, no background images
- **Responsive**: Touch-friendly targets on mobile
- **Recent activity**: Collapsible, readable

---

## 4. Implementation Order

1. **Phase A**: Remove watermark/background images (base, portal, admin, login, reports)
2. **Phase B**: Delete `logo_watermark.html` and any remaining references
3. **Phase C**: Update ThemePack seed command with school-focused palettes
4. **Phase D**: Extend palette schema for dark/system/high-contrast (if needed)
5. **Phase E**: Improve admin sidebar CSS
6. **Phase F**: Improve portal sidebar CSS

---

## 5. References

- Soft UI Dashboard, Material Dashboard 2 (Creative Tim)
- Tabler, AdminLTE, V-Dashboard (Tailwind)
- Kiaalap (Education Bootstrap 5)
- Django Unfold (Tailwind admin)
- WCAG 2.1 AAA contrast requirements
