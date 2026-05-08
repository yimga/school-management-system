# Payment / PSP / settlement — repo-fixable vs external-required

Honest classification for **`global_payments`** and **`marketplace_monetization`** closure posture.  
Full-market category-defining status remains blocked until listed **external** rows reach **`verified_live`** (see **`docs/external_dependencies_register.json`** and SOT §12).

| Blocker | System | Repo-fixable? | External-required? | Current status | Required repo change | Required external action |
|--------|--------|---------------|---------------------|----------------|----------------------|--------------------------|
| Readiness dashboard + health snapshots | global_payments | yes | no | shipped | extend as corridors evolve | none |
| Environment contract documentation | global_payments | yes | no | shipped | keep vars in sync with code | operators set secrets in deployment |
| `check_payment_gateways --mode=metadata` | global_payments | yes | no | shipped | extend provider map | none for metadata mode |
| `missing_credentials` detection | global_payments | yes | no | shipped | tune hint keys per integration | tenant configures Integration |
| `external_required` for CARD/BANK rails | global_payments | yes (signal) | yes (truth) | shipped | none | PSP merchant onboarding |
| Production gateway ping (live API) | global_payments | yes (for Stripe/Paystack/Flutterwave) | yes (for MoMo/Orange/bank) | shipped | non-charge probes for Stripe (`Balance.retrieve`), Paystack (`/transaction/totals`), Flutterwave (`/v3/balances`); MoMo/Orange/bank remain `external_required` by design (no provider-supported non-charge probe) | prod credentials + provider approval |
| Settlement confirmation from PSP | marketplace_monetization | partial | yes | enforced | ledger guards + webhook wiring | processor payouts + webhooks |
| Per-tenant PSP credentials | global_payments | no | yes | external | isolation tests only | tenant merchant accounts |
| Live settlement / payout proof | marketplace_monetization | no | yes | external | dashboard shows blocked reason | bank/settlement verification |
| Manual receipt + reconciliation | global_payments | yes | partial (process owner) | shipped | audits / isolation | operational owner |

**REPO-FIXABLE (non-exhaustive):** readiness UI, env contract docs, gateway health model, metadata checks, settlement state machine (without faking paid), fake/test adapters in CI, reconciliation audit logs, tenant isolation tests, marketplace dashboard blocked reasons, checklists, **non-charge production-ping probes for Stripe / Paystack / Flutterwave (run from deploy host once live secrets land — see `docs/payments/PSP_API_CONNECTION_GUIDE.md`)**.

**EXTERNAL-REQUIRED:** live merchant approval, production keys, webhook secrets from PSP, production connectivity proof, settlement bank verification, payouts, country KYC, PSP contracts, tenant onboarding with PSP.

**HOW TO PROVE LIVE-READY ONCE CREDENTIALS LAND** (per provider):

```bash
# Stripe / Paystack / Flutterwave — non-charge probe
python manage.py check_payment_gateways --school=<slug> --provider=<stripe|paystack|flutterwave> --mode=production_ping
# Expected: status=ready, message ends with "(non-charge production ping)"

# MTN MoMo / Orange Money — metadata only (supervised live txn is the proof)
python manage.py check_payment_gateways --school=<slug> --provider=<mtn_momo|orange_momo> --mode=metadata
# Expected: status=ready (metadata) — then capture aggregator settlement report
```

See `docs/payments/PSP_API_CONNECTION_GUIDE.md` for the per-provider sign-up + key-rotation + webhook-registration recipe.
