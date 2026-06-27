# Reference-Integrity CI Gate Family

**Audience:** operators (what to run / what a red gate means) + engineers (how each
gate works, how to fix or excuse a finding).

**What it is:** a family of static + runtime CI gates that seal one bug class —
**a literal string reference that resolves to nothing at runtime.** Across the
platform, code names things by string: an import path, a `get_model("app","M")`
label, a `reverse("name")`, a `render(request, "x.html")` template, a
`settings.NAME`, an ORM `.only("field")` / `.select_related("rel")`, a
`{% static 'a.css' %}`. Each of those is invisible to `manage.py check` and to a
naive grep, but at runtime a typo or a rename surfaces as an uncaught
`ImportError` / `LookupError` / `NoReverseMatch` / `TemplateDoesNotExist` /
`AttributeError` / `FieldError` 500 — or, worse, gets swallowed by a broad
`except` so a counter pins to 0/empty forever and nobody notices.

Every member resolves with **ground truth** (the live registry / loader /
resolver / `_meta`, or the filesystem+AST for the deps-free one), so it has zero
false positives from incomplete static knowledge, and every member is a
**zero-tolerance gate at baseline 0**.

> This doc is the subsystem reference. The per-gate one-line rules also live in
> the scanner table in [`../CLAUDE.md`](../CLAUDE.md); the §12 completion-gate
> index lives in [`VERIFICATION_GATES_INDEX.md`](VERIFICATION_GATES_INDEX.md).
> This file is the place that explains the family as one system.

---

## 1. The eight seals + the meta-gate

| # | Gate (`scripts/…`) | Reference sealed | Runtime failure if broken | Needs Django? | Workflow |
|---|---|---|---|---|---|
| 1 | `scan_import_reference_integrity.py` | `from apps.X import Y`, `import apps.X`, relative imports, `importlib.import_module("apps…")` | `ImportError` 500 / swallowed | No (AST+FS) | `architectural-boundaries.yml` |
| 2 | `verify_get_model_integrity.py` | `get_model("app","Model")`, `ContentType.objects.get(app_label=,model=)` | `LookupError` / silent `DoesNotExist` | Yes | `ci.yml::django-tests` |
| 3 | `verify_url_name_integrity.py` | `reverse("n")`, `reverse_lazy("n")`, `{% url "n" %}` | `NoReverseMatch` 500 / dead link | Yes | `ci.yml::django-tests` |
| 4 | `verify_template_reference_integrity.py` | `render` / `render_to_string` / `TemplateResponse` / `get_template` / `select_template` / `template_name[s]` | `TemplateDoesNotExist` 500 | Yes | `ci.yml::django-tests` |
| 5 | `verify_static_reference_integrity.py` | `{% static 'path' %}` | silent browser 404 (broken CSS/JS/img) | Yes | `ci.yml::django-tests` |
| 6 | `verify_settings_key_integrity.py` | `settings.NAME`, `getattr(settings,"NAME")` no-default | `AttributeError` 500 / dead branch | Yes | `ci.yml::django-tests` |
| 7 | `verify_field_reference_integrity.py` | `.order_by/.values/.values_list/.only/.defer/.distinct("field")` | `FieldError` 500 / wrong query | Yes | `ci.yml::django-tests` |
| 8 | `verify_relation_path_integrity.py` | `.select_related/.prefetch_related("rel")` | `FieldError` 500 | Yes | `ci.yml::django-tests` |
| — | `verify_ci_gate_wiring.py` (**meta-gate**) | the gates themselves | a gate silently un-enforced | No (text scan) | `architectural-boundaries.yml` |

Each docstring records its own family position and rationale:
`scan_import_reference_integrity.py:2-16`, `verify_get_model_integrity.py:2-19`,
`verify_url_name_integrity.py:2-20`, `verify_template_reference_integrity.py:2-25`,
`verify_static_reference_integrity.py:2-26`, `verify_settings_key_integrity.py:2-21`,
`verify_field_reference_integrity.py:2-17`, `verify_relation_path_integrity.py:2-29`.

### Why split static vs runtime

