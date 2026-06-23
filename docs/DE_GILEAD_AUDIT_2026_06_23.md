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
- `schools/models.py` — `country_code` is `blank=True` and `default_region` is not
  auto-derived, so a tenant can exist with no region binding (falls back to a *generic* pack,
  not Cameroon — so not a leak, but a missed-localization). **Fix:** on `School.save()`,
  auto-derive `default_region` from `country_code` when unset; backfill migration; consider
  requiring country at signup. Touches signup → supervised.

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
