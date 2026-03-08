# Cleanup and Performance

Date: 2026-03-08

## Summary

Performance and cleanup issues are structural, not cosmetic. The repo is carrying oversized modules, a broad asset stack, heavy exception swallowing, and an expensive test setup path.

## 1. File-Size Hotspots

Largest Python hotspots:

- `apps/siteconfig/models.py` - 4589 lines
- `apps/accounts/views.py` - 3245 lines
- `apps/schools/super_views.py` - 2910 lines
- `apps/evals/views.py` - 2552 lines
- `apps/siteconfig/admin.py` - 2487 lines

Largest template hotspots:

- `templates/parent/dashboard.html` - 1781 lines
- `templates/portal_base.html` - 1565 lines
- `templates/components/ai_copilot.html` - 808 lines
- `templates/components/global_search.html` - 783 lines

Implication:

- the codebase has crossed the threshold where large-file refactors are no longer optional hygiene; they are a prerequisite for reliable change velocity

## 2. Asset Stack Bloat

Observed:

- `templates/base.html:80-99` imports a long fixed list of CSS files before page-specific needs are known
- theming is layered across design tokens, unified systems, responsive rules, high-contrast rules, dark theme rules, visibility guards, and platform polish assets

Impact:

- higher baseline payload
- more CSS ordering risk
- harder diagnosis of styling regressions

## 3. Exception Swallowing

Repo-wide count:

- `except Exception` occurrences: 945

Interpretation:

- this is not defensive coding at the margins
- this is a systemic observability and correctness risk

Cleanup rule:

- replace broad exception swallowing in runtime, middleware, and policy paths with explicit exceptions plus structured logging

## 4. Singleton Fanout

Repo-wide count:

- `SiteSettings.get_solo(` occurrences: 218

Impact:

- the repo keeps falling back to global singleton state even when a multi-tenant runtime abstraction exists
- this is both a correctness risk and a scaling risk

## 5. Test Harness Cost

Observed:

- `python manage.py check` is healthy
- raw `pytest` collection is not healthy because `pytest-django` is missing
- single-test Django runs require heavy migration setup and often spend roughly three to four minutes before running one assertion

Impact:

- developers are discouraged from writing small focused tests
- review loops become slower than the size of the targeted change would justify

Required action:

1. add `pytest-django`
2. define repo-level `pytest.ini`
3. create a fast-path test profile for unit and middleware tests
4. keep a smaller migration/test bootstrap path where possible

## 6. Cleanup Targets That Should Be First

1. split `apps/accounts/views.py`
2. split `apps/siteconfig/models.py`
3. split `apps/portal/views.py`
4. collapse duplicate sidebar ownership
5. reduce base template CSS imports
6. remove roadmap endpoints from the main API surface
7. cut broad `except Exception` from middleware and runtime code first

## Performance/Cleanup Verdict

The repo does not mainly need micro-optimization. It needs ownership reduction:

- fewer giant files
- fewer global fallbacks
- fewer CSS layers
- fewer catch-all exceptions
- a real fast test path
