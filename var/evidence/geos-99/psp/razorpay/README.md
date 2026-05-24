# Razorpay — Lane 2 evidence (SFDP 1443)

Repo-complete: `apps/finance/gateways/razorpay.py`, webhook normalizer, production_ping via `/v1/payments`.

Operator: KYC + `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` in Integration; file `phase1_razorpay_charge_evidence.json` from template; flip `razorpay_india` register row to **verified_live**.
