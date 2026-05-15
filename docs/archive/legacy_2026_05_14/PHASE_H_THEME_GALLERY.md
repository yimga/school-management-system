# Phase H: Theme choice and ThemeGallery

## Implemented

- **School.theme_choice** (UNFOLD, JAZZMIN, SNEAT) added to the School model; migration `schools.0007_school_theme_choice`.
- **Change theme in School settings:** Admin → Schools → edit school → **Theme & branding** → **Admin theme** dropdown. Staff can change the admin theme at any time.
- **Create School wizard:** Step 3 (Branding) includes an **Admin theme** dropdown (Unfold recommended, Jazzmin, Sneat). Value is sent as `theme_choice` and saved on the new school.
- **Unfold dashboard callback** injects school logo and primary/accent colors when `request.school` is set (`apps.siteconfig.unfold_dashboard.dashboard_callback`).

## Optional ThemeGallery polish (onboarding)

To match the roadmap’s “Premium Configurator” and Phase H theme polish:

1. **Theme cards in wizard (Step 3)**  
   Replace the single dropdown with three cards:
   - **Unfold (Modern)** — [RECOMMENDED] badge, short description.  
   - **Jazzmin (Classic)**  
   - **Sneat (Enterprise)**  
   Use `data-theme` (e.g. `UNFOLD`) and JS to set a hidden `theme_choice` input.

2. **Live preview**  
   In the same step, add a “Live preview” area (e.g. right column or below cards):
   - Small iframe or a mini-dashboard component that reflects the selected theme (sidebar style, colors).
   - Update preview when the user selects a different card (no full page reload).

3. **[RECOMMENDED] badge**  
   On the Unfold card: badge + optional subtle pulse/gradient so it’s clearly the default.

4. **Framer Motion (if using React)**  
   If the wizard is ever ported to React: use Framer Motion for card selection (e.g. scale/opacity) and for the preview transition when switching theme.

5. **DynamicThemeMiddleware (backend)**  
   If you need per-tenant admin templates (e.g. `templates/themes/unfold/`, `themes/jazzmin/`), add middleware that sets `request.theme_path` (or equivalent) from `request.school.theme_choice` so the admin base template can extend the correct theme. Unfold may already be the only admin theme; in that case `theme_choice` is still useful for analytics or future multi-theme support.

## Migration order (reference)

- **siteconfig:** 0096 → 0097_sync_conflict_phase_g → 0098_phase_f_design_template_brand_settings → 0099. Single chain; no merge needed.
- **schools:** 0006_school_billing_type_waiver_note → 0007_school_theme_choice. Run after siteconfig 0094 if 0005 depends on it.
