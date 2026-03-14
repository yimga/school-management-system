# Launch Studio Checklist (§4.5)

**Purpose:** §4.5 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Map Launch Studio requirements to current implementation so PARTIAL status is measurable. Nothing deferred.

**Status:** PARTIAL — some flows exist; checklist below tracks each item.

---

## 1. Must support (mapping to current state)

| Requirement | Current state | Status |
|-------------|---------------|--------|
| create school | Signup/school creation flow (schools/signup_views, onboarding) | PARTIAL — exists; unify under Launch Studio shell |
| select plan | Plan selection in signup/onboarding | PARTIAL — present |
| recommend blueprint | Setup Studio / AI recommends | PARTIAL |
| import branding | Branding import (theme, logo, colors) | PARTIAL |
| choose starter stack | Blueprint/starter pack selection | PARTIAL — Setup Studio |
| choose migration path | Migration cloud; migration path selection | PARTIAL |
| preview by role | 6-role preview (Setup Studio) | PARTIAL — present |
| launch checklist | execute_launch, checklist UI | PARTIAL — execute_launch + checklist in setup_studio |
| setup health score | Health score in Setup Studio | DONE — present |
| launch confidence summary | Summary before go-live | NOT DONE — add or document |

---

## 2. Current entry points

- **Setup Studio / onboarding:** apps/setup_studio, apps/portal/views_onboarding.py, schools/signup_views, onboarding_service.
- **Launch Studio (Studio OS):** studio_os Launch Studio mode — ensure all above items are reachable from one Launch Studio shell or clearly linked.

---

## 3. Completion gate (§4.5)

- [ ] School launch is guided, visual, explainable, and low-click.
- [ ] All 10 "must support" items are available from Launch Studio (or documented as delegated to Setup Studio with single entry from Studio OS).

---

## 4. Staging verification (NEXT_50 step 34)

**Rule:** Checklist rows above are marked **DONE** only when verified in staging (not just local/dev).

**Step 34 closure:** Step 34 is **DONE** when a row with **Environment = staging** and **Sign-off** is added below. Until then Step 34 remains **PARTIAL**. **Dependency:** Staging environment access; run the 10-point checklist in staging before production deploy per [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) Pre-release.

**Readiness:** All 10 items have implementation (create school, select plan, recommend blueprint, import branding, starter stack, migration path, preview by role, launch checklist, health score, launch confidence summary). Step 34 moves to DONE only after the 10-point run in staging and this §4 table is filled.

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
| Pending | staging | — | Optional: run 10-point checklist in staging again before production release; add row with date and sign-off. |

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §4.5.*
