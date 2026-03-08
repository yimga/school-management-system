# RunMyCampus Full Codebase Review

Date: 2026-03-08

## Scope

Primary review target:

- `apps`
- `config`
- `templates`
- `static`
- `tests`
- `scripts`
- `sdk`
- `manage.py`
- architecture docs under `docs/architecture`

Derived or secondary artifacts treated as non-source unless directly runtime-relevant:

- `node_modules`
- `staticfiles`
- `media`
- backup files
- screenshot/debug artifacts
- prior audit markdown files

Important review rule: existing audit and security markdown files inside the repo were treated as prior opinions, not source truth.

## Method

1. Code-first pass across runtime, tenancy, policy, navigation, marketplace, API, security, migration, and document surfaces.
2. Runtime verification with Django checks and targeted tests.
3. Database snapshot counts for marketplace, registries, and migration cloud maturity.
4. Docs drift pass after independent findings were written.

## Baseline Commands

Executed from repo root:

- `python manage.py check`
- `python -m pytest --collect-only -q`
- targeted `python manage.py test ...`

Observed state:

- `python manage.py check` passed before and after review changes.
- `python -m pytest --collect-only -q` is not a usable developer signal in the current repo state because `pytest-django` is missing and collection throws large numbers of Django setup errors.
- Targeted Django tests are viable, but first-run database setup is expensive because the test runner applies a very large migration set.

## Inventory Snapshot

Top-level `apps` directories: 35

Repository file count excluding heavy derived folders: 2796

Top file extensions:

| Extension | Count |
|---|---:|
| `.py` | 1444 |
| `.md` | 618 |
| `.html` | 422 |
| `.css` | 81 |
| `.log` | 52 |
| `.js` | 42 |

Largest Python files:

| Lines | File |
|---:|---|
| 4589 | `apps/siteconfig/models.py` |
| 3245 | `apps/accounts/views.py` |
| 2910 | `apps/schools/super_views.py` |
| 2552 | `apps/evals/views.py` |
| 2487 | `apps/siteconfig/admin.py` |
| 2461 | `apps/finance/models.py` |
| 2420 | `apps/portal/views.py` |
| 2373 | `apps/finance/views.py` |
| 1948 | `apps/schools/marketing_views.py` |
| 1847 | `apps/api/views_v1.py` |

Largest HTML templates excluding debug artifacts:

| Lines | File |
|---:|---|
| 1781 | `templates/parent/dashboard.html` |
| 1565 | `templates/portal_base.html` |
| 808 | `templates/components/ai_copilot.html` |
| 783 | `templates/components/global_search.html` |

Code smell counters from repo-wide grep:

| Pattern | Count |
|---|---:|
| `SiteSettings.get_solo(` | 218 |
| `except Exception` | 945 |
| `TODO/FIXME/TBD` | 23 |

## Test Harness Reality

Verified directly during this review:

- `python manage.py check` -> pass
- `python manage.py test apps.tenancy.tests.test_tenant_context_middleware -v 2` -> pass
- `python manage.py test apps.accounts.tests.test_security_export_mfa.SecurityExportMfaTests.test_user_has_mfa_accepts_passkey -v 2 --keepdb` -> pass
- `python manage.py test apps.accounts.tests.test_security_export_mfa.SecurityExportMfaTests.test_security_export_allows_passkey_only_user -v 2 --keepdb` -> pass
- `python manage.py test apps.api.tests.test_search_api_tenant_scope -v 2 --keepdb` -> pass

Structural test harness issues:

- `pytest-django` is missing.
- raw `pytest` collection is broken for normal developer use.
- the Django runner pays a large migration tax for even single-test executions.

## Database Maturity Snapshot

Marketplace and registry counts collected with `python manage.py shell -c ...`:

| Metric | Count |
|---|---:|
| publishers | 1 |
| marketplace apps | 4 |
| marketplace listings | 4 |
| approved listings | 4 |
| marketplace reviews | 0 |
| installations | 0 |
| blueprint packs | 15 |
| policy bundles | 10 |
| tenant blueprints | 0 |
| workflow packs | 7 |
| dashboard packs | 6 |
| countries | 249 |
| education levels | 3 |
| education system types | 10 |
| currencies | 259 |
| institution types | 0 |
| document types | 9 |
| fee categories | 8 |
| grade scales | 5 |
| migration runs | 0 |
| rollback-ready migration runs | 0 |

## Working Tree Note

The repository was already dirty before review changes. Existing user changes were left intact. This review added only targeted fixes and focused tests, then wrote the audit outputs in `docs/reviews/runmycampus_full_codebase_2026-03-08/`.
