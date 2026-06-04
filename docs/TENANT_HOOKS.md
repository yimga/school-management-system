# Tenant Hooks (Request-to-Feature / FeatureFragment)

Canonical hook registry and template placement for **Request-to-Feature** (plan 3.20, Powerhouse). Schools on Pro/Enterprise can have custom UI fragments injected at fixed "socket" locations.

## Hook registry

**Module:** `apps.siteconfig.hooks`

- **HOOK_REGISTRY** — list of allowed hook names (UPPERCASE).
- **HOOK_CHOICES** — `(value, label)` for admin dropdown and docs.

Use the same names in templates and when creating FeatureFragments in admin.

| Hook name | Where it appears |
|-----------|------------------|
| `STUDENT_PROFILE_SIDEBAR` | Student 360 component (custom block below tabs) |
| `STUDENT_LIST_FOOTER` | Backend student list card footer |
| `GRADEBOOK_CONTROLS` | Teacher marks list, above filters |
| `GRADEBOOK_CARD_FOOTER` | Teacher marks list card footer |
| `FINANCE_DASHBOARD_EXTRA` | Finance dashboard, below action buttons |
| `FINANCE_SUMMARY_FOOTER` | Finance dashboard, bottom of page |
| `BILLING_EXTRA` | Reserved for invoice/billing views |
| `CARD_FOOTER` | Generic card footer (use in any card) |

## Template usage

```django
{% load tenant_hook %}
...
{% tenant_hook 'STUDENT_LIST_FOOTER' %}
```

The tag returns the fragment's `metadata_schema["html"]` for the current school and hook, or empty string. No fragment is rendered if the school has no active FeatureFragment for that hook.

## Plan gating

- **CustomFeatureTicket:** Schools can submit requests on any plan (Request custom requirement page).
- **FeatureFragment:** Plan cap applies when creating fragments: Basic 0, Pro 2, Enterprise 5 (`get_feature_fragment_cap(school)`).

## Request flow

1. School admin goes to **Request custom requirement** (Site Settings / Customizer area; `settings.manage`).
2. Submits title + description → creates **CustomFeatureTicket** (status Submitted).
3. Super Admin (or AI) reviews in Django admin, then creates a **FeatureFragment** linked to the ticket (target_hook, metadata_schema with `html` or `partial`).
4. Fragment is rendered wherever that hook is placed in templates.

## Security

- Fragment HTML is rendered with `mark_safe`. For untrusted content, consider stripping `<script>`, `on*` attributes, or serving via CSP/sandbox.
- Hook names are normalized to uppercase in the tag.

## JSON-Logic nuance (separate registry)

Template **tenant hooks** (this doc) are unrelated to the **JSON-Logic nuance engine** used for tuition, fee discounts, report-card averages, and scholarship eligibility.

| Concern | Module |
|--------|--------|
| UI fragment sockets (`STUDENT_LIST_FOOTER`, …) | `apps/siteconfig/hooks.py` |
| JSON-Logic hook points (`tuition_calc`, `report_card_avg`, …) | `apps/siteconfig/nuance_engine.py` (`HOOK_REGISTRY`, `apply_nuance`, `evaluate_json_logic`) |
| Grading preset templates → policy → `CustomNuance` | `apps/policies/grading_nuance_templates.py` |
| Contract verifier | `python scripts/verify_nuance_logic_toolset_contract.py` |

`scholarship_eligibility` is a **virtual** hook: rules live on `Scholarship.eligibility_criteria` and run via `evaluate_json_logic`, not `CustomNuance` rows.

## Related

- **Models:** `CustomFeatureTicket`, `FeatureFragment` in `apps.siteconfig.models`
- **Tag:** `apps.siteconfig.templatetags.tenant_hook`
- **View:** `request_custom_requirement` in `apps.siteconfig.views_custom_requirement`
- **Powerhouse blueprint vs codebase:** See plan summary (e.g. `.cursor/plans/` or ROADMAP_TOKEN_SUMMARY).
