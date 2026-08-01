# Tenant funds custody boundary

## Current product contract

- `apps.billing` may collect RunMyCampus SaaS subscription payments through the operator's Stripe or PayPal account.
- `apps.finance` records school fees. The school is the merchant of record and supplies its own gateway credentials and settlement account.
- RunMyCampus does not collect, hold, pool, split, transfer, or settle tenant school-fee funds.
- Cash, checks, bank transfers, vouchers, manual mobile-money references, invoices, receipts, partial payments, and offline capture remain available without a PSP.
- Online collection is optional, deployment-gated, tenant-configured, and confirmed only by a signed provider webhook.

## Disabled future backlog

Platform collection or split settlement on behalf of tenants is not activatable by settings, environment variables, feature flags, or counsel tokens. A future implementation requires a separately approved product, legal, licensing, compliance, safeguarding, dispute, refund, treasury, and reconciliation program. It must replace the refusing compatibility stubs rather than bypass them.
