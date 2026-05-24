# Orange Money — Lane 2 evidence (SFDP 1429 + Phase 2)

Repo-complete: Orange integration slugs (`orange_momo`, `orange_money`), webhook normalizer, CM/CI/SN regional profiles.

**Honest constraint:** Partner APIs vary by country; no universal non-charge ping. Use `--mode=metadata` for Integration health; live proof requires partner-approved credentials + supervised txn.

Operator checklist:

1. Orange / partner merchant onboarding for corridor (CM, CI, SN).
2. Partner API credentials in `Integration(provider=payments)`.
3. Callback URL registered with partner.
4. Supervised collection txn; file `phase1_orange_money_charge_evidence.json` from template.
5. Flip `orange_money` register row to **verified_live** only with evidence on disk.
