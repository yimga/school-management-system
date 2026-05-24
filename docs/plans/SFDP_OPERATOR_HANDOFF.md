SFDP Operator Handoff & Evidence Template

Purpose: Standardized operator playbook and evidence README template for Lane 2 live activation.

Evidence README template (`var/evidence/geos-99/psp/<provider>/README.md`):

---
provider: <provider-slug>
corridor: <country-codes>
date: YYYY-MM-DD
operator_contact: <name/email>
proof_files:
  - redacted_live_key_proof: path_or_description
  - webhook_delivery_log: path_or_description
  - supervised_test_charge: path_or_description
notes: |
  - Redacted fields only. Do not include secrets or full keys. Store secrets in Integration (UI) or secure vault.
---

Operator activation steps
1. Confirm `Integration(provider=<provider>)` has `mode=production` and secrets set in vault/Integration fields (never in git).
2. Run metadata/production ping:
   - `python manage.py check_payment_gateways --school=<slug> --provider=<psp> --mode=production_ping`
3. Create a supervised test charge: use test card or mobile-money flight, confirm ledger `JournalEntry` and `Invoice` created.
4. Validate webhook signature(s) and normalizer path: verify canonical event produced and idempotent ledger post.
5. Populate `var/evidence/geos-99/psp/<provider>/README.md` and attach logs (redacted) as references.
6. Update `docs/external_dependencies_register.json` child row to `verified_live` and include pointer to evidence README.

Handoff acceptance criteria
- Evidence README exists and references the supervised test charge.
- Webhook normalizer applied payments correctly and ledger shows idempotent post.
- Payment success rate & live health snapshot meet minimum thresholds (TBD by operator SLA).

Security and privacy
- NEVER commit live secrets to the repo.
- Evidence must be redacted; store full logs in operator-only artifact storage.
