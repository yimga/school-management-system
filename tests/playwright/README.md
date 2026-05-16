# Playwright integration tests — RunMyCampus

End-to-end browser tests that run against a real **staging tenant** of
RunMyCampus (default: `gilead-school`). These are **not unit tests** —
they prove a school can operate the platform by clicking through the
lifecycle the same way a real user would.

## What's here

| File | Purpose |
|---|---|
| `playwright.config.ts` | Playwright config (reads `RMC_STAGING_*` env vars; CI-aware reporter) |
| `tests/first-school-operating-proof.spec.ts` | 8-step lifecycle proof: login → dashboard → class → attendance → marks → reports → invoice → audit |
| `package.json` | Minimal Playwright + TypeScript dependency set |

## Required configuration

The tests are **skipped** unless these three environment variables are set:

| Env var | Example | Notes |
|---|---|---|
| `RMC_STAGING_BASE_URL` | `https://gilead-school.staging.runmycampus.com` | The full staging tenant URL — no trailing slash |
| `RMC_STAGING_TEST_USER` | `proof-runner@gilead-school.test` | Seeded test user with broad enough role to traverse all stages |
| `RMC_STAGING_TEST_PASS` | (secret) | The user's password |

In CI, store these in **GitHub repository secrets** under the exact
names above and they will be injected into the workflow.

The test user should:
- Exist on the gilead-school tenant
- Have a role that can read attendance, marks, reports, finance, and
  (ideally) the audit log — `ADMIN` or `SUPERADMIN` works
- Not be a real human's account (use a service account)

## Running locally

```bash
cd beta/school-management-system/tests/playwright
npm install
npm run install-browsers  # one-time

export RMC_STAGING_BASE_URL=https://gilead-school.staging.runmycampus.com
export RMC_STAGING_TEST_USER=proof-runner@gilead-school.test
export RMC_STAGING_TEST_PASS='...'

npm run test:proof
```

The HTML report lands in `playwright-report/`.

## Running in CI

A workflow at `.github/workflows/first-school-operating-proof.yml` runs
this on `workflow_dispatch` (manual trigger). It does NOT run on every
PR — the dependency is a live staging environment, not the source tree.

To enable nightly runs, change the workflow trigger to `schedule:` and
make sure the staging tenant is reachable from `ubuntu-latest`.

## Why each stage matters

The 8-stage proof maps directly to the user's "first school operating
proof" requirement:

| Stage | What it proves |
|---|---|
| 1. Login + shell | Auth pipeline works; brand cascade resolves; topbar renders |
| 2. Class navigation | Tenant has class data and routes resolve under real load |
| 3. Attendance | Roll-call surface renders with a class selector |
| 4. Marks entry | Evaluations / marks surface reachable |
| 5. Reports | Reports library is accessible |
| 6. Invoice | Finance invoice surface renders for the tenant |
| 7. Audit trail | Audit log records or refuses access (both are valid signals) |

The proof does **not** mutate tenant data — every stage is read-only
verification. If you want a write-path proof (actually take attendance
and verify it persists), add a follow-up spec that uses a sandbox
classroom.

## Honest scope

- This proves **the lifecycle pages render** on a real tenant, not
  that the business logic is correct. Business correctness is the
  Django test suite's job.
- It does **not** run on every PR — staging dependency is too heavy
  for that. Use it as a release gate or nightly canary.
- It targets gilead-school by default but is multi-tenant by env-var
  swap — point `RMC_STAGING_BASE_URL` at any tenant.
- Mutating tests are out of scope for this initial scaffold; add them
  per-stage when you have a sandbox classroom dedicated to the proof.
