# Paystack — Lane 2 evidence (SFDP 1427)

Repo-complete: `apps/finance/gateways/paystack.py`, webhook normalizer, NG/GH regional profiles.

Operator checklist (do not mark `verified_live` until complete):

1. Merchant KYC approved in Paystack dashboard.
2. `sk_test_*` / `sk_live_*` stored in tenant `Integration(provider=payments)` — never in git.
3. Webhook URL: `https://<tenant-host>/finance/payments/webhook/paystack/`
4. Capture redacted evidence: `phase1_paystack_charge_evidence.json` (template in repo).
