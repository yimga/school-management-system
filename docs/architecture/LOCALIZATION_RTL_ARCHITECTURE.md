# Localization / RTL / low-bandwidth execution

Runtime terminology, translation strategy, RTL layout, locale formatting, mobile-first and low-bandwidth behavior (Execution Master §3.6, §3.7, §7.5).

## Requirements

- **Runtime terminology everywhere:** Labels (e.g. "Student", "Learner") from runtime.policy or runtime.locale.terminology_pack; no hardcoded strings for tenant-facing UI where term varies.
- **Translation strategy:** Django i18n (makemessages/compilemessages); translation files per locale; lazy translation in templates and code.
- **RTL layout strategy:** CSS logical properties and `dir="rtl"` where locale demands; template `is_rtl` or runtime.locale.direction; no RTL-specific template forks.
- **Locale formatting consistency:** Date, number, currency format from runtime.registry and runtime.locale; single formatter layer; templates use filters/tags that respect request.tenant_runtime.
- **Mobile-first shells where needed:** Portal and key tenant workflows responsive; compact shell rules for mobile; see PERFORMANCE_BUDGETS for layout budgets.
- **Low-bandwidth widget/layout variants:** Optional simplified views or lazy-load for heavy widgets; degraded-safe behavior for critical flows (e.g. attendance, fee payment).
- **Degraded-safe behavior:** Critical workflows work with minimal JS and fallback UI; no required features that depend only on full bandwidth.

## Implementation direction

- Terminology: use `request.tenant_runtime.locale.terminology_pack` or policy.terminology; expose via `apps.platform_runtime.helpers.get_effective_locale(request)` or portal policy; expose in context for templates.
- Formatting: central format_date, format_currency, format_number that read locale/registry from runtime; use in all templates.
- RTL: set `dir` and body class from runtime.locale.direction; use logical CSS (margin-inline, padding-inline, text-align: start/end).
- Mobile/low-bandwidth: document which modules are mobile-first; add responsive and reduced-data patterns in page families; avoid duplicate code paths (one responsive layout, not separate mobile templates per feature).

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 2)
- apps/platform_runtime/contracts.py (LocaleContext)
- apps/platform_runtime/helpers.py (get_effective_locale)
- apps/portal/runtime_helpers.py (get_portal_policy for terminology in policy)
