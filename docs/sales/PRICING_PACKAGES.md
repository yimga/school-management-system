# RunMyCampus — Pricing and package structure (internal)

**No Stripe or payment capture is defined here.** This is a **GTM and packaging template** for conversations. Actual entitlements in code are driven by `Plan` / `included_features` and related gates; align sales language with the deployment’s data, not this file alone.

## Tiers (conceptual)

### Starter

- **Target**: Single school, lean admin team, need core SIS + portal + basic reporting.
- **Included (example themes)**: core academics and people, portal, baseline reports, limited marketplace/Studio access if contract allows.
- **Limits (example themes)**: lower automation concurrency, fewer scheduled report recipients, narrower API rate expectations (set per environment).
- **Upgrade triggers**: multiple campuses, advanced interop, district connectors, high-volume scheduled delivery.

### Growth

- **Target**: Multi-campus or high-active schools, more operators, need evidence-heavy audits.
- **Included**: Broader `included_features` set, Studio OS and automation where licensed, more marketplace installs subject to plan entitlements.
- **Limits**: Soft caps on background throughput; document in the customer order form.
- **Upgrade triggers**: enterprise SSO, dedicated support, RLS/tenant isolation review sessions, custom integrations.

### Enterprise

- **Target**: Groups, public-sector style governance, or multi-region posture.
- **Included**: Full entitlement negotiation, interop pack, security review support as contracted.
- **Limits**: Set contractually (SLA, support hours), not in this repo.
- **Ideal motion**: security questionnaire → architecture review → pilot tenant → production cutover with runbook in `docs/deployment/`.

## Sales notes

- **Monetization UI** (if present in a deployment) is read-only on plan/usage in many builds; do not promise self-serve card checkout unless Stripe (or other) is live.
- **Entitlements** are enforceable in product; do not claim features that are not in `included_features` for the tenant you are showing.

## Related

- `OBJECTION_HANDLING.md` — scope and “what’s in the box” boundaries.
