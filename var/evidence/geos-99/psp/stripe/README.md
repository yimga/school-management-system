# Stripe PSP evidence (GEOS step 5)

Operator-only artifacts. **Do not commit secrets** (API keys, webhook signing bytes, full card data).

## Phase 1 — Platform direct charge (required before Connect pilot)

Save redacted JSON after one supervised pilot invoice charge + refund on Render:

```
var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.json
```

(Dated copies optional: `phase1_platform_charge_<YYYY-MM-DD>.json`.)

Use `phase1_platform_charge_evidence.template.json` as the shape. Initialize pending scaffold:

```bash
python scripts/run_lane2_operator_playbook.py --school=<slug> --batch=1170 --init-evidence
```

Proof commands:

```bash
python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=production_ping
```

## Phase 2 — Connect pilot school

After one school completes Express onboarding and receives a payout:

```
var/evidence/geos-99/psp/stripe/phase2_connect_pilot_evidence.json
```

(Dated copies optional: `phase2_connect_pilot_<school_slug>_<YYYY-MM-DD>.json`.)

Tenant onboarding URL: `https://<tenant-host>/siteconfig/billing-stripe/`

## Register updates

After each phase, set status in `docs/external_dependencies_register.json` and run:

```bash
python scripts/generate_external_dependencies_register.py --write
python scripts/verify_greatest_education_os_matrix.py --write
```

Only use **`verified_live`** when an evidence file path exists in this directory.