- The **static** member (#1) resolves `apps.*` imports against the filesystem +
  AST with **no Django/runtime dependency**, so it runs in the deps-free
  `architectural-boundaries.yml` boundary job
  (`scan_import_reference_integrity.py:13-15`).
- The **runtime** members (#2–#8) need the live Django registry / URL resolver /
  template loader / `_meta` to be ground truth, so they run in
  `ci.yml::django-tests` after `python manage.py check`
  (`.github/workflows/ci.yml:22-41`).
- The static gate deliberately **cannot** resolve dynamic model lookups — a model
  class can be physically defined in a `models_*.py` (so a static scan "finds"
  it) yet be unregistered (no migration / not in any installed app), so
  `get_model` raises `LookupError` at runtime. #2 closes exactly that gap with
  the live registry (`verify_get_model_integrity.py:4-19`).

---

## 2. Operator runbook

### Run the whole family locally

The runtime members need Django installed + `manage.py check` passing. The static
member and the meta-gate are stdlib-only and run anywhere.

```bash
# Stdlib-only (no Django needed) — runs in the deps-free boundary job
python scripts/scan_import_reference_integrity.py --compare
python scripts/verify_ci_gate_wiring.py

# Runtime members (need Django; run from a deps-installed env)
python scripts/verify_get_model_integrity.py        --compare
python scripts/verify_url_name_integrity.py          --compare
python scripts/verify_template_reference_integrity.py --compare
python scripts/verify_static_reference_integrity.py  --compare
python scripts/verify_settings_key_integrity.py      --compare
python scripts/verify_field_reference_integrity.py   --compare
python scripts/verify_relation_path_integrity.py     --compare
```

### Flag contract (uniform across the family)

Every member uses the same three-mode CLI (e.g.
`verify_url_name_integrity.py:352-367`):

- **no flag** → recompute and **overwrite** the baseline JSON (only do this when
  intentionally accepting a new state). For #1 the no-flag run is non-failing.
- `--compare` → **CI mode**: print the summary and exit `1` if there are findings
  beyond baseline 0 (this is what the workflows invoke).
- `--json` → emit the machine payload (count + findings + rule) for tooling.

### What a red gate means + first move

| Symptom in CI | First move |
|---|---|
| `…integrity: N unresolved …` | A literal reference now resolves to nothing. **Fix the reference** (correct the import / name / path / field). Do **not** re-baseline to silence it. |
| meta-gate: `MISSING: scripts/X.py is in NO workflow` | A gate's invocation vanished from every workflow file. **Re-wire it** in `ci.yml` / `architectural-boundaries.yml`, or — if removal is intentional — drop it from `REQUIRED_GATES` (`verify_ci_gate_wiring.py:42-68`), a reviewed change. |

### Baselines

All eight baselines are `var/security-audit-baseline-<gate>.json`, each carrying
`{finding_count, findings, generated_at, rule}` — all currently
**`finding_count: 0`** (e.g. `verify_url_name_integrity.py:72`,
`scan_import_reference_integrity.py:60`, `verify_get_model_integrity.py:58`). The
documented-vs-JSON drift between these files and the CLAUDE.md table is itself
guarded by `check_documented_baselines.py`.

---

## 3. The meta-gate (why the gates can't quietly die)

The gates protect the code, but nothing protected the **gates themselves** from
being silently un-enforced. A peer edit to `ci.yml` once dropped the
`verify_url_name_integrity` step entirely: the verifier still existed, its
baseline still said 0, its tests still passed — but it no longer **ran** on any
PR, so a new `NoReverseMatch` could ship uncaught
(`verify_ci_gate_wiring.py:4-10`).

`verify_ci_gate_wiring.py` closes that meta-loophole. It holds a SOT
`REQUIRED_GATES` registry (`verify_ci_gate_wiring.py:42-68`) and asserts each
gate's `scripts/<gate>.py` invocation appears in **at least one**
`.github/workflows/*.yml` file (`verify_ci_gate_wiring.py:84-91`). It is a
pure-text scan (no YAML parse, no Django) so it runs in the deps-free boundary
job alongside the static scanners it protects (`verify_ci_gate_wiring.py:17-19`).
"Wired in ANY workflow" is the contract — a gate may legitimately move between
workflow files, but it must never vanish from all of them
(`verify_ci_gate_wiring.py:19-22`). The boundary workflow already triggers on
edits to `.github/workflows/*.yml`, so dropping a step re-runs this gate and
fails. As of this writing it checks **18 required gates** (live run:
`18 required gate(s) checked, 0 un-wired`); `REQUIRED_GATES` covers the whole
reference-integrity family plus several other zero-tolerance gates
(`scan_money_float`, `scan_tenant_queryset_safety`,
`verify_offline_capability_implementation`, the grading-scale registry coverage
gate, etc.) (`verify_ci_gate_wiring.py:42-68`).

---

## 4. How each runtime member avoids false positives

A zero-tolerance gate is only useful if a clean tree stays green. Each member is
engineered around its specific false-positive trap:

- **URL names (host-split trap).** RunMyCampus is host-split across multiple
  urlconfs (`config.urls` / `public_urls` / `tenant_urls` / `manager_urls` /
  `api_urls` / `docs_urls`), and the manager host is routed by middleware, not a
  settings constant. `get_resolver()` only sees `ROOT_URLCONF`, so a naive
  checker flags every name registered solely in a host-split urlconf. The fix
  unions registered names across **every** `config/*urls*.py` module (auto-
  discovered) + settings `*_URLCONF` + `django.contrib.admin.autodiscover()`,
  then for any miss falls back to classifying Django's own `NoReverseMatch`
  message ("not a valid view function or pattern name" = finding, vs
  "pattern(s) tried" = valid-but-needs-args) (`verify_url_name_integrity.py:11-30`).
- **Templates (third-party trap).** Resolving against repo templates only would
  false-positive on `admin/base_site.html`, `rest_framework/api.html`, etc. #4
  asks Django's own loader (`get_template` / `select_template`), so installed-app
  templates resolve exactly as at runtime; `select_template`/list args use
  "any member resolves" semantics (`verify_template_reference_integrity.py:16-39`).
- **Static assets.** #5 asks `staticfiles.finders.find`, covering
  `STATICFILES_DIRS` **and** every installed app's `static/` (so `unfold/…`
  resolves); a directory-prefix literal that libraries like tesseract.js need
  resolves as a directory and passes (`verify_static_reference_integrity.py:20-39`).
- **Settings.** Ground truth is `hasattr` against the live `django.conf.settings`
  after `django.setup`; only UPPER_SNAKE **read** context counts (assignment
  targets skipped), and only in files that `from django.conf import settings`
  (`verify_settings_key_integrity.py:18-37`).
- **ORM field + relation gates (conservative-by-design).** Both are biased hard
  toward false-**negatives** so they never redden a clean tree: they check
  positional string args only, on a chain whose head is a directly-resolvable
  `<Model>.objects` that maps to **exactly one** registered model (0 / name-
  collision → skipped, not guessed); any chain with
  `annotate`/`alias`/`extra`/`raw`/`union`/`intersection`/`difference` is skipped
  (pseudo-fields); only the **first** `__` segment is checked so related-
  traversal / lookup tails never false-positive
  (`verify_field_reference_integrity.py:19-37`,
  `verify_relation_path_integrity.py:31-49`). The field gate deliberately
  **excludes** `select_related`/`prefetch_related` (relation, not scalar-field,
  resolution) — that is exactly the gap #8 was built to close
  (`verify_relation_path_integrity.py:5-12`).
- **Imports (over-collect symbols).** #1 over-collects symbols (walks the whole
  target tree) to bias toward false negatives; PEP-420 namespace packages,
  `from x import *` re-exports, and module-level `__getattr__` are treated as
  opaque so a symbol can't be "proven absent" wrongly
  (`scan_import_reference_integrity.py:38-45`).

