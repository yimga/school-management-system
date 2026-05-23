# GEOS-99 Lane 2 operator checklist

**Repo status:** Lane 1 **GEOS_99_MATRIX_PASS** (all pillars repo 100%). **Composite 99%** requires this checklist with evidence under `var/evidence/geos-99/` (gitignored secrets).

## Status ladder

`not_started` → `credentials_needed` → `in_progress` → `approved_test` → `approved_production` → **`verified_live`** (evidence path required)

## Order (SOT §13.7)

1. Optional: `STAGING_PROFILE=1` + `python scripts/verify_staging_deploy_profile.py`
2. Render deploy + post-deploy shell (`docs/RENDER_SHELL_AFTER_DEPLOY.md`)
3. **SHA parity — DONE 2026-05-23:** `verify_manager_render_parity.py` → [`var/evidence/geos-99/render/sha_parity_2026-05-23.json`](../../var/evidence/geos-99/render/sha_parity_2026-05-23.json) (`verified_live`; Render + manager `commit_sha` match)
4. Email: web+worker `EMAIL_*`; `/super/email/health/`; provision welcome `.eml` in evidence
5. PSP: one settled txn + webhook + ledger (`docs/payments/LIVE_PSP_READINESS_CHECKLIST.md`)
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
npm run verify:geos-99
```

Do **not** set `verified_live` without a file path under `var/evidence/geos-99/`.
