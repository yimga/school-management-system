# Lexicon engine (Wave A — G1, 2026-05-15)

> A school can rename **any** registry term ("Student" → "Scholar",
> "Class" → "Cohort", "Teacher" → "Sensei") and have the change reflected
> platform-wide — UI labels, headings, breadcrumbs, error copy — **without
> code edits or migrations**.

Status: shipped. SW version `sms-v2.20.0-lexicon-engine-2026-05-14`.

## Why

Pre-Wave-A, only four terms were tenant-renamable (`grade`, `gpa`, `term`,
`report_card`) and only via curriculum-template selection or a flat
`School.settings["terminology"]` JSON blob. That covered exam-related
language but missed the loudest UX surface: roles ("Student" / "Teacher" /
"Parent"), organisational nouns ("Class" / "Department" / "Campus"),
and finance ("Fee" / "Invoice"). Tenants in non-Anglophone or non-K12
contexts had no way to localise platform terminology beyond i18n.

Wave A keeps the existing API working unchanged and **extends** it with a
canonical registry, plural support, a wider cascade, and a client-side
helper.

## Architecture

```
                         ┌──────────────────────────────────────┐
                         │ lexicon_catalog.LEXICON_REGISTRY      │  ← Layer 1
                         │ 41 canonical keys, singular+plural    │     defaults
                         └──────────────────────────────────────┘
                                          ▲
                                          │  per-key override
                                          │
            RuntimeDefaults.payload["lexicon.country_overrides"]      ← Layer 2
                e.g. { "FR": { "student": {"singular": "Élève", "plural": "Élèves"} } }
                                          ▲
                                          │  if School.country_code matches
                                          │
            curriculum_templates_registry.json → terminology_map      ← Layer 3
                e.g. american_k12 sets `term: Semester`
                                          ▲
                                          │  if School.settings["curriculum_template_key"] set
                                          │
            walk School.parent_school chain → ancestor terminology    ← Layer 4
                root→nearest, nearest wins                                (district)
                                          ▲
                                          │
            School.settings["terminology"]                            ← Layer 5
                most specific (highest precedence)
```

The resolver lives in `apps/siteconfig/terminology_service.py`. The
canonical 41-term registry is `apps/siteconfig/lexicon_catalog.py`.
The 4 legacy keys (`grade`, `gpa`, `term`, `report_card`) are aliases of
their registry counterparts — old templates with `{% grade_label %}` keep
working unchanged.

## Surfaces

### Python / Django templates

```django
{% load terminology_tags %}

{% term "student" %}                 → "Scholar" (or default)
{% term "student" plural=True %}     → "Scholars"
{% term "class" capitalize=True %}   → "Cohort"
{% term_lower "teacher" %}           → "sensei"
```

### JavaScript

A `<meta name="rmc-lexicon">` tag is emitted in every shell that carries
**only the keys that differ from defaults** (compact JSON `{"s":..,"p":..}`
shape). `static/js/rmc-lexicon.js` reads it once on load and exposes:

```js
RMC.term("student");                            // → "Scholar"
RMC.term("student", { plural: true });          // → "Scholars"
RMC.term("class", { capitalize: true });        // → "Cohort"
RMC.term("teacher", { lower: true });           // → "sensei"
RMC.lexicon.snapshot();                         // full resolved map (debug)
RMC.lexicon.refresh();                          // re-read the meta tag
```

The helper bundles its own 41-key fallback table, so anonymous /
default-tenant pages render correctly even when the meta tag is empty.

### Context processor

`apps.siteconfig.context_processors.lexicon_context` injects:

- `rmc_lexicon_meta` — JSON string for the `<meta>` bridge
- `lexicon` — full `{key: {singular, plural}}` dict for direct template use

Wired in `config/settings.py` after `language_context`.

## Storage shapes

`School.settings["terminology"]` accepts **either** shape per key, mixable:

```jsonc
{
  "student": "Scholar",                                   // flat string (legacy)
  "class":   { "singular": "Cohort", "plural": "Cohorts" }, // explicit plural
  "teacher": { "singular": "Sensei" }                       // plural auto-derived
}
```

Country overlays under `RuntimeDefaults.payload["lexicon.country_overrides"]`
follow the same shape, keyed by ISO 3166-1 alpha-2 country code.

## When to use the generic `{% term %}` vs legacy per-key tags

* **New work** — always `{% term "key" %}`. It pulls from the full 41-key
  registry, supports plurals, and stays consistent across the platform.
* **Existing templates** — leave `{% grade_label %}` / `{% term_label %}`
  alone; they delegate to the same cascade. Migrate during organic
  template touches.
* **Schema-time field renames** (DB columns, model verbose_name) — use
  `DynamicFieldDefinition` instead. The lexicon engine is render-time
  copy only.

## What's intentionally **not** in the engine

* Locale-specific lexicons (FR vs EN-CA vs EN-GB) — out of scope here;
  the i18n layer remains the right home for full translation.
* Classroom-level overrides — `School.settings` is the bottom rung;
  finer-grained per-classroom renaming was deferred.
* Server-side caching of resolved terms — overlay reads are cheap
  enough (one RuntimeDefaults fetch + a parent_school walk capped at 16
  hops); revisit only if profiling shows it.

## Verification

```bash
# Unit tests
python manage.py test apps.siteconfig.tests.test_lexicon_engine
python manage.py test apps.siteconfig.tests.test_terminology_engine    # back-compat

# Manual smoke (Python shell)
from apps.siteconfig.terminology_service import resolve_term
resolve_term(school_with_scholar_override, "student", plural=True)     # → "Scholars"
```

## See also

* `apps/siteconfig/lexicon_catalog.py` — registry (single source of truth)
* `apps/siteconfig/terminology_service.py` — resolver
* `apps/siteconfig/templatetags/terminology_tags.py` — `{% term %}`
* `static/js/rmc-lexicon.js` — `RMC.term()`
* `templates/partials/rmc_lexicon_meta.html` — meta-tag bridge
