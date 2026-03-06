# Section 25.7 — Accessibility and low-bandwidth / offline-first

## WCAG 2.2 AA

- **Target:** All tenant and public UI meets WCAG 2.2 AA (perceivable, operable, understandable, robust). Document in this file; run automated a11y checks (e.g. axe-core, pa11y) in CI or manually before release.
- **RTL:** Policy and brand registry support `is_rtl`; use in templates for layout and text direction.
- **Terminology from Blueprint:** Labels and terminology come from policy/Blueprint (TerminologyResolver, `global_env.terminology`); no hardcoded strings for tenant-facing copy.
- **Date/time and calendars:** Use locale and policy default_language; format dates per tenant preference.

## Low-bandwidth and offline-first

- **Policy keys:** `get_effective_policy(school)` can include `offline_mode` or `low_bandwidth` (add to platform defaults and school.settings merge if not present). Consumers (e.g. mobile app, PWA) can skip non-essential assets or enable offline caching when enabled.
- **Offline-first (teachers):** Document that attendance, grade entry, and notes can be supported offline with sync (SyncConflict, offline policy). Policy key `offline_mode` or feature flag per tenant.
- **Service worker:** Public/tenant shells can register a service worker for offline fallback (e.g. `offline.html`); see config/urls and public_urls.

## Implementation

- Add to resolver platform defaults: `out.setdefault("a11y", {"low_bandwidth": False, "offline_mode": False})` and merge from school.settings so tenants can enable low-bandwidth or offline-friendly behavior.
- Runbooks: reference this doc for a11y and offline verification steps.
