# Pricing & packaging (commercial model)

This document maps **commercial tiers** to the **technical entitlements** already modeled in code (`siteconfig.Plan`, `School.plan`, `School.addons`, feature toggles). Dollar amounts and contracts are **commercial decisions** outside this file; engineering owns the **feature keys** and limits.

## Tiers (sales names ↔ technical anchor)

| Tier | Intended buyer | Technical anchor |
| --- | --- | --- |
| **Starter** | Single campus getting core academics + portal online | `Plan` slug (e.g. `starter`) with a minimal `included_features` list and optional `max_students` / `max_staff` caps. |
| **Growth** | Multi-program or growing enrollment; needs reports + automation | `Plan` slug (e.g. `growth`) with broader `included_features` (e.g. `reports`, `reports_scheduled_delivery`, module families). |
| **Enterprise** | Groups, compliance-heavy workflows, custom integrations | `Plan` slug (e.g. `enterprise`) with `max_*` null (unlimited) where appropriate, full feature matrix, plus `addons` for SKU-style add-ons. |

## Feature mapping (examples)

Feature codes are strings in `Plan.included_features` and `School.addons` (see `apps/schools/models.py` entitlement helpers). Typical mappings:

| Capability | Example codes (illustrative) |
| --- | --- |
| Core academics & people | `library`, coarse modules as configured per deployment |
| Reports & scheduled delivery | `reports`, `reports_scheduled_delivery` |
| Studio / experience | `design_studio` or packs as your `Plan` rows define |
| Marketplace / packs | Activated via plan + marketplace governance (super surfaces) |

**Rule:** Sales must not promise a code that is not present on the tenant's `Plan` / `addons` / toggle state.

## Limits (when set)

`Plan.max_students` and `Plan.max_staff` are optional positive integers; `null` means *no cap encoded in this field* (not the same as legal “unlimited” — clarify in MSA).

**Read-only visibility:** Tenant operators with `settings.manage` can open **`/siteconfig/billing/plan/`** to see assigned plan, included codes, add-ons, and live headcounts vs caps.

**Superuser break-glass:** Django admin does not expose a tenant `Plan` changelist (catalog lives on the control plane). On that page, superusers get an advanced link that opens the manager-host **plans list** (`super:plans_list`) when an admin changelist is unavailable.

## Upgrade triggers (commercial)

Use these as **conversation triggers**, not automatic in-app upsells:

1. **Headcount** — Active students or teacher profiles approach `max_students` / `max_staff`.
2. **Capability** — School requests modules whose codes are absent from `included_features` and not granted via `addons`.
3. **Operations** — Scheduled report volume, marketplace packs, or multi-campus governance requires Enterprise-style controls.

## What we do not do in-product (by design)

- No Stripe or card capture in this repository path.
- No fabricated usage dashboards for billing — only real ORM counts on the plan page.
