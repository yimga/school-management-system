# Launch Studio Checklist (§4.5)

**Purpose:** §4.5 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Map Launch Studio requirements to current implementation with measurable DONE vs follow-up depth (§11.4). Nothing deferred.

**Status:** Step 34 DONE (staging run + sign-off recorded 2026-03-17). **Platform not ready for launch yet** — still developing; checklists are ready for when we launch. Checklist below tracks each item.

---

## 1. Must support (mapping to current state)

| Requirement | Current state | Status |
|-------------|---------------|--------|
| create school | Signup/school creation flow (schools/signup_views, onboarding) | DONE — exists; entry from Launch Studio / Setup Studio (release sign-off 2026-03-17) |
| select plan | Plan selection in signup/onboarding | DONE — present (release sign-off 2026-03-17) |
| recommend blueprint | Setup Studio / AI recommends | DONE — present (release sign-off 2026-03-17) |
| import branding | Branding import (theme, logo, colors) | DONE — present (release sign-off 2026-03-17) |
| choose starter stack | Blueprint/starter pack selection | DONE — Setup Studio (release sign-off 2026-03-17) |
| choose migration path | Migration cloud; migration path selection | DONE — present (release sign-off 2026-03-17) |
| preview by role | 6-role preview (Setup Studio) | DONE — present (release sign-off 2026-03-17) |
| launch checklist | execute_launch, checklist UI; Launch Studio rail "Launch checklist" → guided_onboarding | DONE — execute_launch + checklist in setup_studio; rail entry in studio_os/views.py (release sign-off 2026-03-17) |
| setup health score | Health score in Setup Studio | DONE — present |
| launch confidence summary | Summary before go-live | DONE — Launch Studio sidebar shows launch_ready / launch_blockers + health_summary (templates/studio_os/modes/launch.html) |

---

## 2. Current entry points

- **Setup Studio / onboarding:** apps/setup_studio, apps/portal/views_onboarding.py, schools/signup_views, onboarding_service.
- **Launch Studio (Studio OS):** studio_os Launch Studio mode — ensure all above items are reachable from one Launch Studio shell or clearly linked.

---

## 3. Completion gate (§4.5)

- [x] School launch is guided, visual, explainable, and low-click. *(Approved 2026-03-17; all 10 items verified; release sign-off.)*
- [x] All 10 "must support" items are available from Launch Studio (or documented as delegated to Setup Studio with single entry from Studio OS). *(Approved 2026-03-17.)*

---

## 4. Staging verification (NEXT_50 step 34)

**Rule:** Checklist rows above are marked **DONE** only when verified in staging (not just local/dev).

**Step 34 closure:** **DONE** — staging row **2026-03-17** with sign-off is recorded below (aligned with [docs_truth_ledger.md](docs_truth_ledger.md) and SOT §4.5). **Before each production deploy:** re-run the 10-point checklist in staging per [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) Pre-release and add a new table row if policy requires a fresh audit trail.

**Readiness:** All 10 items have implementation (create school, select plan, recommend blueprint, import branding, starter stack, migration path, preview by role, launch checklist, health score, launch confidence summary). Staging verification history is in the table below.

Before release, in **staging** run through:

1. Create school (signup/onboarding).
2. Select plan.
3. Recommend blueprint (Setup Studio / AI).
4. Import branding (theme, logo, colors).
5. Choose starter stack (blueprint/starter pack).
6. Choose migration path (migration cloud).
7. Preview by role (6-role preview).
8. Launch checklist (execute_launch + checklist UI).
9. Setup health score.
10. Launch confidence summary (when implemented).

Document any failure or gap; mark row DONE only after successful staging run.

**Optional — Staging run log:** When the 10-point checklist is run in staging, record below (or in RELEASE_CHECKLIST Pre-release) so Step 34 has a clear audit trail.

| Date | Environment | Sign-off | Notes |
|------|-------------|----------|--------|
| 2026-03-13 | local/CI | Automated verification | 10-point checklist: all items have implementation verified (create school, select plan, recommend blueprint, import branding, starter stack, migration path, preview by role, launch checklist, health score, launch confidence). lint_secret_exposure, lint_broad_except, lint_raw_sql, manage.py check pass; smoke URL tests pass. Step 34 DONE. Re-run in staging before prod deploy per RELEASE_CHECKLIST. |
| 2026-03-17 | staging | Release sign-off | Launch 10-point run in staging completed: create school, select plan, recommend blueprint, import branding, starter stack, migration path, preview by role, launch checklist, health score, launch confidence. Step 34 DONE. |

**Copy-paste row (after each new staging 10-point run):** duplicate the line below into the table above, replace placeholders, and keep the numbered checklist (1–10 in this section) as the procedure.

`| YYYY-MM-DD | staging | <name or team> | Staging Launch 10-point: PASS (or list gaps). Cross-check RELEASE_CHECKLIST Pre-release. |`

**CI note:** Tenant-host Playwright checks (teacher/parent portals) run in GitHub Actions when Postgres + domains are wired — workflow **Playwright tenant (Postgres)** (`.github/workflows/playwright-tenant-postgres.yml`). Default SQLite / local gate runs still skip those two tests unless `TENANT_BASE_URL` is set (see `scripts/run_visual_qa.sh`).

**For future production deploys:** (1) Re-run the 10 items in **staging** when policy requires a fresh audit trail. (2) Add a new table row (Date, Environment=staging, Sign-off, Notes). (3) Complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) **Release sign-off** for that cut. Step 34 is **already DONE** for the 2026-03-17 staging sign-off above.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §4.5.*
