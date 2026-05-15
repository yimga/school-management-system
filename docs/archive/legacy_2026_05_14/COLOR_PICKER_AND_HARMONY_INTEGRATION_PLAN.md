# Color Picker & Color Harmony Integration Plan

## Overview

Integrate an enhanced color picker with **color harmony generation** into the themepack system, providing:
- Visual HEX picker (building on existing Pickr)
- Color combination previews (Complement, Split-complementary, Triadic, Analogous, Monochromatic, Tetradic)
- Centralized placement in admin
- One-click apply of harmonies to ThemePack / SiteSettings / ReportCardStyle

---

## 1. Current State

| Component | Location | Notes |
|-----------|----------|-------|
| **ColorInputWithPreview** | `apps/siteconfig/widgets.py` | Uses Pickr; swatch + hex input; no harmony |
| **Pickr** | CDN 1.8.2 | Already loaded for color fields |
| **Color fields** | SiteSettings, ThemePack, ReportCardStyle | `primary_color`, `accent_color`, `header_bg_color`, `footer_bg_color`, `background_color` |
| **Admin forms** | Site Settings, Theme Pack, Report Card Style | Each has color fields with ColorInputWithPreview |

---

## 2. Proposed Architecture

### 2.1 Centralized "Color Palette Studio"

**Location:** Single reusable component included wherever colors are edited:
- **Site Settings** change form (Theme & Experience)
- **Theme Pack** add/change form
- **Report Card Style** add/change form

**Implementation:** A collapsible panel / card that:
1. Opens above or beside the color fields
2. Provides one base color picker
3. Generates harmonies in real time
4. Shows swatches + HEX codes + "Best for" hints
5. Offers "Apply as primary" / "Apply as accent" / "Apply palette" to fill form fields

### 2.2 Component Layout (Concept)

```
┌─────────────────────────────────────────────────────────────────┐
│  Color Palette Studio                                    [Expand]│
├─────────────────────────────────────────────────────────────────┤
│  Base color: [🎨 swatch] #ffcea4    [Pick]  [Paste hex]          │
│                                                                  │
│  Presets: [Blue & Orange] [Shades of Blue] [Coral-Sky-Spring] …  │
│                                                                  │
│  Harmony: [Complement ▼]                                          │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │ [■#ffcea4] [■#a4d5ff]                                        ││
│  │ Best for: High-impact designs, CTAs, logos                    ││
│  │ [#ffcea4] [#a4d5ff] [Copy] [Apply primary] [Apply accent]     ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ── Or choose:                                                   │
│  [Complement] [Split-complementary] [Triadic] [Analogous]         │
│  [Monochromatic] [Tetradic]                                       │
│                                                                  │
│  Apply to: [Primary color ▾] [Accent color ▾] [Background ▾]      │
│  [Apply to portal / theme pack / report card]                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Color Harmony Engine

### 3.1 Algorithms (HSL-based)

All harmonies derived from HSL. Base color → (H, S, L). Then:

| Harmony | Formula | Output |
|---------|---------|--------|
| **Complement** | H + 180° | 2 colors |
| **Split-complementary** | H + 150°, H + 210° | 3 colors |
| **Triadic** | H + 120°, H + 240° | 3 colors |
| **Analogous** | H ± 30° | 3 colors |
| **Monochromatic** | Same H, L ± 25%, L ± 50% | 3 colors |
| **Tetradic** | H + 90°, H + 180°, H + 270° | 4 colors |

### 3.2 "Best for" Text (from your guide)

| Harmony | Best for |
|---------|----------|
| Complement | High-impact designs, CTAs, logos |
| Split-complementary | Vibrant yet balanced layouts |
| Triadic | Playful, energetic designs |
| Analogous | Nature-inspired, calming interfaces |
| Monochromatic | Minimalist, sophisticated designs |
| Tetradic | Rich, diverse color schemes |

### 3.3 Top Glass & Classic Harmony Presets (one-click palettes)

Curated presets admins can apply without picking a base color:

| Preset | Type | Colors (HEX) | Best for |
|--------|------|--------------|----------|
| **Complementary – Blue & Orange** | High contrast | `#2563eb`, `#f97316` | CTAs, buttons, dashboards |
| **Complementary – Red & Green** | High contrast | `#dc2626`, `#16a34a` | Alerts, success/error |
| **Complementary – Purple & Yellow** | High contrast | `#7c3aed`, `#eab308` | Premium, academic |
| **Analogous – Blue-Green & Red-Purple** | Serene | `#0d9488`, `#a855f7`, `#ec4899` | Calm interfaces |
| **Analogous – Yellow, Amber & Red** | Serene | `#eab308`, `#f59e0b`, `#ef4444` | Warm, welcoming |
| **Triadic – Coral, Sky Blue, Spring Green** | Vibrant | `#f97316`, `#0ea5e9`, `#22c55e` | Energetic, playful |
| **Monochromatic – Shades of Blue** | Sophisticated | `#0ea5e9`, `#1e3a5f`, `#0369a1` | Minimalist, professional |
| **Monochromatic – Shades of Green** | Sophisticated | `#22c55e`, `#14532d`, `#15803d` | Nature, growth |
| **Classic – Black-White-Red** | Classic | `#000000`, `#ffffff`, `#dc2626` | Corporate, high contrast |
| **Classic – Light Brown & Blue** | Classic | `#a16207`, `#2563eb`, `#fef3c7` | Trust, warmth |

