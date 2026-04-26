# GTM handoff — RunMyCampus (internal)

**Status:** Staging **readiness** is **documented** (execution checklist + smoke + verifiers in repo). **A live deployment is** your **org’s** Render/dashboard action — not auto-complete from this file.

## Target ICP (initial)

- **Private K–12** or small **multi-campus** groups that need a **unified** portal, **operator evidence**, and **extensible** apps (marketplace, Studio) without re-building tenant isolation.
- **Secondary buyers:** principal/registrar (operations), finance/admin (scheduled reports, bulk comms where enabled), IT (interop, admin fallback discipline).

## Core positioning

- **School operating system** with **control-plane-first** navigation: Configuration Control Center, evidence pages, and Studio — not “admin screens as the product.”
- **Django admin** = **Advanced / internal** only; CP routes are primary (see `docs/sales/RUNMYCAMPUS_ENTERPRISE_POSITIONING.md`).

## Demo flow

- **Script:** `docs/sales/DEMO_SCRIPT.md` (login → dashboard → CCC → evidence → reports → Studio/marketplace → admin last → logout).
- **Post-deploy product smoke:** `docs/deployment/LAUNCH_SMOKE_TEST.md` (repo-accurate paths on tenant host).

## Pricing / packaging

- **Reference:** `docs/sales/PRICING_PACKAGES.md` (Starter / Growth / Enterprise framing). **No payment flow** is implied in-repo unless you enable Stripe (or other) in deployment.

## Deployment status (repo truth)

- **Documentation:** `docs/deployment/STAGING_RELEASE_EXECUTION.md`, `docs/deployment/PRODUCTION_DEPLOYMENT_CHECKLIST.md`, `docs/deployment/RENDER_DEPLOYMENT_RUNBOOK.md`, `docs/deployment/ENVIRONMENT_VARIABLES.md`.
- **Tests:** A **staging prep** bar and verifiers can be re-run as documented in those files; this does not replace a **live** health check on **your** URL.

## Internal pipeline (founder / control-plane operators)

- **Manager host:** `/sales/` — minimal **Lead** + **PipelineStage** + **Activity** list (requires control-plane access). No external CRM.
- **Growth playbooks:** `docs/growth/OUTREACH_PLAYBOOK.md`, `docs/growth/FIRST_50_CUSTOMERS_PLAN.md`, `docs/growth/SCALE_TO_1000_SCHOOLS.md`.
- **Enterprise:** `ENTERPRISE_SALES_SCRIPT.md`, `ENTERPRISE_PILOT_PLAN.md`, `ENTERPRISE_ROLLOUT_CHECKLIST.md`, `ENTERPRISE_CONTRACTS_AND_PRICING.md`.

## Next sales action (suggested)

1. **Lock staging URL** and replace **ALLOWED_HOSTS** / **CSRF_TRUSTED_ORIGINS** / service hostname in the hosting dashboard.
2. **Run** `LAUNCH_SMOKE_TEST.md` on the school subdomain with a **seeded demo tenant**.
3. **Book** a live demo using `DEMO_SCRIPT.md`; send **one-pager** from `BUYER_PERSONAS.md` + `PRICING_PACKAGES.md` as pre-read.
4. **Hand security** the architecture notes from deployment docs + SOT — not invented certifications.

## First customer

- **Onboarding sequence:** `docs/sales/FIRST_CUSTOMER_ONBOARDING.md` (account → setup → first milestone → live).

## Related

- **Objections:** `docs/sales/OBJECTION_HANDLING.md`
- **Enterprise positioning:** `docs/sales/RUNMYCAMPUS_ENTERPRISE_POSITIONING.md`
- **Release notes (product):** `docs/deployment/RELEASE_NOTES_LAUNCH.md`
- **Company (hiring, funding):** `docs/company/HIRING_PLAN.md`, `docs/company/FUNDING_STRATEGY.md`
- **Scale / international:** `docs/growth/SCALE_TO_10000_SCHOOLS.md`, `docs/growth/INTERNATIONAL_EXPANSION.md`
