# PSP ownership and operator external checklist

## Product boundary

RunMyCampus has two separate payment concerns:

1. **Operator subscription billing** — RunMyCampus charges a tenant for its
   software subscription. The operator owns this merchant account. Stripe is
   the primary implementation; PayPal can remain a later alternative.
2. **Tenant school-fee collection** — each tenant supplies and controls its own
   PSP, bank, or mobile-money merchant credentials. Funds settle directly to
   the tenant. RunMyCampus records invoices, payment state, signed provider
   events, receipts, cash, bank transfers, checks, vouchers, sponsorships, and
   reconciliation evidence. It does not currently collect, hold, split, or
   settle school-fee money for a tenant.

Local and offline operation does not depend on either PSP. A tenant can record
cash or other manual receipts and synchronize them later. Online collection is
an optional tenant integration.

## What the RunMyCampus operator must provide

For **operator subscription billing only**:

- RunMyCampus legal business name, registration/tax details, business address,
  support contact, website, terms, privacy policy, and subscription refund or
  cancellation policy requested by the chosen processor.
- One operator-owned Stripe merchant account and its verified settlement bank
  account. Start with Stripe only; add PayPal only if commercial demand justifies
  the extra reconciliation and support burden.
- Stripe test and live publishable/secret keys, webhook signing secrets, live
  price IDs for each subscription plan/cycle/currency, and the production
  webhook URL. Store all secrets in the deployment secret manager, never Git.
- A successful test subscription checkout, renewal webhook, failed-renewal
  webhook, cancellation, refund/credit path, and a production settlement proof.
- The operator's PCI questionnaire or acquirer confirmation applicable to the
  hosted/redirected payment flow, plus any required external vulnerability scan.
- Named owners for subscription refunds, disputes, reconciliation, secret
  rotation, and incident response.

The operator does **not** need to provide tenant bank accounts, tenant merchant
KYC, or tenant PSP keys. Those belong to each tenant.

## What each tenant provides when enabling online fee collection

- Its chosen provider and operating country/currencies.
- Its own approved merchant account and settlement bank or mobile-money wallet.
- Its own public/API key, secret, merchant/account identifier, webhook-signing
  secret, and any provider callback/IP allowlist settings.
- A sandbox transaction and, before declaring the rail live, one supervised
  payment, signed webhook, duplicate-webhook replay, failure, refund where
  supported, settlement proof, and reconciliation evidence.
- Named tenant owners for refunds, disputes, cash-office closure, and bank
  reconciliation.

Tenants enter secrets through their tenant-scoped payment integration. They do
not send credentials to RunMyCampus staff by email or commit them to source.

## Explicit future backlog

Collection on behalf of tenants, destination charges, application fees,
marketplace splits, pooled settlement, and platform-managed chargebacks are not
current capabilities. They require a separate merchant-of-record/payment-
facilitator product decision, legal and regulatory review, processor approval,
underwriting, reserves and negative-balance policy, tax treatment, expanded PCI
scope, and new accounting controls before any code path may be enabled.

## Evidence commands after credentials are installed

```text
python manage.py check_payment_gateways --school=<tenant-slug> --provider=<provider> --mode=metadata
python manage.py check_payment_gateways --school=<tenant-slug> --provider=<stripe|paystack|flutterwave> --mode=production_ping
```

Production ping is non-charge evidence only. A provider rail is not declared
verified live until tenant-side transaction, webhook, settlement, and
reconciliation evidence exists.
