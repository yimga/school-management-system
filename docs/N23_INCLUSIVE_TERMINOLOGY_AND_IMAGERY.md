# N23 — Inclusive terminology and imagery

**Authority:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.1.5 (N23); [CONTENT_AND_TERMINOLOGY_GOVERNANCE.md](CONTENT_AND_TERMINOLOGY_GOVERNANCE.md).

**Status:** Structural checklist and code conventions. Full sitewide audit remains incremental; this doc is the **completion gate** for governance + key patterns.

---

## 1. Terminology

- **People-first:** Describe roles and actions, not stereotypes (e.g. “families”, “guardians”, “learners” where accurate; avoid defaulting to “mom/dad” in product copy).
- **Geographic neutrality:** Avoid idioms tied to one country unless the tenant context requires it; use locale-aware dates/currency (existing region formatters).
- **Ability / access:** Prefer “accessible”, “keyboard-friendly”, “screen reader” in internal docs; user-facing copy stays plain (“Skip to main content”).
- **Glossary alignment:** New UI strings should align with [CONTENT_AND_TERMINOLOGY_GOVERNANCE.md](CONTENT_AND_TERMINOLOGY_GOVERNANCE.md) §1; extend the glossary when introducing a new domain term.

## 2. Imagery and icons

- **Alt text:** Decorative images use `alt=""` only when truly decorative; **logos and branded marks** use a short descriptive `alt` (e.g. `{% trans 'School logo' %}` inside a double-quoted HTML attribute).
- **Stock / marketing:** Prefer diverse representation in marketing assets; document chosen sources in marketing content packs when updated.
- **Contrast:** Follow design tokens and high-contrast CSS where provided (`dashboard-high-contrast.css`, marketing a11y lint).

## 3. Engineering checks (repeatable)

- Tables: `<th scope="col">` / `scope="row"` on data tables ([TEMPLATE_EDITING_CONVENTION.md](TEMPLATE_EDITING_CONVENTION.md)).
- Printable / standalone HTML (e.g. receipts): `lang` on `<html>`, meaningful `alt` on logos, `aria-label` or `<caption>` for data tables when layout is minimal.

## 4. Verification

- Pillar script: `docs/N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md` present (this file).
- Finance receipt template: tests in `apps/finance/tests/test_finance_form_draft_templates.py` assert accessible receipt markers.
