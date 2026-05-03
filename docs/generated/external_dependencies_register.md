# External dependencies register

**Source:** `docs/external_dependencies_register.json`  
**Blocking level counts:** `{"blocks_feature": 1, "blocks_full_market": 3, "blocks_region": 5, "non_blocking": 5}`  

## Payments / PSP highlights

| Id | Dependency | Blocking | Status | Repo readiness | External action |
|----|------------|----------|--------|----------------|-----------------|
| bank_sepa_card_partner | Bank / SEPA / sponsor bank rails | blocks_full_market | not_started | partial — CARD/BANK rails flagged external_required without  | Legal + banking onboarding outside repo |
| flutterwave_multi_country | Flutterwave — Africa multi-country fallback | blocks_region | credentials_needed | partial | Flutterwave merchant onboarding + live secrets |
| manual_fallback_operations | Manual offline receipt + reconciliation owner | blocks_feature | approved_test | partial — TenantPaymentPolicy + receipt UX where deployed | Define operational procedure per tenant |
| mtn_momo | MTN MoMo collections | blocks_region | waiting_on_provider | partial — Integration slug mtn_momo / mtn | Telco / aggregator production approval + credential provisioning |
| orange_money | Orange Money collections | blocks_region | waiting_on_provider | partial — Integration slug orange_momo / orange | Partner onboarding + callbacks |
| paystack_wa | Paystack — Ghana / Nigeria cards & bank transfers | blocks_region | credentials_needed | partial — regional hints + adapter stubs where present | Merchant approval and production keys in tenant/integration config |
| stripe_global_cards | Stripe — global card payments | blocks_full_market | credentials_needed | partial — integration hooks, webhook scaffolding, metadata h | Complete Stripe onboarding; configure live keys and webhook endpoint in deployme |

## Systems impacted (aggregate)

accounts, global_payments, marketplace_monetization, mobile_clients, multi_region, notifications, platform_runtime, platform_security, sales_contracts
