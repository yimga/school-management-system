# De-Gilead / Local-First Audit — Pass 2 (2026-06-23)

**Mandate (owner):** "This platform was built for ONE school (Gilead, in Cameroon) then
generalized to a multi-tenant product. Ensure NOTHING is single-built or hardcoded for
Gilead/Cameroon — everything seeds from the tenant's country/region. Audit, then run a
prompt that addresses everything (multi-agents allowed)."

Pass 2 followed Pass 1 (see `project_tenant_100x_execution_2026_06_23` memory) and a
parallel local-first remediation (currency SoT, locale middleware, scale-driven grading,
compliance-region, term cap 4→12). This pass used a 4-agent read-only audit (backend
defaults / Gilead identity / templates / infra) then shipped the **safe, backward-compatible**
fixes and documented the rest for a supervised pass.

## Verdict

The localization **infrastructure is sound** — `LEXICON_REGISTRY` + `terminology_service`
cascade, `RegionConfig`/`EducationSystemProfile` country packs, `School.resolve_currency()`
local-first cascade, `academics/exam_boards.py` country→board SoT all resolve per-tenant with
**no Cameroon fallback** in production code. The remaining work is **adoption + a few baked
defaults**, not structural holes.

## Shipped this pass (commit `1fe40107b`)

| Area | File:line | Fix |
|---|---|---|
| Compliance default | `platform_runtime/geos_lane2_core_loop.py:121` | `country_code or "CM"` + `"XAF"` → tenant `country_code` + `School.resolve_currency()` |
| Currency helper | `evals/grading.py:391` | `format_currency(currency_code="XAF")` → platform default (no non-test callers) |
| Lexicon | `siteconfig/lexicon_catalog.py` | New `sequence` key (Cameroon CA term) |
| Templates | `reports/term_report.html`, `teacher/marks_entry.html` | hardcoded "Sequence 1/2" → `{% term "sequence" %}` (English default preserved) |
| Templates | `reports/annual_report.html:110` | hardcoded "Principal" → `{% term "principal" %}` |
| CI gate | `scripts/lint_gilead_residue.py` | pattern `gilead` → `gilead|small soppo`; reworded 2 prior "De-Gilead" comments the gate was already (silently) flagging |
| Dashboard scale (`561f277fc`) | `accounts/views.py` + `backend_dashboard.html` | top-performer/at-risk `/20` + the `>= 10` at-risk pass threshold were Cameroon-/20-baked; now derived from `resolve_school_score_scale()` (denominator = scale max, pass = half scale). `/20` school unchanged; `/100`/GPA correct. Defensive `grading_scale_max=20` on the no-data path |
| Role gate (`561f277fc`) | `accounts/auth_backends_role_perms.py` | greened the `role-strings --compare` gate (was red on a peer-added admin-like role set) via two `# role-string-allow` markers — comment-only |

RBAC per-school OWNER role also shipped this session (commit `936d5ebd4`) — the deferred
Phase-0 item; see `project_rbac_school_owner_2026_06_23` memory.

## Deferred — needs a supervised pass (exact targets + fix)

### P0 (non-/20 tenants are actively wrong) — grade-scale plumbed into context — ✅ CLOSED
- `templates/accounts/backend_dashboard.html` — **SHIPPED `561f277fc`** (see above).
- `templates/teacher/marks_entry.html` — **SHIPPED `8f618c080`** (supervised pass, after the
  peer's OCR-path grade-scale work landed as `a94321b54`). All six mark inputs (seq1/seq2/exam/
  mock/practical + the OCR-correction field) now bind `max="{{ max_score|default:20 }}"`; the
  view resolves `resolve_school_score_scale(school)` and normalizes it via the new
  `_normalized_scale_max` helper (20→"20", 4.0→"4", 7.5→"7.5"), so a /100, /4 or /10 tenant can
  enter valid marks. Cameroon `score_scale=20` → `max="20"` (back-compat, unchanged). No
  migration. No-DB tests in `apps/evals/tests/test_marks_entry_scale.py`; the resolver itself is
  DB-tested in `test_grading_provisioning.py`.

### P1 — founding-tenant seed history + structural binding
- `schools/migrations/0012`, `0013`, `customers/migrations/0003` — seed a Gilead-specific
  founding tenant. **DO NOT edit applied migrations.** Instead parametrize the seed *command*
  via env (`DEFAULT_TENANT_SLUG` / `DEFAULT_TENANT_NAME`) and/or DEBUG-gate it; leave history
  intact.
