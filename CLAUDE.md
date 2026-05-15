# CLAUDE.md — RunMyCampus engineering guide for Claude Code

This file is read by Claude Code at session start. Keep it short, durable, and load-bearing.

## What this codebase is

RunMyCampus is a multi-tenant SaaS school management platform. **Active code lives in `beta/school-management-system/`** — the `Live Code/` folder at the workspace root is empty and not in use. "The platform" includes:

- `runmycampus.com` — public marketing surface (cream / editorial / Source Serif 4)
- `manager.runmycampus.com` — control plane for super-admin / operator workflows (dark)
- Tenant subdomains — portal / backend / teacher / parent / student / studio_os shells (indigo + emerald + Inter, recessive so tenant brand wins)

Nothing about the platform is "off the table" — marketing, control plane, and tenant surfaces are all in scope. Each has its own design language but all must be world-class.

## Engineering best-practices for "big jobs"

Heavy workflows (large refactors, multi-template polish waves, platform-wide sweeps, end-to-end feature builds) are highly dependent on how the Claude Code session is set up. Protect them by following these three practices:

### 1. Clear session pollution before massive refactors

If a session is already long or carrying unresolved errors, run `/clear` *before* starting a heavy run. This wipes stale conversational history and maximizes the remaining token context available for raw code generation. Don't `/clear` mid-task — but at the start of a fresh big job in a polluted context, clearing first is the right move.

### 2. Isolate and scope explicitly

Don't point Claude Code at the entire monorepo when the task is bounded. Use explicit directory targets so the model's focus stays narrow:

- **Routing work:** `apps/<app>/urls.py` + `config/urls.py` — not the whole tree.
- **Theme / token work:** `static/css/design-tokens.css` first, then the surface shell.
- **Marketing surface:** `templates/marketing/` + `static/marketing/` + `apps/schools/marketing_views*.py`.
- **Cascade work (tenant config):** `apps/platform_runtime/models.py` + first-class resolver + `apps/siteconfig/`.
- **Exploration:** use `Grep` / `Glob` with `path=` set to the narrow subtree; reserve open-ended scans for the Explore subagent with breadth specified.

### 3. Pre-seed configurations before initiating the run

Confirm the precondition state before a heavy structural change:

- `CLAUDE.md` (this file) is up to date.
- `static/css/design-tokens.css` is the canonical foundation — semantic surface tokens (`--surface-bg/canvas/elevated/popover`, `--text-*`, `--hairline`, `--elev-1/2/3`, `--material-blur`) are defined there, **never duplicated** in per-shell stylesheets.
- For tenant-configurable values, the **cascade lands first**: `RuntimeDefaults` typed column → migration → `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES` tuple → `EXACT_FIELD_OWNERS` map → `siteconfig.models.SiteSettings` brand_payload tuple → context processor (`apps/siteconfig/context_processors.py`) → meta-tag bridge (`templates/partials/rmc_theme_meta.html`) → CSS custom property on `<html>` (set by `static/js/theme-preference-bootstrap.js`) → CSS rule that consumes it.
- Template adoption work happens **after** the underlying primitives are settled — never alongside.

## Non-negotiable directives

These rules are durable user instructions. Don't relitigate them per-task.

### No hardcoding

Nothing on the platform may be hardcoded. Every value routes through the 7-layer configurability contract (tenant `SiteSettings` → env var → user prefs → i18n → feature flag → DB fixture → platform constant). When in doubt, push the value up the cascade. Inline hex literals, magic numbers, and role strings are all in scope for the no-hardcoding rule.

### Apple-tier polish, world-class delivery

Nothing is assumed. Luxury / premium aesthetic is the bar. The semantic token system + the `.rmc-*` component grammar (data-table, empty, skeleton, cmdk, section-nav, segmented, sheet, kbd-cheatsheet, metric-ticker, page-progress, bottom-sheet, etc.) is the canonical foundation — extend it, don't fork it.

### Clean up after yourself

Removed code does not leave behind retired `// removed` comments, dead `_unused` vars, unused exports, or orphan CSS rules. Find dead callers via grep before deleting; if zero references confirmed, delete cleanly and add one retirement note in `docs/CSS_RETIREMENT_DOCKET.md` (the SOT for that work).

### Surface scope violations early

