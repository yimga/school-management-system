# Enterprise contracts and pricing (commercial hygiene)

**Not legal advice.** Use your counsel for DPA, liability caps, and local education law. This doc is **operational** alignment with in-product **plans/entitlements**.

## Tiers and truth source

- **List prices** and packaging live in `PRICING_PACKAGES.md`.  
- **Enforcement** in deployment is `Plan` / `included_features` and related data—not what is on a PDF alone.

## Per-school vs per-campus

- **Default:** per **school** (tenant) for simplicity.  
- **Multi-campus:** Add a **per-campus line item** or **higher tier** that maps to the same *data* (one tenant vs many) per how you set up the customer—**do not** claim cross-tenant “district” features the build does not expose.

## Discounting

- **Volume:** 2+ schools same trust, annual prepay.  
- **Pilot:** Time-boxed; **read-only** or **capped** users if entitlements are technically enforceable.  
- **Rule:** If you give a **permanent** discount, update what **finance** tracks so ARR is not a lie to yourself.

## Negotiation (practical)

- **Anchor** on annual **total** and scope (modules, campuses, support).  
- **Procurement:** offer a **pilot SOW** with a fixed exit checklist, then **order form** for production.  
- **Multi-year:** year-1 price fixed; year-2+ escalator in CPI band or %—your finance choice.

## Contract structure (clauses to discuss with counsel)

1. **Onboarding:** who supplies DNS, who trains CCC, go-live **definition**.  
2. **Pilot:** duration, data retention, **exit** to paid or deprovision.  
3. **Expansion:** new campus + fee trigger.  
4. **SLA (optional):** what you can actually monitor (e.g. health endpoints)—no fake 99.99%.

## No Stripe in this document

- Payment rail is your choice; the repo’s **entitlements** are separate from how money moves.

## Related

- `PRICING_PACKAGES.md` · `ENTERPRISE_PILOT_PLAN.md`
