# Phase 7 UX & Dashboard Guide

## Vision
Deliver a modern, unified experience across admin, teacher, and parent dashboards by:

- Replacing the old layouts with reusable widget partials (`templates/widgets/*.html`) so every role sees a curated set of KPIs.
- Emphasizing functional minimalism, high contrast, and adaptive layouts (mobile-first, dark/light, RTL-safe) so complex data stays legible.
- Layering micro-interactions (tap states, subtle hover transitions) and consistent icon/chart styling to signal actions without pop-ups.

## Dashboard Components
- **Attendance Snapshot** – real-time metrics plus a sparkline for daily/overall attendance; drives quick-alert badges for absences.
- **Performance Overview** – class averages, grade trends, and class retention rate cards with optional exports.
- **Financial Summary** – hero banner with total fees collected, pending invoices, and late fees plus a detailed widget showing payment methods (card, bank, offline).
- **Task Tracker** – teacher/admin cards that surface pending tasks/assignments with progress pills and quick "mark as done" actions.
- **Portal Access Quick Links** – button grid providing one-click access to schedules, grades, messages, and resource uploads.
- **Timetable/Schedule** – weekly view with expandable slots, highlighting current/next classes for teachers and parents.
- **Communication Center** – cards for announcements, WhatsApp/SMS chat actions, and embedded Zoom/Meet links fed from the `Integration` records.
- **Data Visualizations** – mix of trends/charts (line, bar, doughnut) using shared CSS so each dashboard matches the woven color story.
- **Resource/File Manager** – quick access list for syllabus, forms, and policy docs, highlighting downloads.

## UX Strategy
- **Modular Layouts** – allow each user to reorder widget cards; persist layout in `UserPreference.dashboard_layout`.
- **Accessibility & Compliance** – maintain WCAG 2.2/3.0 contrast ratios, 44x44 tap targets, and keyboard navigation; track scores via `docs/qa.md`.
- **Breadcrumbs & Navigation** – baked into `templates/partials/breadcrumbs.html` to reinforce semantic URLs (e.g., `/student-portal/grades`, `/finance/payments/receipts`).
- **Multi-theme Support** – new `ThemePack` entries for primary (finance), accent, and highlight palettes; `SiteSettings` toggles dark/light.
- **Conversational Layer** – placeholder chat widget that surfaces WhatsApp quick actions (call/chat) and customer service numbers, ready for future AI.

## Verification & Future Improvements
- Validate each widget via `python manage.py check`/`test`, run `run_phase7_checks`, and refresh static assets before merges.
- Continue refining analytics cards (enrollment by cohort, performance heatmaps) and ensure every report (students, teachers, subjects, payments) is exportable as described in `docs/phase6-checklist.md`.
- Revisit breadcrumbs/SEO docs (`docs/urls.md`) whenever routes change to keep `phase7-Roadmap` accurate.
- Theme control lives in Site Settings: whatever theme is installed/applied should expose its palette, appearance, and feature toggles under `siteconfig` so admins can adjust colors/branding at any time.
