# A–Z provisioning audit & fix prompt (owner signup → MFA → tenant schema)

**Goal:** A brand-new school owner can go from confirmation email → password/name → brand → MFA (setup **or** waive when policy allows) → live portal without stuck schema, MFA-verify-without-device, or incomplete wizard.

**Do not stop** after one slice. Implement → test → remediate until the A–Z path passes.

## Reported defects (must close)

1. **Confirmation → account/brand incomplete** — wizard stalls or never marks `owner_onboarding.completed`.
2. **MFA asked before enrollment** — verify/code page when user has no *confirmed* device; cannot finish setup or waive.
3. **Tenant schema stuck** — `tenant_schema` / Phase A–B never reaches `phase_b_complete` / portal ready.

## Hard rules

- Single SOT: map work to `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 after proof.
- Tenant isolation on every queryset; MFA checks use **confirmed** devices only.
- Never run multi-minute `migrate_schemas` on the gunicorn request thread.
- Proof = named tests green + (when possible) management/scripted A–Z school create.

## Audit checklist (line-by-line)

### A. Confirmation email → token account setup

- [ ] Signup verify link → `accounts:owner_onboarding_account` (token + uidb64)
- [ ] `OwnerOnboardingAccountView` sets password, name, logs in, kicks `_run_owner_provisioning`
- [ ] Success lands on `owner_onboarding_school` (not login, not MFA verify)

### B. Brand / school step

- [ ] Name + primary_color save; skip allowed
- [ ] Advances to MFA step or done per enrollment state
- [ ] Does not depend on schema being live yet

### C. MFA (critical)

- [ ] `has_device` / enrolled helpers use **confirmed** TOTP (or passkey), never unconfirmed draft devices
- [ ] `post_login_mfa.resolve_post_login_mfa_redirect` honors `resolve_mfa_enforcement` (optional/grace → no hard wall)
- [ ] Incomplete `owner_onboarding` is exempt from hard MFA redirect (wizard owns the step)
- [ ] `mfa_verify` with no confirmed device → **setup**, never code entry / login loop
- [ ] Onboarding MFA page: setup works; **waive/continue later** when mode is optional or grace
- [ ] `owner_onboarding_done` does not hard-block forever when waive is allowed
- [ ] RequireMFAMiddleware still exempts `/authentication/onboarding/`

### D. Tenant schema / Phase A–B

- [ ] Kick only via durable outbox / Celery (`kick_complete_provisioning_background` / `dispatch_provision_school`)
- [ ] Watchdog + reconcile resume incomplete Phase B
- [ ] Coverage floor / seed gate do not trap established or mid-onboarding owners incorrectly
- [ ] Idempotent migrations (e.g. academics 0070 school_id)

## Implementation targets (expected files)

- `apps/accounts/post_login_mfa.py` — enforcement mode + onboarding exemption + confirmed-only
- `apps/accounts/views_owner_onboarding.py` — waive path; done gate
- `apps/accounts/views_mfa.py` — verify→setup if no confirmed device
- `apps/accounts/mfa_setup_flow.py` / `_owner_mfa_enrolled` — confirmed-only
- `templates/accounts/owner_onboarding/mfa.html` — continue-without-MFA CTA when allowed
- `apps/schools/tasks.py` / watchdog — only if A–Z still sticks on schema
- Tests: extend `test_owner_onboarding*`, `test_post_login_mfa_routing`, add A–Z smoke

## Validation gates

```bash
python scripts/run_sqlite_memory_tests.py \
  apps.accounts.tests.test_post_login_mfa_routing \
  apps.accounts.tests.test_owner_onboarding \
  apps.accounts.tests.test_owner_onboarding_mfa_cta \
  apps.schools.tests.test_provisioning_seed_gate \
  apps.schools.tests.test_signup_production_readiness
```

Add a focused A–Z test that: create school + membership + token account POST → school POST → MFA waive or confirm → assert onboarding completed and provision kick invoked (mock Celery/outbox).

## Done when

- New owner never sees MFA **verify** without a confirmed device
- Can complete password + brand without schema being live
- Can enroll MFA **or** waive when policy is optional/grace
- Provisioning kick is off-request; healers cover stuck schema
- Tests green; commit + push to `main`