**Implementation:** "Preset" dropdown or quick-select buttons in the studio. Selecting a preset populates the harmony swatches; admin can tweak and apply.

### 3.4 Library Choice

| Library | Purpose |
|---------|---------|
| **Colord** or **TinyColor2** | HEX ↔ HSL conversion, palette generation |
| **Pickr** (existing) | Picker UI |

Colord is lightweight (~2KB) and handles conversions and manipulations well. No extra UI; we implement harmony logic in JS.

---

## 4. Integration with ThemePacks & Teacher/Parent Profiles

### 4.1 Theme flow: who sees what

| Surface | Source | Who sees it |
|---------|--------|-------------|
| **Portal** (teacher, parent, student dashboards) | `SiteSettings.theme_pack` → `ThemePack` (primary_color, accent_color, background_color) | Teachers, parents, students |
| **Admin** | `SiteSettings.admin_theme_pack` → `ThemePack` | Staff, superusers |
| **Backend** | Same as Admin (`admin_theme_pack`) | Staff |
| **Reports** | `ReportCardStyle` (primary_color, accent_color) | Anyone viewing reports |

**Important:** Today there is **one theme_pack for the entire portal** – teachers and parents share the same colors. Changing `theme_pack` (or its colors) updates **all portal users** (teachers, parents, students).

### 4.2 How to change colors for teachers and parents

1. Go to **Admin → Site config → Site settings** or **Admin → Site config → Theme packs**.
2. Edit the **Theme pack** used by the portal (`theme_pack` in Site Settings).
3. Change `primary_color`, `accent_color`, `background_color` in that Theme Pack.
4. Save. All portal dashboards (teacher, parent, student) update.

**Or:** Change colors directly on **Site Settings** – they override the Theme Pack for `primary_color` and `accent_color` when `apply_theme_pack` syncs them.

### 4.3 Future: role-specific themes (teacher vs parent)

If you want **different colors for teachers vs parents**:

| Option | Description |
|--------|-------------|
| **A. Teacher theme pack / Parent theme pack** | Add `teacher_theme_pack` and `parent_theme_pack` to SiteSettings; portal templates choose based on `request.user.role`. |
| **B. Role override in ThemePack** | Add `palette` JSON with `teacher_primary`, `parent_primary`, etc.; templates read role-specific values. |
| **C. Per-user theme preference** | UserPreference already has `theme_preference` (light/dark). Could extend to let users pick a Theme Pack (limited set). |

**Recommendation:** Phase 1 uses one theme for all. Add role-specific theming in a later phase if needed.

---

## 4.4 Mapping harmonies to model fields

