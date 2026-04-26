# RunMyCampus — Enterprise positioning

This document supports **sales and onboarding conversations**. It does not replace the platform execution ledger: see `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` for engineering completion state.

## What RunMyCampus is

RunMyCampus is a **multi-tenant school operating system**: academics, people, reporting, finance-related surfaces, compliance hooks, and extensions (marketplace, Studio OS, automation) under a **control-plane-first** UX. Day-to-day work runs in product surfaces; **Django admin remains an Advanced / internal fallback**, not the primary operator experience.

## Differentiation (fact-based)

- **Unified surface**: Portal, backend dashboard, Configuration Control Center (CCC), Studio OS, and operator **evidence** pages use real data and read-only governance views where applicable.
- **Governance**: Config mutation audit, term publish evidence, scheduled reports evidence, report output history, and related links are designed for **traceability**, not box-checking theater.
- **Extensibility**: Marketplace and Studio connect to the same runtime and entitlements model; feature gates and plan limits are the contract layer (no fake billing flows in the core repo unless explicitly added).

## Who cares (see also `BUYER_PERSONAS.md`)

- **Owner / director**: adoption, cost control, brand consistency.
- **Principal / academic lead**: term cycles, publish discipline, teacher visibility.
- **Registrar / records**: academic years, departments, class structure, report readiness.
- **Finance / admin operator**: fee-related gates where configured; reporting schedules.
- **Teacher**: classroom and grading flows (not school-wide admin).
- **Parent**: own children’s results and comms.
- **District / region**: interop and standards alignment where productized.

## What we do not claim in a demo

- No fabricated customer names, revenue, or NPS.
- No “integrated payment” story unless Stripe or another provider is live in the deployment.
- Scoring or “9.5/10” language must match the SOT gates, not marketing hyperbole.

## Related

- Pricing outline: `PRICING_PACKAGES.md`
- Demo flow: `DEMO_SCRIPT.md`
- Objections: `OBJECTION_HANDLING.md`
