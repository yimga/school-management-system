# Portal Dashboards: Deployment and Privacy

This document covers deployment and privacy considerations for the Teacher and Parent portal dashboards.

## RBAC and Data Scope

- **Teacher dashboard**: Data is scoped to the teacher's assigned classes and students only (enforced in views and services).
- **Parent dashboard**: Data is scoped to guardian-linked students only; finance data only when finance access is granted per link.

RBAC and encryption are assumed in place; this doc adds deployment-specific notes.

## Two-Factor Authentication (2FA)

- For production, enable 2FA for staff and optionally for parents where supported by the application.
- Document 2FA setup in your deployment/security runbook and in SECURITY_QUICK_REFERENCE or SECURITY_IMPLEMENTATION_GUIDE.
- Parent and teacher dashboards do not implement 2FA themselves; rely on account-level 2FA and secure session handling.

## Parent Data Privacy

- Parent dashboard shows only data for students linked via `StudentGuardian`; never expose other students' data.
- Finance visibility is controlled by guardian link flags and (optionally) site-level finance opt-in.
- In deployment/security documentation, state how parent data is stored, who can access it, and retention. Prefer encrypting sensitive fields and using HTTPS and secure cookies (see SECURITY_QUICK_REFERENCE).

## Accessibility and Mobile

- Dashboards use `role="main"` and `aria-label` on main content; touch targets are at least 44px on small screens.
- For full WCAG 2.2 Level AA, run the project's accessibility checks and manual testing (see docs/ACCESSIBILITY.md).

## Multilingual (i18n)

- Dashboard strings should be passed through Django's translation framework (`{% trans %}` / `gettext`) where possible so language selector and locale settings apply consistently.
