# Phase H Plan Checklist (optional / polish)

## Done

- **Unfold dashboard:** `apps.siteconfig.unfold_dashboard`; dashboard_callback and theme integration in settings.
- **School theme_choice:** UNFOLD / JAZZMIN / SNEAT set at creation and in admin; DynamicThemeMiddleware sets `request.theme_path` from `school.theme_choice`.
- **Admin school templates:** `templates/admin/schools/` for custom admin forms/views where added.

## Optional / deferred

- **Theme Gallery:** Live preview of UNFOLD/JAZZMIN/SNEAT in onboarding or school settings (e.g. iframe or redirect per theme). Deferred.
- **Change theme in school settings:** Portal or backend "Theme & branding" page where admin can change `school.theme_choice`; can be done today via Django admin → School → Plan & billing / theme.
- **Bento / Cmd+K / empty states:** Per-plan UX (Bento layout, command palette, empty-state copy); document in `.cursorrules` or design system; implement when building those screens.
