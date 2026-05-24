# Flutterwave — Lane 2 evidence (SFDP 1429)

Repo-complete: `apps/finance/gateways/flutterwave.py`, webhook normalizer, CM corridor profile.

Operator checklist:

1. Flutterwave merchant account + `FLW_SECRET_HASH` for webhooks.
2. Live keys in tenant Integration config (encrypted).
3. Webhook URL: `https://<tenant-host>/finance/payments/webhook/flutterwave/`
4. Store redacted settlement export path in secure vault; reference filename only here.
