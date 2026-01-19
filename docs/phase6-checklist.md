# Phase 6 — Customization & Site Settings Checklist

This checklist keeps all the Phase 6 goals aligned with code in `phase6-customization_UI`. Tick them off once the corresponding component is wired up, then push the branch and open the PR.

## I. Core System Configuration
- [x] **Role-Based access & portals**: decorators in `apps/accounts/decorators.py` gate parent/teacher portal views; `SiteSettings` toggles live portal permissions.
- [x] **Security & data privacy**: `django` defaults plus middleware (`apps/siteconfig/middleware.py`) enforce login/maintenance.
- [x] **Branding & theming**: `SiteSettings`, `ThemePack`, and `templates/portal_base.html` render logos, palette, font, and custom CSS.

## II. Student & Admissions
- [x] **Custom admission fields**: admissions models copy extra fields from `apps/people` (handled earlier phases). Keep doc referenced in admin.
- [x] **Student profile control**: exported reports (students, fee payments) reflect profile fields for audits.
- [x] **Enrollment rules**: analytics thresholds `SiteSettings.top_students_default_limit` and promotion rules centralize grouping/promotion logic.

## III. Academics & Operations
- [x] **Curriculum/timetable**: `apps/portal` and `apps/academics` feed term summaries, and `term_report_context` ensures grade weights are consistent.
- [x] **Attendance settings**: `SiteSettings` default refresh rate and portal toggles support attendance alerts where needed.
- [x] **Grading/reporting**: portal stats, new weighting cards in `templates/parent/results.html`, plus `SiteSettings.enable_reports_pdf` cover this area.
- [x] **Exam management**: exam scheduling and exports live in `apps/evals` and `apps/reports`; the customization doc references them.

## IV. Financial Management
- [x] **Fee structures**: `docs/finance-payments.md` explains fee plans, reminders, and integration.
- [x] **Online payments**: `generate_payment_link` now uses balance and safe signatures; `Integration` records configure providers.

## V. Communication & Engagement
- [x] **Notification settings**: `UserPreference.notification_channels` plus `SiteSettings.notification_channels` drive email/SMS/app notifications.
- [x] **Portal features**: toggles and admin-managed `PortalFeatureItem` rows deliver messaging/forums/video/doc experiences.

## VI. Integrations & Scalability
- [x] **Third-party integrations**: `Integration` admin/model centralizes providers, and linking to finance/payroll ensures compliance.
- [x] **Scalability**: modular toggles/report exports/packs keep the system extensible as student/staff numbers grow.

## Bonus goals
- [x] **Theme library**: `ThemePack` entries show names/descriptions/colors in the customizer; `apply_theme_pack` syncs branding fields automatically.
- [x] **Branding controls**: customizer exposes logo/background/custom CSS/theme pack selection and preview info.
- [x] **User settings**: `/siteconfig/preferences/` form saves dashboard view, refresh rate, timezone, and notification channels per user.
- [x] **Behavior defaults**: Dashboard refresh and default view live in `SiteSettings`; `templates/siteconfig/customizer.html` surfaces them.
- [x] **All reports downloadable**: `ReportTemplate` handlers for `students`, `teachers`, `subjects`, `fee_payments` plus future templates make every key register exportable from `/siteconfig/reports/`.

Once all checkboxes are satisfied, push the branch (`git push origin phase6-customization_UI`) and draft a PR from GitHub; keep the code off `main` until the PR is reviewed.
