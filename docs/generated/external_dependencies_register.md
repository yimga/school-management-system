# External dependencies register

**Source:** `docs/external_dependencies_register.json`  
**Blocking level counts:** `{"blocks_feature": 1, "blocks_full_market": 3, "blocks_region": 5, "non_blocking": 5}`  

## Payments / PSP highlights

| Id | Dependency | Blocking | Status | Repo readiness | External action |
|----|------------|----------|--------|----------------|-----------------|
| bank_sepa_card_partner | Bank / SEPA / sponsor bank rails | blocks_full_market | not_started | complete — CARD/BANK rails flagged external_required without PSP; abstracted by Stripe SEPA / GoCardless when used | Legal + banking onboarding outside repo (sponsor bank agreement, creditor identifier for SEPA, scheme membership) |
| flutterwave_multi_country | Flutterwave — Africa multi-country fallback | blocks_region | credentials_needed | complete — adapter scaffolding, webhook signature verification, non-charge production_ping (/v3/balances) ready to run when live FLWSECK-...-X lands | Flutterwave merchant onboarding + live secrets |
| manual_fallback_operations | Manual offline receipt + reconciliation owner | blocks_feature | approved_test | complete — TenantPaymentPolicy.allow_manual_offline_proof flag, receipt-capture UX, finance reconciliation queue, AuditLog approve/reject trail | Define operational procedure per tenant (who approves) |
| mtn_momo | MTN MoMo collections | blocks_region | waiting_on_provider | complete — Integration slug mtn_momo / mtn, callback receiver, metadata health check; no non-charge probe by design (telco does not expose one — supervised live txn is the only honest proof) | Telco / aggregator production approval + credential provisioning |
| orange_money | Orange Money collections | blocks_region | waiting_on_provider | complete — Integration slug orange_momo / orange, callback receiver, metadata health check; no non-charge probe by design (partner does not expose one — supervised live txn is the only honest proof) | Partner onboarding + callbacks |
| paystack_wa | Paystack — Ghana / Nigeria cards & bank transfers | blocks_region | credentials_needed | complete — regional hints, adapter stubs, non-charge production_ping (/transaction/totals) ready to run when sk_live_* lands | Merchant approval and production keys in tenant/integration config |
| stripe_global_cards | Stripe — global card payments | blocks_full_market | credentials_needed | complete — integration hooks, webhook scaffolding, metadata health command, non-charge production_ping (Balance.retrieve) ready to run when sk_live_* lands | Complete Stripe onboarding; configure live keys and webhook endpoint in deployment secrets |

## Systems impacted (aggregate)

accounts, global_payments, marketplace_monetization, mobile_clients, multi_region, notifications, platform_runtime, platform_security, sales_contracts
