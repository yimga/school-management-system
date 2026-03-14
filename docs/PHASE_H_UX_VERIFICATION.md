# Phase H — Full codebase and live UX verification

**Source:** RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §11 Phase H.

**Goal:** Before considering the plan complete, ensure the entire codebase and live experience are production-ready and visibly correct after deployment.

---

## 1. Automated tests

| Test module | Scope | DB required |
|-------------|--------|-------------|
| `apps.accounts.tests.test_smoke_urls` | URL name → path resolution (critical + Phase H Studio/super) | No (SimpleTestCase) |
| `apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests` | Super, Studio OS, siteconfig reverse() | No (SimpleTestCase) |
| `apps.accounts.tests.test_phase_h_ux_verification.PhaseHCriticalPathsTests` | GET critical paths on manager + tenant host; no 404/500 (middleware/context_processors hit DB) | Yes (TestCase) |
| `apps.accounts.tests.test_phase_h_ux_verification.PhaseHErrorHandlersTests` | 403/404/500 handlers render with correct status | Yes (TestCase) |

**Run (no DB):**
```bash
python manage.py test apps.accounts.tests.test_smoke_urls apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests
```

**Run (full Phase H, requires DB + migrations):**
```bash
python manage.py test apps.accounts.tests.test_phase_h_ux_verification
```

---

## 2. Critical paths (no 404/500)

- **Manager host** (`manager.runmycampus.com`): `/`, `/super/`, `/admin/`, `/authentication/login/`, `/studio/experience/`, `/studio/automation/`, `/studio/control/`, `/health/`, `/healthz/`, `/api/health/`, `/siteconfig/preferences/`, `/siteconfig/console/`.
- **Tenant/default host**: `/`, `/health/`, `/healthz/`, `/admin/`, `/authentication/login/`, `/authentication/backend/`, `/portal/parent/`, `/finance/`, `/analytics/`, `/compliance/dashboard/`, `/studio/experience/`, `/siteconfig/customizer/`, `/discover/`, `/support/`, `/verify/`.

Acceptable status codes: 200, 301, 302, 403 (not 404 or 500).

---

## 3. Error pages

- 403/404/500 handlers must render with correct status.
- On manager host, 403/404/500 use control-plane templates (`errors/*_control_plane.html`).
- On tenant host, 403/404/500 use tenant templates (`errors/403.html`, `errors/404.html`, `errors/500.html`).

---

## 4. Responsive and layout (Phase H gate)

- **Static audit:** `python scripts/phase_h_audit.py` — checks base shells for viewport meta and overflow containment; **skip-to-main-content link** in base and control_plane_skeleton (a11y); tenant and control-plane error templates exist and extend base; optional responsive CSS assets reported as **warnings when missing (warnings always printed when present, not only with --verbose)**.
- **With URL checks:** `python scripts/phase_h_audit.py --live` — same plus URL reverse for critical names (requires Django).
- **Verbose:** `python scripts/phase_h_audit.py --verbose` or `--live -v` — prints each check performed; warnings (e.g. missing optional CSS) are always shown when present; --verbose adds per-check trace.
- **CI:** `scripts/pre_deploy_gate.sh` runs `python scripts/phase_h_audit.py` (static) after smoke + Phase H URL reverse tests.
- **Expectations:** Base shells: viewport, overflow containment, skip-link; all six error templates use `extends`.

## 5. Manual / live checklist (optional)

- [ ] Every link and primary button on manager admin/super/studio resolves (no 404/500).
- [ ] Dashboards and key pages load; no server-not-found or 500.
- [ ] UI is responsive (mobile, tablet, desktop); no fixed-width bloat; typography scales (Flexbox/Grid; fluid containers; clamp() or media queries).
- [ ] Pages are in frame; nothing spewing outside frames.
- [ ] Labels and structure are clear; platform is architecturally sound.
- [ ] After deployment, changes are visibly seen and behave as intended.

---

## 6. Completion gate

**Phase H completion:** No broken links/buttons/shortcuts; no erroring pages or dashboards; consistent high-end UI/UX; correct framing and structure; proper seeding and integration; successful merge/deploy with no critical issues.

When automated path and error-handler tests pass (with DB) and smoke + URL-reverse tests pass (no DB), Phase H automated verification is satisfied. Manual checklist can be used for staging/production sign-off.

---

## 7. Phase H reliable subset (run full test suite — slice)

For **"Run full test suite and any smoke/E2E checks"** (RUNMYCAMPUS Phase H), the **Phase H reliable subset** runs without a full migrated test DB:

```bash
bash scripts/run_phase_h_verification.sh
```

This runs: (1) smoke URLs + Phase H URL reverse tests, (2) `phase_h_audit.py` (static), (3) `phase_h_audit.py --live`. Set `PHASE_H_SKIP_LIVE=1` to skip the live URL reverse (e.g. in minimal CI). The full `scripts/pre_deploy_gate.sh` includes this slice plus migrations, lints, and targeted hardening tests; when the full gate passes, Phase H automation is covered as part of it.