| Harmony | Primary | Accent | Background / extras |
|---------|---------|--------|----------------------|
| Complement | Color 1 | Color 2 | — |
| Split-complementary | Color 1 | Color 2 or 3 | Optional 3rd for gradient |
| Triadic | Color 1 | Color 2 | Color 3 for accents |
| Analogous | Color 1 (center) | Color 2 or 3 | Gradient |
| Monochromatic | Base | Light variant | Dark variant for borders |
| Tetradic | Color 1 | Color 2 | Colors 3, 4 for accents |

### 4.5 Apply actions

1. **Apply as primary** → Set `primary_color` to selected swatch
2. **Apply as accent** → Set `accent_color` to selected swatch
3. **Apply palette** → Fill primary + accent (and optionally background) from the current harmony
4. **Copy HEX** → Copy to clipboard (existing pattern)
5. **Apply to portal** → When on Site Settings or Theme Pack, "Apply" updates the theme used by teacher/parent dashboards.

### 4.6 Centralized placement – single entry, context-aware

- **One Color Palette Studio** partial, included in:
  - Site Settings change form (Theme & Experience)
  - Theme Pack add/change form
  - Report Card Style add/change form
- **Context-aware:** Studio detects which form it’s in and applies to the correct fields (`primary_color`, `accent_color`, `background_color`).
- **Admin entry point:** One place – **Admin → Site config** – where admins manage themes. From there they go to Site Settings or Theme Packs; both show the same Color Palette Studio.

---

## 5. Technical Implementation

### 5.1 New files

| File | Purpose |
|------|---------|
| `static/js/color-harmony-engine.js` | HEX↔HSL, harmony algorithms |
| `static/js/color-palette-studio.js` | UI logic, apply-to-form |
| `static/css/color-palette-studio.css` | Studio layout and swatches |
| `templates/admin/components/color_palette_studio.html` | HTML for the studio |

### 5.2 Dependencies

```html
<!-- Add to forms that use the studio -->
<script src="https://cdn.jsdelivr.net/npm/colord@2.9.3/colord.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/colord@2.9.3/plugins/names.min.js"></script>  <!-- optional: color names -->
```

Or bundle Colord via npm if the project uses a build step.

### 5.3 API (JS)

```javascript
// color-harmony-engine.js
colorHarmony.hexToHsl("#ffcea4")     // → { h, s, l }
colorHarmony.hslToHex(h, s, l)       // → "#ffcea4"
colorHarmony.complement(hex)         // → ["#ffcea4", "#a4d5ff"]
colorHarmony.splitComplementary(hex) // → ["#ffcea4", "#c3ffa4", "#aaa4ff"]
colorHarmony.triadic(hex)            // → ["#ffcea4", "#a4ffce", "#cea4ff"]
colorHarmony.analogous(hex)          // → ["#ffcea4", "#ffc5a4", "#ffd7a4"]
colorHarmony.monochromatic(hex)      // → ["#ffcea4", "#554537", "#aa896d"]
colorHarmony.tetradic(hex)           // → ["#ffcea4", "#a7ffa4", "#a4d5ff", "#fba4ff"]
```

### 5.4 Form integration

- Studio reads `primary_color`, `accent_color`, `background_color` from the page (or passed via `data-*`).
- "Apply" buttons use `document.querySelector('[name="primary_color"]')` (or equivalent) and set `.value`, then dispatch `change`.
- Existing `ColorInputWithPreview` + Pickr will reflect the new values if they listen for `change`.

---

## 6. Optional Enhancements

### 6.1 Image color extractor

| Component | Library | Purpose |
|-----------|---------|---------|
| Color Thief | `colorthief` (or similar) | Extract dominant palette from uploaded image |

**Flow:** Upload/paste image → Extract 3–5 colors → Show as swatches → Apply to form.

**Priority:** Phase 2.

### 6.2 RGB / HSL display

- Show HEX, RGB, HSL (and optionally OKLCH) under each swatch.
- Copy button per format.

### 6.3 Lock & generate

- Lock base color(s) and regenerate harmonies when sliders change (similar to Coolors).
- Can be a later phase.

---

## 7. Implementation Phases

