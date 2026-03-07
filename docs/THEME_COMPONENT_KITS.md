# Theme Component Kits (Figma / CSS alignment)

This document defines component-level styles for the **Academic Authority** (admin) and **Active Learner** (student portal) theme kits so design and code stay aligned. Use these values in Figma and when building or theming components.

---

## 1. Academic Authority (Admin / Principal)

Best for: dense data, tables, financial tracking, principal dashboards.

| Component | Style | Figma/CSS values |
|-----------|--------|-------------------|
| Primary Button | Sharp 4px corners, solid navy | BG: `#0D173B`, Text: `#FFFFFF` |
| Secondary Button | Ghost (border only) | Border: `#0D173B`, Text: `#0D173B` |
| Input Fields | Subtle gray border, white fill | Border: `#D1D5DB`, BG: `#FFFFFF` |
| Data Tables | Zebra stripes | Row 1: `#FFFFFF`, Row 2: `#F9FAFB` |
| Side Navigation | Dark theme, high contrast | BG: `#0D173B`, Active text: `#4AB7E0` |
| Cards | Flat, 1px light border | Border: `#E5E7EB`, Shadow: none |

---

## 2. Active Learner (Student Portal)

Best for: course modules, quizzes, gamified dashboards.

| Component | Style | Figma/CSS values |
|-----------|--------|-------------------|
| Primary Button | Rounded (full), gradient | BG: `linear-gradient(#7C7CE4, #6A4C93)` |
| Action Button (e.g. Submit) | Pop color | BG: `#EC5800`, Shadow: `0 4px #BF4600` |
| Progress Bars | Thick, rounded, vibrant | Track: `#F3F4F6`, Fill: `#1982C4` |
| Course Cards | Heavy radius, soft shadow | Radius: 16px, Shadow: `0 10px 15px -3px rgba(0,0,0,0.1)` |
| Status Badges | Capsule, pastel | Success BG: `#DCFCE7`, Text: `#15803D` |
| Search Bar | Floating, blurred | `backdrop-filter: blur(8px)`, Opacity: 0.8 |

---

## 3. Shared Global States (Universal)

Regardless of theme, use these for consistent user clarity:

| State | Hex | Usage |
|-------|-----|--------|
| Success (Pass / Paid) | `#22C55E` | Attendance present, paid fees, completed |
| Warning (Pending / Late) | `#F59E0B` | Pending actions, late submissions |
| Error (Fail / Overdue) | `#EF4444` | Failing, overdue, validation errors |
| Disabled | `#9CA3AF` | Disabled buttons, muted controls |

**State variants:** For Hover, Pressed, and Disabled, use 10–20% lighter or darker than the primary color (e.g. in Figma: adjust luminance; in CSS: use `color-mix()` or precomputed hex).

---

## 4. Implementation tips

- **Tokens:** Prefer semantic names (`brand-primary`, `status-success`) over raw hex in code.
- **Contrast:** Aim for WCAG AA (4.5:1) or AAA for text; use a contrast checker (e.g. A11y plugin in Figma).
- **Off-black:** Avoid pure black `#000000` on pure white `#FFFFFF`; use off-black `#1A1C1E` on soft backgrounds (e.g. `#F0F3F5`, `#FDFCF0`) to reduce eye strain and support accessibility.

See also: [THEME_PACK_SCOPE.md](THEME_PACK_SCOPE.md), [THEME_ACCESSIBILITY.md](THEME_ACCESSIBILITY.md) (if present), and `static/css/design-tokens.css`.
