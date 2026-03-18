# Billing SKUs and entitlements (BR-10)

| SKU tier | Includes | Notes |
|----------|----------|-------|
| **Core** | SIS, academics, people, portal, basic reports | Default tenant |
| **Interop** | OneRoster, district hub, LTI/OIDC/SAML, SCIM | Add-on or bundle |
| **Intelligence** | Analytics benchmarks, ML stubs, at-risk (EWS), AI gateway quotas | Entitlement-gated |

Align `Plan` / marketplace listings with this matrix; document in trust center and `/api/v1/manifest.json` feature flags where applicable.
