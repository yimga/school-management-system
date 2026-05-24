# MTN MoMo — Lane 2 evidence (SFDP 1428–1429 + Phase 2)

Repo-complete: `apps/finance/gateways/mtn_momo.py` (or integration slug `mtn_momo` / `mtn`), webhook normalizer, GH/CM/UG regional profiles.

**Honest constraint:** MTN does not expose a safe non-charge `production_ping`. Use `--mode=metadata` for credential shape checks; corridor-live proof is one supervised collection transaction.

Operator checklist:

1. Aggregator / telco production API approval for target country (CM, GH, UG).
2. Store API user/key in tenant `Integration(provider=payments)` — never in git.
3. Register callback URL with aggregator: `https://<tenant-host>/finance/payments/webhook/mtn_momo/`
4. Run supervised live txn; save redacted evidence as `phase1_mtn_momo_charge_evidence.json` (copy from `.template.json`).
5. Flip `mtn_momo` in `docs/external_dependencies_register.json` to **verified_live** only after step 4.
