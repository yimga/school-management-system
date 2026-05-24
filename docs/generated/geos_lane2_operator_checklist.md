# GEOS-99 Lane 2 operator checklist

**Repo status:** Lane 1 **GEOS_99_MATRIX_PASS** (all pillars repo 100%). **Composite gate:** `python scripts/verify_greatest_education_os_matrix.py --require-composite-99` → **GEOS_99_COMPOSITE_PASS** when register + pilot evidence are synced (`scripts/sync_geos_evidence_to_register.py --write`, `record_geos_internal_core_loop`). **True production Stripe/SOC2/live-cloud AI** still require operator steps below.

## Status ladder

`not_started` → `credentials_needed` → `in_progress` → `approved_test` → `approved_production` → **`verified_live`** (evidence path required)

## SOT batches 1170 / 1171 / 1174 (operator — parallel)

Canonical queue-head status: **REPO-COMPLETE (operator playbook)**. Legacy body rows marked **SUPERSEDED** where duplicated. Live money remains **NOT verified_live** until evidence JSON exists on disk.

| Batch | Scope | Evidence path | Commands |
|-------|--------|---------------|----------|
| **1170** | Stripe platform charge + Connect pilot | `var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.json`, `phase2_connect_pilot_evidence.json` | [`STRIPE_CONNECT_PLATFORM_SETTLEMENT_PLAN.md`](../plans/STRIPE_CONNECT_PLATFORM_SETTLEMENT_PLAN.md) Phase 1→2 |
| **1171** | WAfrica + global PSP keys per tenant | `var/evidence/geos-99/psp/<psp>/phase1_*_evidence.json` | `manage.py check_payment_gateways --mode=metadata` then `production_ping` where allowed |
| **1174** | Live reconciliation + health snapshot | `var/evidence/geos-99/psp/live_reconciliation_evidence.json` | Supervised charge + snapshot IDs (redacted) |

**Single runner (metadata + evidence gap report):**

```bash
python scripts/run_lane2_operator_playbook.py --school=<slug> --batch=all --init-evidence --write-report
```

Exit **2** = scaffold OK, operator evidence still pending (honest). Exit **0** = evidence files present (operator must still review before `verified_live`).

### 1170 — Stripe live (Engine 1)

1. Stripe onboarding: **non-recurring + recurring + platform/marketplace** (all three).
2. Render: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`.
3. Webhook: `/finance/payments/webhook/stripe/`.
4. `python manage.py check_payment_gateways --school=<slug> --provider=stripe --mode=metadata`
5. When `sk_live_*` exists: `--mode=production_ping` (Balance.retrieve — no charge).
6. One supervised platform invoice charge + refund → fill `phase1_platform_charge_evidence.json`.
7. Connect Express pilot at `/siteconfig/billing-stripe/` → fill `phase2_connect_pilot_evidence.json`.
8. Flip `stripe_global_cards` / `stripe_connect_platform` in `docs/external_dependencies_register.json`.

### 1171 — WAfrica / global corridors (Engine 2)

1. Enable `Integration(provider=payments)` per PSP on pilot tenant (admin / School Studio).
2. Metadata: `python manage.py check_payment_gateways --school=<slug> --provider=<psp> --mode=metadata`
3. Production ping (Stripe, Paystack, Flutterwave only when live keys exist): `--mode=production_ping`
4. MTN / Orange: metadata only — supervised live txn is the proof.
5. Evidence template → `var/evidence/geos-99/psp/<psp>/phase1_*_evidence.json`; flip child register row.

See [`apps/finance/payment_lane2_checklist.py`](../../apps/finance/payment_lane2_checklist.py) and SFDP plan **§8.1**.

### 1174 — Live reconciliation

1. Complete supervised live charge (any pilot corridor).
2. Run health rollup: `python manage.py check_payment_gateways --school=<slug> --mode=metadata` (writes `PaymentGatewayHealthSnapshot`).
3. Fill `live_reconciliation_evidence.json`: redacted charge/webhook/ledger IDs + settlement artifact reference.
4. Do **not** store secrets, PAN, or raw webhook signing bytes in git.

## Order (SOT §13.7)

1. Optional: `STAGING_PROFILE=1` + `python scripts/verify_staging_deploy_profile.py`
2. Render deploy + post-deploy shell (`docs/RENDER_SHELL_AFTER_DEPLOY.md`)
3. **SHA parity — DONE 2026-05-23:** `verify_manager_render_parity.py` → [`var/evidence/geos-99/render/sha_parity_2026-05-23.json`](../../var/evidence/geos-99/render/sha_parity_2026-05-23.json) (`verified_live`; Render + manager `commit_sha` match)
4. Email: web+worker `EMAIL_*`; `/super/email/health/`; provision welcome `.eml` in evidence
5. PSP: one settled txn + webhook + ledger (`docs/payments/LIVE_PSP_READINESS_CHECKLIST.md`) — batches **1170–1174** above
6. Pilot slot 1: all core-loop booleans in `docs/generated/pilot_readiness_scorecard.json`
7. SOC2 / residency: compliance PDFs when available
8. Regenerate: `python scripts/generate_external_dependencies_register.py --write`
9. Matrix: `python scripts/verify_greatest_education_os_matrix.py --write`

## AI Option A (batch 1402 — separate from step 3)

- Repo: **RENDER_ONLINE_AI_POSTURE_PASS** + [`docs/AI_DEPLOYMENT_POSTURE.md`](../AI_DEPLOYMENT_POSTURE.md) Option A
- Production: set `LITELLM_*` on Render; flip register `openai_litellm_option_a` to **verified_live** after AI Center shows **live_cloud**

## Proof (repo scaffold only)

```bash
python scripts/verify_geos_lane2_scaffold.py
python scripts/verify_payment_gateway_lane2_scaffold.py
python scripts/run_lane2_operator_playbook.py --school=<slug> --batch=all
npm run verify:geos-99
```

Do **not** set `verified_live` without a file path under `var/evidence/geos-99/`.
