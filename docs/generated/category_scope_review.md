# Category scope review (program_gap_registry / system_closure_map)

**Date:** 2026-05-03  
**Inputs:** `docs/generated/system_closure_map.json`  
**Verdict:** **CATEGORY DEFINING — REPO SCOPE**

## Systems in `systems[]`

| System | gap_status | Classification | Repo-actionable gap? | External-only? | Notes |
|--------|------------|----------------|----------------------|----------------|-------|
| developer_platform | closed | closed | no | no | — |
| workflow_engine | closed | closed | no | no | — |
| event_system | closed | closed | no | no | — |
| data_platform | closed | closed | no | no | — |
| tenant_lifecycle | closed | closed | no | no | — |
| offline_first | closed | closed | no | no | — |
| global_payments | partial | partial_external_blocker | no | yes | Credential-backed live PSP merchant onboarding and production payment-gateway ping (Stripe/Paystack/Flutterwave/MoMo pro… |
| experience_control | closed | closed | no | no | — |
| marketplace_monetization | partial | partial_external_blocker | no | yes | Live PSP merchant settlement + production gateway health ping — tenant/external (global_payments); honest ledger never f… |
| enterprise_security | closed | closed | no | no | — |

## Labels previously missing from closure map

_None — `experience_control`, `marketplace_monetization`, `enterprise_security` are present in the closure map registry._

## Classification rule summary

- **partial_repo_gaps:** `missing_pieces` require more in-repo tests/surfaces (not honest to claim FULL MARKET category defining).
- **partial_external_blocker:** `global_payments` live PSP truth outside repo.
- Marketing route/chrome cleanup supports **experience_control** evidence only; it does not close marketplace monetization or enterprise security.

## Proof gates

See `category_scope_review.json` key `proof_gates` (populated after verifier runs).