---

## 5. Excusing an intentional reference

Every member accepts the **same two excuse forms**, so a genuinely dynamic /
optional / deferred reference does not need a code change to the gate:

1. **Guard with the matching `try/except`.** Each gate excuses a reference inside
   a `try/except` that catches its own failure family — `ImportError` /
   `ModuleNotFoundError` (#1), `LookupError` (#2), `NoReverseMatch` (#3),
   `TemplateDoesNotExist` (#4), `AttributeError`/`ImproperlyConfigured` (#6),
   `FieldError`/`FieldDoesNotExist` (#7/#8) — or a broad `Exception` /
   `BaseException` / bare `except`, including a named exception-tuple alias that
   contains a guard exc. See the `_GUARD_EXC_NAMES` sets, e.g.
   `verify_get_model_integrity.py:61`, `verify_url_name_integrity.py:75`,
   `verify_settings_key_integrity.py` (`AttributeError`/`ImproperlyConfigured`).
2. **An inline allow-marker** on the reference line or the line directly above.
   Each gate has its own marker token (so reasons stay specific):

   | Gate | Marker | Source |
   |---|---|---|
   | imports | `# import-ref-allow: <reason>` | `scan_import_reference_integrity.py:62` |
   | get_model | `# get-model-allow: <reason>` | `verify_get_model_integrity.py:60` |
   | url-name | `# url-name-allow: <reason>` (also `{# url-name-allow #}` in templates) | `verify_url_name_integrity.py:74` |
   | template | `# template-ref-allow: <reason>` | `verify_template_reference_integrity.py:71` |
   | static | `{# static-ref-allow: <reason> #}` | `verify_static_reference_integrity.py:60` |
   | settings | `# settings-key-allow: <reason>` (also a same-line `hasattr` ternary / a `getattr` default) | `verify_settings_key_integrity.py:57` |
   | field | `# field-ref-allow: <reason>` | `verify_field_reference_integrity.py:58` |
   | relation | `# relation-path-allow: <reason>` | `verify_relation_path_integrity.py:73` |

In all members, **migrations and test files are skipped** (migrations have their
own historical-state gate; tests intentionally reference fixtures that may not be
registered).

---

## 6. Why this family exists — real bugs it caught at introduction

This is not a theoretical gate. Each runtime member's first `--compare` run on the
real tree caught latent production failures, recorded in the docstrings:

- **#2 get_model:** would have caught `apps/evals/import_services.py`
  `get_model("evals","GradeImportJob")` / `"GradeImportRowLog"` — defined only in
  the migration-less `evals/models_enhanced.py`, so unregistered →
  `LookupError` at runtime (`verify_get_model_integrity.py:9-14`).
- **#1 imports:** first run caught an unregistered duplicate
  `GenerateRegionalReportsCommand` importing a nonexistent
  `ReportCompilationService` (the real command lives in `reports/…`); retired
  (see CLAUDE.md scanner table, import-reference-integrity row).
- **#4 templates:** per the CLAUDE.md scanner-table row, caught **6 real broken
  references** on first run (4 live 500s incl. the routed `/finance/notifications/`
  page + the deadline-reminder email; 2 a grade-publication email pair), driving
  862 literal targets checked → 0 (see the template-reference-integrity row in
  [`../CLAUDE.md`](../CLAUDE.md); the gate's loophole rationale is in
  `verify_template_reference_integrity.py:12-25`).
- **#7 fields:** per the CLAUDE.md scanner-table row, caught **7 real latent
  `FieldError` 500s** (6 in `apps/analytics/ml/grade_prediction_features.py`
  `.only("seq1"/"seq2"/"exam")` — the real fields are `*_score`; 1 in
  `apps/academics/bulk_attendance.py` `StudentProfile.objects.only("external_id")`
  — no such field), all fixed → 0 (see the field-reference-integrity row in
  [`../CLAUDE.md`](../CLAUDE.md); the gate's loophole rationale is in
  `verify_field_reference_integrity.py:5-11`).
- **#8 relations:** caught **1 real latent `FieldError` 500** in the canonical
  `apps/reports/management/commands/generate_regional_reports.py` —
  `.select_related("component","subject")` when `evals.Evaluation` has neither
  (its relation is `subject_assignment` → `SubjectAssignment.subject`); fixed to
  `.select_related("subject_assignment__subject")`
  (`verify_relation_path_integrity.py:21-29`).
- **#3 url-name / #5 static / #6 settings:** introduced clean at 0 against large
  surfaces (per the CLAUDE.md scanner table: 3784 url references; 1520 static
  refs; 506 settings reads) — proving the host-split / installed-app /
  live-settings false-positive handling, while the gate stays armed against the
  next regression. (These per-introduction totals are recorded in the
  [`../CLAUDE.md`](../CLAUDE.md) scanner-table rows; the live "N checked" count is
  printed by each gate's summary line, e.g. `verify_url_name_integrity.py:318`,
  `verify_static_reference_integrity.py:187`, `verify_settings_key_integrity.py:262`.)

---

## 7. Adding a new member or new required gate

- **New reference shape inside an existing gate:** add the call shape to that
  gate's collector, keep the false-negative bias (skip anything you can't resolve
  to exactly one ground-truth target), and add a stdlib test under
  `scripts/tests/test_<gate>.py`. **Every** family member (all eight seals + the
  meta-gate) has a matching stdlib test file — `144 passed` across the nine files
  as of this writing (`scripts/tests/test_verify_field_reference_integrity.py`
  was the last to land, 38 cases covering each of the six `_FIELD_METHODS`,
  guard/marker excuses, and the `__`-segment / leading-`-` / `pk` / `?`
  normalisation). Bare-run to write the baseline, confirm `finding_count: 0`,
  then wire `--compare` into the right workflow.
- **A brand-new gate that must always run:** after wiring its `--compare` step
  into `ci.yml` or `architectural-boundaries.yml`, **add it to `REQUIRED_GATES`**
  in `verify_ci_gate_wiring.py:42-68` so the meta-gate guards it from silently
  falling out of CI.

---

## 8. Quick reference (paths)

- Verifiers: `scripts/scan_import_reference_integrity.py`,
  `scripts/verify_{get_model,url_name,template_reference,static_reference,settings_key,field_reference,relation_path}_integrity.py`,
  `scripts/verify_ci_gate_wiring.py`.
- Baselines: `var/security-audit-baseline-{import-reference,get-model,url-name,template-reference,static-reference,settings-key,field-reference,relation-path}-integrity.json`.
- Tests (one per member — 9 files): `scripts/tests/test_scan_import_reference_integrity.py`,
  `scripts/tests/test_verify_{get_model,url_name,template_reference,static_reference,settings_key,field_reference,relation_path}_integrity.py`,
  `scripts/tests/test_verify_ci_gate_wiring.py`.
- CI wiring: `.github/workflows/ci.yml:22-41` (runtime members),
  `.github/workflows/architectural-boundaries.yml` (static member + meta-gate).
- Related index: [`VERIFICATION_GATES_INDEX.md`](VERIFICATION_GATES_INDEX.md);
  per-gate rules: [`../CLAUDE.md`](../CLAUDE.md) scanner table.