If a request would silently widen scope (e.g. "sweep dashboards" naturally implicates 100+ templates), name the breadth and the strategic subset *before* sweeping. The user values progress over exhaustive coverage, but only if the trade-off is visible.

## Sources of truth

- **CSS retirement audit + every polish wave (v2.0 → current):** `docs/CSS_RETIREMENT_DOCKET.md`
- **Tenant config cascade pattern:** `apps/platform_runtime/runtime_defaults_first_class.py` + `apps/siteconfig/domain_ownership.py`
- **Configurability contract (7-layer decision tree):** referenced in `docs/CSS_RETIREMENT_DOCKET.md`; details in memory.
- **Service worker version:** `static/js/service-worker.js` — bump on every wave that ships new CSS/JS, so cache invalidates cleanly after deploy.
- **AI gateway access (app code):** `services/ai_helpers.py` — `invoke_with_request`, `normalize_gateway_metadata`, `record_feedback`. App code under `apps/` MUST NOT import `services.ai_gateway` directly. Allowlisted infrastructure exceptions: `apps/portal/ai_provider.py`, `apps/portal/views_ai_gateway.py`, `apps/migration_cloud/ai_bridge.py`, `apps/platform_runtime/ai_providers.py`, `apps/siteconfig/management/commands/aggregate_ai_metrics.py`. Enforced by `scripts/scan_ai_gateway_boundary.py` (CI baseline 0).
- **Sentry SDK access:** `apps/observability/tracing.py` — `start_named_transaction`, `set_transaction_status`, `finish_transaction`, `trace_view`, `set_tags`. App code MUST NOT import `sentry_sdk` directly outside `apps/observability/`. Enforced by `scripts/scan_sentry_boundary.py` (CI baseline 0).

## Architectural CI gates (self-enforcing rules)

AST-based scanners + CI workflows enforce platform contracts on every PR. Update a baseline ONLY when intentionally removing a violation; never to silence a new one.

