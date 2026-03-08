# Logic and Hardcoding

Date: 2026-03-08

## Summary

Hardcoding is still a system-level trait, not a cleanup tail. The repo does contain runtime and policy abstractions, but hardcoded behavior still shapes onboarding, navigation, default identity, page theming, and approval behavior.

## Measured Indicators

Repo-wide grep counts at review time:

| Signal | Count |
|---|---:|
| `SiteSettings.get_solo(` | 218 |
| `except Exception` | 945 |
| `TODO/FIXME/TBD` | 23 |

Interpretation:

- global singleton configuration still leaks into many runtime paths
- broad exception swallowing is being used as a control-flow tool
- technical debt is not confined to a small set of isolated files

## Hardcoded Behavior Inventory

### Navigation

- `templates/partials/portal_sidebar.html:66-220` contains large role-specific fallback trees.
- `templates/partials/portal_sidebar.html:252-283` adds additional feature-driven fallback sections after the main tree.
- `apps/siteconfig/portal_sidebar_items.py:208-366` constructs most portal nav items in Python with role and permission branching.

Why it matters:

- navigation is product policy, not presentation detail
- hardcoded nav multiplies drift between runtime claims and actual user experience

### Admissions and Approval Defaults

- `apps/policies/resolver.py:221-230` falls back to `AUTO_OR_MANUAL`, `FULL`, and school code `GIL`
- `apps/policies/resolver.py:266-271` falls back to `["DEAN", "HOD"]`

Why it matters:

- institution identity and role governance are being encoded as code defaults
- these are not safe universal assumptions for a multi-country platform

### Onboarding Geography

- `templates/schools/onboard_wizard.html:17-23` hardcodes Cameroon, Canada, United States, and Nigeria

Why it matters:

- onboarding should be registry-driven if the platform claims world-engine and blueprint support

### Base Shell Theme and Page Logic

- `templates/base.html:41-49` hardcodes page detection by URL fragments
- `templates/base.html:80-99` imports a long fixed asset stack
- `templates/base.html:215` defaults typography to `Inter, system-ui, sans-serif`
- `templates/base.html:230` hardcodes a global gradient

Why it matters:

- the shell still owns visual and routing behavior that should be data-driven or page-family-driven

### School Defaults

- `apps/schools/models.py:117-121` constrains `sub_system` to `FR`, `EN`, `INT`
- `apps/schools/models.py:121` defaults timezone to `Africa/Douala`

Why it matters:

- defaults reveal a strong historical product center
- those defaults are acceptable as bootstrap seeds, but not as invisible platform assumptions

## Logic Drift Patterns

### Runtime plus fallback instead of runtime instead of fallback

The repo frequently introduces a runtime abstraction, then keeps the old path as a silent fallback. The practical result is that the old path remains dominant because it is simpler and better understood by future contributors.

Examples:

- `apps/policies/resolver.py`
- `templates/partials/portal_sidebar.html`
- `apps/siteconfig/portal_sidebar_items.py`
- `templates/base.html`

### Exception swallowing as compatibility glue

The scale of `except Exception` usage indicates a codebase preference for "do not break the request" over "make ownership and failure explicit." That makes it much harder to know whether runtime or policy layers are truly working.

## What Should Own These Behaviors Instead

| Current owner | Better owner |
|---|---|
| template fallback nav branches | nav registry plus runtime visibility rules |
| hardcoded admissions defaults | policy bootstrap data and registry seed data |
| hardcoded onboarding countries | country and education-system registries |
| base shell route detection | page-family metadata or explicit view context |
| school-code and grade-role fallbacks | tenant blueprint / policy pack defaults |

## Required Rule Change

Use this engineering rule going forward:

"No new tenant behavior may be introduced through template branching, direct `School.settings` reads, or `SiteSettings.get_solo()` in request-time module logic unless the same behavior is first expressed in policy/runtime."

Without that rule, the platform will keep growing sideways instead of consolidating.