### Phase 1: Harmony engine + studio UI (core)

1. Add `color-harmony-engine.js` with all six harmonies.
2. Add Top Glass & Classic presets (Blue & Orange, Shades of Blue, etc.).
3. Create `color_palette_studio.html` and `color-palette-studio.js` + `.css`.
4. Include the studio in Site Settings change form (Theme & Experience section).
5. Wire "Apply primary" / "Apply accent" / "Apply palette" to form fields.
6. Add Colord (or TinyColor) for conversions.

### Phase 2: ThemePack & ReportCardStyle

1. Include the studio in Theme Pack add/change form.
2. Include the studio in Report Card Style add/change form.
3. Ensure field names match (`primary_color`, `accent_color`, etc.).
4. Context-aware labels ("Apply to portal / theme pack / report card").

### Phase 3: Polish

1. Copy HEX/RGB/HSL to clipboard.
2. Improve responsive layout.
3. Optional: image color extraction.

---

## 8. Centralized Admin UX – Making It Easy

### 8.1 Single entry point

**Admin → Site config** as the main hub:

| Link | What it does |
|------|--------------|
| **Site settings** | Global theme, primary/accent, header/footer, theme_pack for portal |
| **Theme packs** | Create/edit themes used by portal (teacher, parent) and admin |
| **Report card styles** | Report-specific colors |

The **Color Palette Studio** appears in all three forms. No separate "Color Studio" page – admins stay in the context where they’re editing.

### 8.2 Studio UX flow (admin-friendly)

1. Admin opens **Site Settings** or **Theme Pack** or **Report Card Style**.
2. At top of Theme / Colors section: **"Color Palette Studio"** (collapsed by default).
3. Click **Expand** → see base picker + harmony selector + preset quick-select.
4. Pick a base color OR choose a preset (e.g. "Blue & Orange", "Shades of Blue").
5. Harmony swatches update. "Best for" text explains each option.
6. Click **Apply primary** / **Apply accent** / **Apply palette** → form fields update.
7. Save form → changes apply to portal (teacher, parent) or reports.

### 8.3 Context-aware labels

| Form | Apply button label |
|------|--------------------|
| Site Settings | "Apply to site colors (portal, teacher, parent)" |
| Theme Pack | "Apply to this theme pack" |
| Report Card Style | "Apply to report card" |

Makes it clear where the chosen colors will be used.

### 8.4 Color Theory Principles (for UI copy)

Display in the studio as guidance:

| Principle | Copy |
|-----------|------|
| Balance | Use one dominant color, support with secondary, accent sparingly. |
| Contrast | Ensure sufficient contrast for readability and accessibility. |
| Harmony | Colors should work together for a unified visual experience. |

---

## 9. File Changes Summary

| Action | File |
|--------|------|
| Create | `static/js/color-harmony-engine.js` |
| Create | `static/js/color-palette-studio.js` |
| Create | `static/css/color-palette-studio.css` |
| Create | `templates/admin/components/color_palette_studio.html` |
| Modify | `templates/admin/siteconfig/sitesettings/change_form.html` — include studio |
| Modify | Theme Pack change form — include studio |
| Modify | Report Card Style change form — include studio |
| Optional | Extend `ColorInputWithPreview` to optionally open the studio instead of only Pickr |

---

## 10. Acceptance Criteria

- [ ] User can pick a base color via Pickr or type HEX.
- [ ] User can switch harmony type and see 2–4 swatches update.
- [ ] User can select a preset (Blue & Orange, Shades of Blue, etc.) for one-click palette.
- [ ] Each swatch shows HEX; "Best for" text is shown.
- [ ] "Apply primary" / "Apply accent" / "Apply palette" update form fields.
- [ ] Studio is visible in Site Settings, Theme Pack, and Report Card Style forms.
- [ ] Context-aware labels clarify where colors apply (portal, theme pack, report card).
- [ ] Changing Theme Pack colors updates teacher and parent dashboards immediately (after save).
- [ ] No duplication of Pickr; reuses existing integration.
- [ ] Works with existing `ColorInputWithPreview` (values propagate correctly).
