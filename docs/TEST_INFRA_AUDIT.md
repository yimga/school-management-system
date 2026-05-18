# Test Infrastructure Audit (P12)

**Audit date:** 2026-05-17
**Pillar:** P12 — 12-pillar platform audit (test infra slice)
**Authority:** [pytest.ini](../pytest.ini), [conftest.py](../conftest.py), [.github/workflows/](../.github/workflows/)

This document is the **flattened test-infra inventory** — runners, coverage policy, CI matrix, flake policy.

---

## 1. Runners

| Runner | Purpose | Invocation |
|---|---|---|
| Django `manage.py test` | Default — Django test runner, SQLite by default | `python manage.py test apps.X` |
| Postgres tenants test runner | RLS / `django-tenants` parity | `USE_DJANGO_TENANTS=1 python manage.py test --tag=tenants_rls` |
| pytest | Coverage + parametric tests | `pytest apps/X/tests/ --cov=apps.X` |
| Playwright | Browser visual / interaction + axe | `npx playwright test` (via [.github/workflows/marketing-visual-truth.yml](../.github/workflows/marketing-visual-truth.yml)) |
| Lighthouse CI | Core Web Vitals budgets | `npx lhci autorun` (via [.github/workflows/lighthouse-ci.yml](../.github/workflows/lighthouse-ci.yml) + local variant) |

---

## 2. Coverage policy

**Declared thresholds (advisory until CI wires `--cov-fail-under`):**

| App / module | Threshold | Rationale |
|---|---|---|
| `apps/analytics/` | 80% | Model registry + governed analytics path |
| `apps/finance/` | 85% | Money-handling code; aligns with `scan_money_float` zero-tolerance |
| `apps/security/` | 90% | Auth / CSP / tenancy; defense-in-depth tier |
| `apps/api/` | 75% | Public + internal API surface |
| All other `apps/*` | 60% | Floor (drift detection) |

Thresholds declared in `pytest.ini` comments + CI workflow [.github/workflows/coverage-gate.yml](../.github/workflows/coverage-gate.yml) (v3.23.4 follow-up — wired 2026-05-17). Operator turns enforcement ON by setting `COVERAGE_GATE_STRICT=1` in CI environment.

**Coverage report:** `pytest --cov=apps --cov-report=term-missing --cov-report=html` → `htmlcov/index.html`.

---

## 3. CI workflow matrix

| Workflow | Trigger | Purpose |
|---|---|---|
| `architectural-boundaries.yml` | Every PR | 18 architectural scanners (`scan_*` + `verify_*` + `audit_*`) + `check_documented_baselines.py` drift gate |
| `django-tests.yml` | Every PR | SQLite Django test runner, untagged tests |
| `tenants-rls.yml` | PRs touching tenancy/RLS files | Postgres 15 service, `@tag("tenants_rls")` only |
| `playwright-tenant-postgres.yml` | PRs touching tenancy/marketing | Postgres, `@tag("tenants_schema")` only |
| `a11y-axe.yml` | PRs touching templates/static | axe-selenium on 6 public + 18 auth routes |
| `pa11y-ci.yml` | Manual (`PA11Y_BASE_URL` gated) | WCAG2AA against a live URL |
| `lighthouse-ci.yml` | Manual / staging | Core Web Vitals against staging |
| `lighthouse-ci-local.yml` | PRs touching marketing | Boots Django on 127.0.0.1:8123, runs lhci against marketing locally |
| `marketing-visual-truth.yml` | PRs touching marketing | Playwright visual snapshots + axe |
| `k6-baseline-dispatch.yml` | Manual | Load test against staging (operator-supplied URL) |
| `coverage-gate.yml` | Every PR (opt-in enforce) | `pytest --cov` per app + threshold gate (off-by-default until `COVERAGE_GATE_STRICT=1`) |

---

## 4. Flake policy

- **Per-test quarantine** — flaky test gets `@pytest.mark.flaky(reruns=2)` or `@unittest.skip("flake-quarantine: <issue-link>")`. Must carry an issue link, not "tmp" / "todo".
- **Marker visibility** — quarantined tests surface in CI summary; PR cannot land if quarantine grows.
- **30-day rule** — a quarantined test that stays quarantined for 30 days gets either fixed or deleted. No silent-rot quarantine.

---

## 5. Test data + fixtures

| Fixture | Source | Use |
|---|---|---|
| `seed_demo` mgmt cmd | [apps/academics/management/commands/seed_demo.py](../apps/academics/management/commands/seed_demo.py) | Bulk demo data — wrapped in `rls_bypass()` (cross-tenant maintenance) |
| `preview_fixtures` | [apps/siteconfig/management/commands/preview_fixtures.py](../apps/siteconfig/management/commands/preview_fixtures.py) | Marketing preview surfaces — fixed seed |
| Tenant factories | [conftest.py](../conftest.py) + per-app `tests/factories.py` | Per-test tenant setup via `rls_school(school_id)` context |
| `bootstrap_at_risk_registry` | mgmt cmd | Idempotent at-risk model artifact backfill |
| `seed_platform_complete` | mgmt cmd | Render predeploy step (covers ~17 platform seed steps) |

---

## 6. Visual regression

| Surface | Snapshot location | Refresh command |
|---|---|---|
| Marketing | `marketing-snapshots.spec.js-snapshots/` | `UPDATE_SNAPSHOTS=1 npx playwright test marketing-visual-truth` |
| Tenant portal | (queued) | — |

Snapshot pinning is intentional — PRs that change visual output must `UPDATE_SNAPSHOTS=1` and commit the new PNGs.

---

## 7. Daily operator drill

```bash
# Run the full pre-merge bundle locally
python scripts/verify_sot_pillar_evidence.py
python -m pytest apps/portal/tests/
python -m pytest apps/finance/tests/test_webhook_signature_verifiers.py
python -m pytest apps/analytics/tests/test_at_risk_model_registry.py apps/analytics/tests/test_verify_ai_promotion_readiness.py

# Coverage (advisory)
pytest --cov=apps.analytics --cov=apps.finance --cov=apps.security --cov-report=term-missing

# Architectural scanners (CI does this too)
bash scripts/release/render_predeploy.sh   # full predeploy bundle
```

---

## 8. Honest carve-outs

- **Coverage enforcement is opt-in** — thresholds are *declared*; CI strict-mode is `COVERAGE_GATE_STRICT=1`. Until operator flips that flag, coverage is drift-detection, not a gate.
- **Visual regression for tenant portal** — Playwright snapshot infrastructure exists for marketing only. Portal/teacher/parent shell snapshots are queued.
- **k6 baseline numbers** — `var/k6_baseline_last_run.json` stays `pending` until operator runs [scripts/run_k6_baseline_local.sh](../scripts/run_k6_baseline_local.sh) against a real staging URL. Cannot be CI-gated without an external target.
