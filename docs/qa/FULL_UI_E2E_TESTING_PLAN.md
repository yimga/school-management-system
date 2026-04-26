# Full UI / E2E testing (planning)

**Purpose:** Plan a **coherent, layered** “full” test story for the system under test (SUT) — browser UI, real HTTP, and tenant/manager hosts — **without** replacing `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` or spawning a second product roadmap. Use this to sequence work, staff time, and CI minutes.

**Current repo truth (do not ignore):**

| Layer | What exists | When to use |
|-------|-------------|------------|
| **Django** | `manage.py test` across apps | Regressions, permissions, business logic, URL reverses. |
| **“Operator E2E”** | `scripts/verify_operator_phase10_11_e2e.py` (migrate + pytest + `verify_ux_completion`) | Market/operator/dashboard waves; not a full browser. |
| **Playwright (local/CI)** | `playwright.config.js`, `tests/e2e/ux-visual-qa.spec.js`, `tests/e2e/offline-sync.spec.js`, `scripts/run_visual_qa.sh` | **Real Chromium**, host-resolver rules for `runmycampus.com` / `manager.runmycampus.com`. |
| **Postgres + tenants CI** | `.github/workflows/playwright-tenant-postgres.yml` + `scripts/ci_setup_postgres_tenants_for_visual_qa.sh` | Tenant-host flows that **cannot** be honest on default SQLite. |
| **Human smoke** | `docs/deployment/LAUNCH_SMOKE_TEST.md` | Staging/prod; **14-step** table is the product contract for go-live. |

---

## 1. Definition of “full” (recommended)

1. **Full** does **not** mean “every template in the repo in Playwright.” It means: **(a)** every **tier-1 user journey** has either automated E2E or a **signed** manual smoke, and **(b)** deploy gates stay green.  
2. **Tier-1** (starting set): unauthenticated or login → **tenant home**; **Backend** for staff; **CCC**; **one evidence** page; **one** portal role surface (e.g. teacher) **where Playwright is already set up**; **logout**; optional **manager** open (if control-plane in scope for your release).  
3. **Map tier-1 to** `LAUNCH_SMOKE_TEST.md` so automated E2E **does not invent** a different product story.

---

## 2. Phased rollout (practical)

### Phase A — Stabilize what you already ship (1–2 weeks)

- [ ] `npm ci` and `npx playwright install` documented for Windows/macOS/Linux **the same** as in CI.  
- [ ] `bash scripts/run_visual_qa.sh` green on a **dedicated** machine with env vars from script header (no shared SQLite lock).  
- [ ] `python scripts/verify_operator_phase10_11_e2e.py` in pre-merge or nightly when touching dashboards/marketing.  
- [ ] `LAUNCH_SMOKE_TEST.md` run once per staging cut (human), log date + operator in your release runbook, **not** in this file alone.

### Phase B — Expand Playwright to smoke parity (iterative)

- [ ] For each `LAUNCH_SMOKE_TEST` **step 4–11**, either:  
  - **Automate** a minimal “GET + visible selector” check in `tests/e2e/` (tag `@smoke`), **or**  
  - **Explicitly exclude** with reason (e.g. entitlements, needs seed student id) and keep manual-only.  
- [ ] Reuse `data-rmc-*` and shell markers already required by `verify_shell_surface_inventory.py` for **stable** selectors.  
- [ ] Add **@enterprise** (or similar) for long flows; do not block PR on the full 14 steps until parallelization and DB are ready.

### Phase C — Environments and data

- [ ] **SQLite (fast):** `run_visual_qa` + subset of e2e; good for **developer** pre-push.  
- [ ] **Postgres + django-tenants (honest):** `playwright-tenant-postgres` path for **CI** and release candidates.  
- [ ] **Seed contract:** one doc table: users (`seed_render_users` or equivalent), schools, and **one** student id for Student 360 — **versioned** with migrations so E2E does not chase random PKs.  
- [ ] **Secrets:** never commit; CI uses `GITHUB_SECRETS` / **ephemeral** passwords aligned with `ENVIRONMENT_VARIABLES.md`.

### Phase D — Flake budget and triage

- [ ] **Timeout policy:** `playwright.config.js` (45s); increase only per-test for cold starts.  
- [ ] **Retries:** keep `trace: on-first-retry` for first failure; cap CI retries to avoid masking real failures.  
- [ ] **Quarantine:** failing E2E moved to a `quarantine/` project with issue link — not silently skipped in main project.

---

## 3. CI / cadence (suggested, not a mandate)

| Cadence | Job |
|---------|-----|
| **Per PR (light)** | Django tests (scoped), key `verify_*.py` from CONTRIBUTING, optional Playwright **smoke** project only if minutes allow. |
| **Nightly / main** | `run_visual_qa` or `playwright-tenant-postgres` on schedule; archive traces to artifacts. |
| **Pre-prod** | Full human `LAUNCH_SMOKE_TEST` + `STAGING_RELEASE_EXECUTION` minimum bar. |

---

## 4. Gaps to close (inventory)

- [ ] **Manager host E2E** (e.g. `/sales/`, super surfaces): add **dedicated** spec + `public_host_kind=manager` in request — not mixed with tenant specs without `HTTP_HOST` discipline.  
- [ ] **Cross-origin / CSRF:** E2E must use same **CSRF_TRUSTED_ORIGINS** as staging (document env for local Playwright).  
- [ ] **Windows SQLite lock:** use **unique** `DJANGO_TEST_DB_FILE` per job; document in CONTRIBUTING.  
- [ ] **Coverage report:** agree whether **E2E** is measured (often no); use **journey** checklist + smoke table as coverage instead of % lines.

---

## 5. Link to canonical execution (SOT)

- When a **formal** gate is adopted for “UI E2E required,” add **one** row in `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` (forward queue) pointing here + the **named** command (`run_visual_qa` / workflow name). **Do not** mark rows DONE without a green named verifier.  
- **Supporting** audit and scripts index: `docs/PHASES_3_11_GATE_VERIFICATION.md`, `docs/MANAGEMENT_COMMANDS_INDEX.md` (lines for `run_visual_qa`, `verify_operator_phase10_11_e2e`).

---

## 6. Next step (one decision)

**Pick a single “definition of done” for the first milestone:** e.g. *“Playwright smoke: login, backend shell marker, CCC 200, logout — green on Playwright-tenant-postgres on `main`.”* Then add specs and CI wiring to match that sentence only.

**Related files:** `playwright.config.js` · `tests/e2e/*.spec.js` · `docs/deployment/LAUNCH_SMOKE_TEST.md` · `docs/launch_studio_checklist.md` (CI note) · `CONTRIBUTING.md` (pre-merge if present).
