# Finance billing ledger certification

**Generated:** 2026-05-20T03:20:13.135586+00:00
**Verdict:** FINANCE LEDGER READY — REPO SCOPE

Audit: `docs/generated/finance_ledger_precision_audit.json`

## Gates

| Gate | OK | Note |
|------|----|------|
| audit_ok | True | precision discovery audit |
| money_float_zero | True | money-float scan: 0 call(s) |
| json_decimal_smoke | True | amount_str + DecimalJSONEncoder |
| module_billing_platform_charge | True | billing_platform_charge |
| module_billing_usage_metering | True | billing_usage_metering |
| module_finance_json_decimal | True | finance_json_decimal |
| module_finance_post_payment_ledger | True | finance_post_payment_ledger |
| module_finance_webhook_claim | True | finance_webhook_claim |
| module_finance_webhook_idempotency | True | finance_webhook_idempotency |
| module_marketplace_ledger_ops | True | marketplace_ledger_ops |
| module_payment_blocker_classification | True | payment_blocker_classification |
| module_payment_webhook_ingress | True | payment_webhook_ingress |
| module_payroll_calculate | True | payroll_calculate |
| decimal_fields_present | True | count=79 |
| psp_lane_external_honest | True | no fake live PSP proof in repo |
| tests_apps_finance_tests_test_ledger_failures | True | exit=0 |

## External (not repo-proven)

- live_psp_merchant_onboarding
- production_settlement_bank_verification
- per_tenant_psp_credentials
