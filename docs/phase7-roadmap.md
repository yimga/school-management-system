# Phase 7 — QA, URLs & UX Roadmap

Branch: `phase7-Roadmap` (keep all work here until you’re ready to PR).

## Objectives
1. Guarantee a “single source of truth” by tying LMS/SIS data, dashboards, communications, and automations together.
2. Elevate QA/security to 2026 standards before rolling out the portal-wide UX overhaul.
3. Clean URLs, polish navigation/SEO, and deliver responsive, accessible dashboards with meaningful widgets.

## Implementation Plan

### A. QA & Automation (Early, Continuous, Secure)
- Add regression tests for core workflows (teacher publish → parent report, fee reminder process) using Django’s test client or Playwright.
- Hook `python manage.py run_attendance_cycle`/`run_payroll_cycle` (existing commands) into scheduled QA scripts; verify outputs in `docs/automation.md`.
- Introduce MFA checks (via `django-otp`/`django-allauth` or mocked multi-factor toggle) and pen-test checklist items in `docs/qa.md`.
- Create API integration health checks for SMS/WhatsApp (e.g., `Integration` ping command).
- Document accessibility checks (WCAG 2.2/3.0) and add `axe-core`/`pa11y` lint targets for portal pages.

### B. URL/SEO Cleanup
- Audit and remove unused routes from `apps/**/urls.py`; rename key paths to semantic forms (`/admissions/application-status`, `/student-portal/grades`, `/finance/payments/receipts`).
- ✅ Add breadcrumbs via a context processor and render them in `templates/partials/breadcrumbs.html`.
- Ensure HTTPS enforcement in `config/settings.py`/`render.yaml` and add canonical/local SEO tags to admissions/public pages (keywords like “sixth form admissions [city]”).
- Create a mapping doc (`docs/urls.md`) outlining the cleaned structure and redirect rules for legacy paths.

### C. UX/Dashboard Overhaul
- Build a component library (`templates/widgets/`) for:
  * Attendance Snapshot (daily + overall charts).
  * Performance Overview (trends, class averages).
  * Financial Summary (fee status, pending payments).
  * Upcoming Events/Alerts (scroller + badge).
  * Task/Assignment Tracker.
  * Portal Access quick links.
  * Class Timetable/Schedule.
  * Communication Center (messages, announcements, WhatsApp/Zoom link).
  * Data Visualization quick filters.
  * Resource/File Manager.
- ✅ Added task tracker, portal quick links, timetable, and communication widgets for parents (see `templates/widgets/parent_dashboard_widgets.html` and `apps/portal/services.py`).
- ✅ Implemented attendance, performance, financial, and event widgets on the parent dashboard plus a reusable partial (`templates/widgets/parent_dashboard_widgets.html`).
- Add modular layout support (drag-and-drop, stored order per user via `UserPreference.dashboard_layout`) + adaptive rendering per role.
- Enforce mobile-first styles (≥44x44 tap targets), micro-animations, high contrast theming, dark/light modes, and RTL support via CSS variables and `ThemePack` entries.
- Include breadcrumbs navigation (`templates/partials/breadcrumbs.html`) and consistent component styling (icons, charts, colors).
- Add UI for chatbots/conversational layer stub that can hook into future AI features; link to WhatsApp integration.

### D. Integrations & Communication
- Manage WhatsApp API credentials via `Integration` model and surface them in a new Communication widget (customer service contact, quick call/chat actions).
- Expand `Integration` admin to include video conferencing (Zoom/Meet) links and embed them in dashboards/alerts.
- Document automation for reminders (attendance, fees, certificates) plus SoT for AI analytics (predictive alerts) in `docs/automation.md`.

### E. Documentation & QA Inventory
- Create `docs/qa.md` describing testing scripts, security reviews, penetration plan, and accessibility goals.
- Update `docs/ux.md` with dashboard widget descriptions, accessibility standards, responsive specs, and micro-interactions.
- Keep `docs/phase7-roadmap.md` updated with tasks and status notes as work progresses.

## Deliverables
- `docs/qa.md`, `docs/urls.md`, `docs/ux.md`, and `docs/automation.md`.
- Reusable widget partials plus JS for layout/drag.
- Breadcrumb templates + SEO metadata helpers.
- QA scripts/commands accessible via `[scripts/phase7-testing.sh]` (if needed).
- WhatsApp integration details + chat widget placeholder.

## Next Actions
1. Identify highest-impact widget or QA task to tackle first and scope it (tests → feature).
2. Add incremental commits on `phase7-Roadmap` with descriptive messages (e.g., “Add attendance widget partial”).
3. Keep `phase7-Roadmap` synced with upstream, rerun `python manage.py test`/`collectstatic` as needed, then push/PR when you’ve validated all items.
