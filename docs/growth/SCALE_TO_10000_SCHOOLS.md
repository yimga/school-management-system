# Scale to 10,000 schools (strategy, not a promise)

**Purpose:** Shape expectations for **infrastructure, organization, and GTM** if volume grows. This is not a committed roadmap for the repository.

## Infrastructure

- **Multi-instance / multi-region** becomes a product *operations* question: RPO/RTO, database strategy, and where **control plane** runs relative to school data.  
- **Tenant isolation** stays non-negotiable: performance work must not erode RLS/tenant boundaries already in the design.

## Support organization

- **Tier 1:** Account access, login, and “where do I click” for CP.  
- **Tier 2:** Entitlements, domain/DNS, and year/term misconfiguration.  
- **Tier 3:** Engineering and vendor escalation for defects.

## Onboarding at scale

- **Self-serve** where legal and school context allow: activation checklist and docs remain the **honest** ground truth; heavy wizards are a product cost.  
- **Rescue** playbooks for low activation, not infinite custom calls.

## Enterprise expansion

- **Contracting, DPAs, and procurement** are **out of band** in code; the product supports **governance and evidence**—position that clearly in enterprise conversations.

## Pricing evolution

- Tiers in `PRICING_PACKAGES.md` can evolve, but **database entitlements and plans** are the system of record—never two conflicting price “sources of truth.”

## Related

- `INTERNATIONAL_EXPANSION.md` · `Hiring plan` in `../company/HIRING_PLAN.md` · `FUNDING_STRATEGY.md`
