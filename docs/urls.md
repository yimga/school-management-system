# Phase 7 URL Cleanup

## Semantic endpoints
- `/portal/admissions/application-status/` → alias to parent dashboard (application status/grades overview).
- `/portal/student-portal/grades/` → alias to parent dashboard results.
- `/finance/payments/receipts/` → alias to finance payments list (receipt view).
- `/portal/features/<feature>/` → feature pages already live.

## Breadcrumb & SEO helpers
- Breadcrumbs include `BREADCRUMB_LABELS` for these key slugs.
- Use the `SITE` context (via `apps.siteconfig.context_processors.site_settings`) to fill canonical tags in templates such as `templates/base.html` and `templates/portal/feature_page.html`.
- Add meta keywords in public admissions/info templates focusing on “sixth form admissions [city]”, “school fees portal [city]”, and similar terms.

## Redirect map (legacy paths)
| Old path | Redirect |
| --- | --- |
| `/parent/results/` | `/student-portal/grades/` |
| `/finance/reports/old/` | `/finance/reports/` |

Drop unused URLs during the cleanup and document the new structure here so admins understand the change.
