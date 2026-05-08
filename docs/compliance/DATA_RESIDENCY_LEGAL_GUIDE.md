# Data Residency / Localization Legal Guide

Per-corridor data residency is a **legal opinion + hosting choice** — not a code change. This guide is the operator's roadmap.

Cross-reference: `docs/compliance/CONTROL_MATRIX.md`, `docs/compliance/regional/` (per-country opinions stored here).

## Decide per corridor

For each new country / region a tenant operates in, answer:

1. **Is there a data-localization mandate?** (e.g. Nigeria NDPR, South Africa POPIA, EU GDPR, Cameroon data law 2010.)
2. **Does the mandate require in-country hosting** or is *adequate cross-border transfer* sufficient (with SCCs / Standard Contractual Clauses)?
3. **What categories of data are in scope?** (student records — yes; aggregated analytics — usually no; payment data — handled by PSP, not localized by us.)
4. **What is the regulator's expectation for response time** to access requests?

Engage local counsel for the written opinion — store the PDF in `docs/compliance/regional/<iso2>_data_residency_opinion.pdf` and reference it in the external register evidence path.

## Hosting choices that satisfy common mandates

| Region | Provider option |
|---|---|
| EU | Render Frankfurt, AWS eu-central-1, Hetzner Helsinki |
| UK | Render Frankfurt + UK SCCs, AWS eu-west-2 |
| Nigeria | Locally-hosted alternative (MainOne, Galaxy Backbone) when NDPR enforcement is strict |
| South Africa | AWS af-south-1, Teraco |
| Cameroon | AWS eu-central-1 with SCCs is typical; local hosting partners exist (Camtel) |
| US | Render Oregon, AWS us-east-1/us-west-2 |
| APAC | Render Singapore, AWS ap-southeast-1 |

## Repo support for multi-region

The platform is region-agnostic at the code level. To deploy a regional instance:

1. Spin up a separate Render service or AWS environment in the target region.
2. Replicate environment configuration (PSP keys, SMTP, etc.).
3. Configure DNS so tenant URLs point to the regional service.
4. Set `DATA_RESIDENCY_REGION` env var so the audit log records it.

Tenant isolation primitives (audited by `audit_tenant_isolation.py`) remain unchanged.

## Cross-border transfer agreements

When data does cross borders (e.g. EU customer hosted in EU, but support engineer in US accesses logs):

- **EU-US:** Data Privacy Framework (DPF) certification or SCCs.
- **EU-UK:** UK adequacy decision is in force.
- **EU-Africa:** SCCs + Transfer Impact Assessment (TIA) required.
- Document the agreement in the customer's DPA.

## What this guide does NOT cover

- The actual legal opinion — you must engage counsel.
- Negotiating SCCs with each customer — commercial.
- Country-specific regulator filings (e.g. Italian DPA notification).