| Scanner | Baseline | Workflow | Rule |
|---|---|---|---|
| `scan_tenant_queryset_safety.py` | 734 (v2.48+L1a; was 742 at v2.47 — the 8 sites in `scheduling_solver.py` (2), `accounts/permissions.py` (5), `feedback/services.py` (1) are now per-call-site annotated rather than absorbed into baseline) | `tenant-isolation-scan.yml` | Tenant-scoped models need `school=` / `school_id=` / `school__isnull=` kwargs on `.filter/.get/.all/.update/.delete`. Mark safe cross-tenant queries with `# tenant-isolation-allow: <reason>`. |
| `scan_ai_gateway_boundary.py` | 0 | `architectural-boundaries.yml` | App code routes AI through `services.ai_helpers`, not `services.ai_gateway` directly. |
| `scan_sentry_boundary.py` | 0 | `architectural-boundaries.yml` | `sentry_sdk` is fenced inside `apps/observability/`. |
| `scan_print_statements.py` | 0 | `architectural-boundaries.yml` | Use `logging`, not `print()`, in `apps/` and `services/` outside management commands. |
| `scan_bare_except.py` | 0 | `architectural-boundaries.yml` | Always specify the exception type. Bare `except:` catches `KeyboardInterrupt` / `SystemExit`. |
| `scan_migration_model_imports.py` | 0 | `architectural-boundaries.yml` | Migrations use `apps.get_model("X", "Y")` for historical-state safety; do not import live models. |
| `scan_drf_schema_coverage.py` | 0 | `architectural-boundaries.yml` | DRF view classes in `apps/api/` carry `@extend_schema` (or `@extend_schema_view`). Mark intentional exclusions with `# drf-spectacular-allow: <reason>`. |
| `scan_role_strings.py` | 272 (v2.36; was 367 at v2.25 — `apps/accounts/permissions.py` added to `SOT_MODULES` since it owns the ROLE_RANK hierarchy registry) | `architectural-boundaries.yml` | Hardcoded role names (`ADMIN`/`TEACHER`/`PARENT`/`STUDENT`/`PROPRIETOR`) must reference `apps.platform_runtime.role_registry` or `User.Role` TextChoices. SOT modules: `role_registry.py`, `accounts/models.py`, `accounts/permissions.py`. Mark other allowed sites with `# role-string-allow: <reason>`. |
| `scan_assert_in_production.py` | 0 | `architectural-boundaries.yml` | `assert` is stripped under `python -O`; load-bearing checks must raise explicit exceptions. Mark type-narrowing-only allowed asserts with `# assert-allow: <reason>` on the same line. |
| `scan_magic_numbers.py` | **482** (v2.47; was ~1104 — Django CharField max_length conventions 120/128/255/256/512 added to `ALLOWED_LITERALS` alongside the existing RFC HTTP status codes) | `architectural-boundaries.yml` | Integer literals `abs(v) >= 100` outside `config/` / `*/constants.py` should be named constants. Drift-detection only. Mark allowed sites with `# magic-number-allow: <reason>`. |
| `scan_subprocess_shell_true.py` | 0 | `architectural-boundaries.yml` | `subprocess.*(shell=True)` and `os.system(...)` are forbidden (command injection). Mark allowed sites with `# shell-true-allow: <reason>`. |
| `audit_template_render_safety.py` | 0 | `architectural-boundaries.yml` | Templates must not leak content. Catches: multi-line `{# … #}` (Django supports single-line only), orphan template tokens, unbalanced `{% if/for/block/with/comment/verbatim/… %}`, missing `{% include %}`/`{% extends %}` targets, missing `{% static %}` files. Zero-tolerance gate. |
| `scan_inline_style_off_token.py` | **0** (was 155 at v2.26 introduction; v2.27 mechanical retrofit brought it to zero) | `architectural-boundaries.yml` | Apple HIG quiet-luxury: template `style="..."` attributes must not bypass the token system. Catches: inline `font-size:` literals (use `var(--type-size-*)` or `.rmc-type-*`), inline color/background/border-color hex/rgb (use `var(--*)` so tenant brand wins), `transition:` with raw `cubic-bezier(...)` (use `var(--ease-*)` / `var(--motion-*)`). **Zero-tolerance gate** post-v2.27. Mark exceptions with `<!-- inline-style-allow: <reason> -->` or `inline-style-allow:` inside the style. |
| `scan_undefined_css_classes.py` | **0** (was 212 at v2.26 introduction; v2.35 class-grammar completion defined every flagged class in `static/css/rmc-class-grammar.css`) | `architectural-boundaries.yml` | Catches **project-prefixed** CSS class names (`rmc-`, `cp-`, `mkt-`, `portal-`, `ccc-`, `setup-studio-`, `content-max-`, etc.) referenced in templates but never defined in any CSS file under `static/css/` or `static/marketing/css/`. This is the class of bug that hid `content-max-960` (referenced 25x, never defined → silent empty-column on every manager page). Tailwind / Bootstrap / icon-font utilities are allowlisted. **Zero-tolerance gate** post-v2.35. |
| `check_real_migration_drift.py` | n/a (filter, not baseline) | `architectural-boundaries.yml::real-migration-drift` | Wave L (v2.48+L1b). Wraps `makemigrations --dry-run` and classifies each proposed AlterField op as either **cosmetic** (F2 callable-identity drift on known fields: `upload_to=` / `default=` callables — currency / file / photo / reference / timezone / role) or **real** (any other AlterField, AddField, RemoveField, CreateModel, etc.). Exits 1 only on real drift, restoring `makemigrations --check` as a useful CI gate after F2's inlining made it noisy. The ~38 cosmetic AlterFields from F2 are surfaced informationally but ignored for exit-code purposes. |

## Migration / deploy checklist for a wave

When closing out a polish or feature wave:

1. All new files added (templates / partials / static JS/CSS).
2. All 4 dashboard shells + the marketing shell wired to load new shell-level scripts (`portal_base.html`, `base.html`, `control_plane_skeleton.html`, `admin/base_site.html`, `marketing/base_marketing.html`).
3. Service worker `CACHE_VERSION` bumped to `sms-vX.Y.Z-<slug>-<YYYY-MM-DD>`.
4. `docs/CSS_RETIREMENT_DOCKET.md` updated with the wave's `## YYYY-MM-DD — vX.Y …` section + "What landed" table + "Deploy" subsection.
5. Memory updated: single-line index entry in `MEMORY.md` + standalone memory file `project_<wave_slug>.md` for the audit trail.
6. Validate: Python files parse (`python -c "import ast; ast.parse(open(...).read())"`), JS files parse (`node -e "new Function(require('fs').readFileSync(...,'utf8'))"`), and zero broken `{% include %}` references for any deleted partials.
