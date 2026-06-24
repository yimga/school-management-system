# Moderator Program — Global Multi-Tenant + Tenant Customer 250+ Seal

**Batch:** SOT §11.4 **1726** (moderator orchestration)  
**Status:** IN PROGRESS  
**Primary E2E tenant:** `demo-school` (display name: **New Test High School**)  
**Isolation tenant:** `rmc-tenant-isolation-probe` (cross-tenant tests only)

## Programs

| Program | Branch tag | Goal |
|---------|------------|------|
| **P0 BLOCKER** | `seal/runtime-proof` | E2E harness, migrations, seed — nothing proceeds until green |
| **P1 Global** | `seal/global-multitenant` | Manifest 2.0, operational lifecycle FSM, tenant isolation |
| **P2 Tenant Customer** | `seal/tenant-customer-250` | Seed blueprint, country matrix, portals, daily ops, wedges |
| **P3 Hygiene** | `seal/runtime-proof` | Route proof, hygiene classification, contradiction audit |

## Agent roster

| Agent ID | Name | Owns | Programs |
|----------|------|------|----------|
| **M0** | Moderator | Gates, SOT rows, assignments, contradiction audit | All |
| **A1** | Conception/Provisioning | Customer→school→tenant, `demo_user_seeding`, provisioning | P0, P2 W1–W2 |
| **A2** | Country/Education | 249 matrix, `by_wave` regions, localization packs | P2 W3 |
| **A3** | Setup Studio/Manifest | Wizard, `tenant_manifest_compiler`, launch readiness | P1 W1.3, P2 W4 |
| **A4** | Profiles/RBAC/Portals | Role homes, sidebar, workflow portals | P0, P2 W5 |
| **A5** | Daily Operations | Attendance, marks, AY close, synthetic chains | P2 W6 |
| **A6** | Finance/Comm/Funding | Fees, manual fallback, NGO surfaces | P2 W6, W9 |
| **A7** | Offline/PWA | OFFLINE_* taxonomy, SW, sync queue | P1, P2 W7 |
| **A8** | AI/Help | `tenant_ai_help`, route grounding | P2 W8 |
| **A9** | Customer Success | Health, nudges, blockers | P2 W1, W9 |
| **A10** | Premium UI/E2E | Playwright, luxury, page-fold | P0, P2 W10 |
| **L1** | Lifecycle | `tenant_lifecycle_*`, operational FSM | P1 W1.2 |
| **I1** | Isolation | `apps/tenancy/*`, queryset safety | P1 W1.1 |
| **H1** | Hygiene | dead hrefs, interaction integrity, proof canon | P3 |

## Wave order (strict)

```
P0-BLOCKER → P1-W1.1 → P1-W1.2 → P1-W1.3 → P2-W0 inventory → P2-W2 seed blueprint
→ P2-W5 portals → P0 role-home 5/5 → P2-W3 W-Africa → P2-W6 daily ops
→ P2-W7 offline → P2-W8 AI → P2-W9 wedges → P2-W10 UX → P3 hygiene → P2-W12 second audit
```

## Gate table (paste stdout on every handoff)

| Gate | Command | PASS token |
|------|---------|------------|
| G0 | `makemigrations --check --dry-run` | No changes detected |
| G1 | `manage.py check` | 0 issues |
| G2 | `scan_tenant_queryset_safety.py --compare` | 0 |
| G3 | `verify_tenant_experience_competitor_gap_closure.py` | TENANT_EXPERIENCE_COMPETITOR_GAP_CLOSURE_PASS |
| G4 | `verify_role_home_visual_sweep_harness.py` | ROLE_HOME_VISUAL_SWEEP_HARNESS_PASS |
| G5 | `ROLE_SWEEP_TENANT_ONLY=1` role-home sweep | `failed:0` tenantOnly |
| G6 | `verify_tenant_manifest_runtime_consistency.py` | (when exists) PASS |
| G7 | `verify_operational_lifecycle_fsm_coverage.py` | (when exists) PASS |
| G8 | `verify_tenant_customer_250_country_matrix.py` | (when exists) PASS |
| G9 | `verify_interaction_integrity_completion.py` | INTERACTION_INTEGRITY_PASS |
| G10 | `scan_operator_shell_dead_hrefs.py --strict` | 0 |

## Assignment log

| Cycle | Agent | Wave | Gate | Status | Notes |
|-------|-------|------|------|--------|-------|
| 1 | M0 | Baseline | G0–G4 | PENDING | Initial audit |
| 2 | A1+A10 | P0-BLOCKER | G5 | PENDING | Seed + role-home |
| 3 | I1 | P1-W1.1 | G2 | PENDING | |
| 4 | L1 | P1-W1.2 | G7 | PENDING | |
| 5 | A3 | P1-W1.3 | G6 | PENDING | Manifest 2.0 |
| 6 | A4 | P2-W5 | G3,G5 | PENDING | |
| 7 | A2 | P2-W3 Africa | G8 | PENDING | |

## Verifier creation backlog

- [ ] `scripts/verify_tenant_manifest_runtime_consistency.py` (A3)
- [ ] `scripts/verify_operational_lifecycle_fsm_coverage.py` (L1)
- [ ] `scripts/verify_tenant_customer_250_country_matrix.py` (A2)
- [ ] `scripts/verify_tenant_seed_blueprint.py` (A1)
- [ ] `scripts/verify_new_test_high_school_customer_delivery.py` (A1)

## Rules

1. No wave marked DONE without green named verifier + tests run (not assumed).
2. One `by_wave` country region per A2 session.
3. No new parallel strategy docs — update this file + SOT §11.4 only.
4. Lane 2 (live PSP, SOC2) out of scope; `procurement_packet` honesty enforced.