- `schools/models.py` — **SHIPPED (on main):** `School.save()` auto-links `default_region` via `find_region_for_country(country_code)` when unset (read-only, never raises). **Remaining:** backfill migration for legacy rows + require country at signup (supervised).

### P2 — adoption breadth + gates
- Add `bursar` / `proprietor` lexicon keys when the templates that need them are localized.
- `templates/siteconfig/partials/reportcard_style_preview_body.html` — bilingual FR/EN
  fallback labels. **Verify intent first** (this is the *Cameroon* report-style preview, so
  bilingual may be correct) before changing.

## Recommended NEW CI gates (close the class, not just instances)

1. **Terminology-adoption linter** — flag hardcoded canonical terms (Student/Teacher/Class/
   Sequence/Principal…) in templates that render for all tenants, outside a `{% term %}` tag.
   Baseline at the current count, drive to 0 over time (drift-detector, like the magic-number
   gate). ~474 templates currently hardcode at least one canonical term.
2. **Exam-board-filtering gate** — flag any view/template iterating `Board.choices` without
   routing through `academics/exam_boards.allowed_board_choices(country_code)`.

## How to run the supervised pass (prompt)

> Take the P0 grade-scale items above. For `marks_entry`: find the marks-entry view, resolve
> the school's grading scale (the score_scale / GRADING_SCALE_BANDS the parallel local-first
> work added), compute `max_score` (default 20 for back-compat), pass it to context, and bind
> the four `max="20"` inputs to it. Do the same denominator work for `backend_dashboard`'s
> `/20` badge. Add the two CI gates above at their current baselines. Verify-first, write DB
> tests, run on a PRIVATE test DB (`DJANGO_TEST_DB_FILE=…`), browser-check grade entry before
> shipping. Do NOT edit applied seed migrations — parametrize the seed command instead.

## Consolidation closeout (2026-06-23)

**Merge posture:** Local merge `b8c0ea798` (consolidate local main into origin/main) is fully
superseded on **`origin/main`** by `c9172369a` (fleet globe + threshold-era marketing + tenant
dashboard waves) and `939f2fe20` (student 100X role home + `student_results_visibility` policy).
HEAD matches remote; no rebase in flight.

**Branch assessment (June 2026 + legacy):** All ten `origin/*2026-06-*` branches and eight
legacy feature branches (`agentic-phase3-clean`, `asgi-streaming`, `backend_vs_frontend`,
`feat/dashboard-packs-revival`, `feature/dashboard-templates`, `feature/multi-tenant-schools`,
`faq_kb`, `Testing`) report **0 commits ahead of `main`** — fully absorbed or abandoned.
**Deliberately not resurrecting:** pre-2026 safety branches (`safety/pre-main-*`), codex
planning forks, and stale CI fix branches — historical only.

**Gap analysis (this pass):**

| Item | Status |
|---|---|
| P0 grade-scale (marks_entry + backend dashboard) | **CLOSED** (`4792b5e9b`, `561f277fc`, `8f618c080`) |
| Lexicon adoption tests | **GREEN** (`033139d7a`, `test_lexicon_local_first`) |
| Student results visibility | **SHIPPED** (`939f2fe20`) |
| Marketing ascension media + revolution lab | **SHIPPED** (this commit) |
| Marketing enhanced CSS budget | Reconciled **350000 → 425000** B (418174 B actual) |
| P1 founding-tenant seed migrations | **PARTIAL → command shipped** — `ensure_founding_tenant` + `founding_tenant_defaults.py` (`DEFAULT_TENANT_*` env, default `demo-school`); migrations 0012/0013 frozen. `School.save()` auto-region still deferred. |
| P2 terminology-adoption linter + exam-board gate | **SHIPPED** — `lint_terminology_adoption.py` baseline **785** (drift); `scan_exam_board_filtering.py` baseline **0** (zero-tolerance); CI jobs in `architectural-boundaries.yml`. |

**Proof:** `manage.py check` 0 issues; `makemigrations --check` clean; consolidation suites
45+25 tests OK; `lint_gilead_residue` 0; `scan_role_strings --compare` OK;
`INTERACTION_INTEGRITY_PASS`; `verify:marketing` OK; dead hrefs **0**.
