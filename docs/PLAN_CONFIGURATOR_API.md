# Plan Configurator API (Phase E)

**Version:** 1  
**Base URL:** `/super/api/plans-configurator/` (GET)  
**Auth:** Super Admin (TenantSuperAdminRequiredMiddleware).

## Purpose

Same contract for (1) onboarding billing step and (2) PlanConfigurator component. Real-time price engine: billing model + add-ons + estimated student count + country PPP multiplier.

## Request

- **Method:** GET  
- **Query:** `country_code` (optional) — ISO 3166-1 alpha-2/3 for PPP multiplier.

## Response (JSON)

```json
{
  "version": 1,
  "country_code": "CMR",
  "country_multiplier": 0.85,
  "plans": [
    {
      "id": 1,
      "name": "Pro",
      "slug": "pro",
      "billing_model": "PER_STUDENT",
      "base_price": null,
      "price_per_student": 5.00,
      "tier_rules": [],
      "max_students": null,
      "max_staff": null,
      "included_features": ["library", "transport"]
    }
  ],
  "addons": [
    { "code": "design_studio", "name": "Design Studio", "price": 20.00 }
  ]
}
```

## Price calculation (client)

- **FLAT:** `base_price * country_multiplier`
- **PER_STUDENT:** `student_count * price_per_student * country_multiplier`
- **TIERED:** lookup `tier_rules` by student count, then `price * country_multiplier`
- Add addon prices for selected add-ons, then multiply by `country_multiplier`.

## Changelog

- **v1:** Initial: plans, addons, country_multiplier.
