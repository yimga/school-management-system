# Lexicon (`{% term %}`) vs i18n (`{% trans %}`) — which tag to use

A short decision guide for template authors. Both tags wrap a string, but
they answer different questions:

- **`{% trans %}`** — *what language is the user reading?* Driven by
  `request.LANGUAGE_CODE` and gettext message catalogs. The same English
  source string maps to French / Spanish / etc. via `.po` files.
- **`{% term %}`** — *what does this tenant call this concept?* Driven
  by the lexicon cascade (`country → curriculum → ancestors → school →
  classroom`). One tenant calls students "Scholars"; another calls them
  "Cadets"; a third uses the default "Students".

## Rule of thumb

Use **`{% term %}`** when the string is a **canonical tenant-overridable
concept** present in `apps/siteconfig/lexicon_catalog.LEXICON_REGISTRY`:
student, teacher, class, course, parent, grade, term, semester, etc.
This is what the user pays the lexicon engine for.

Use **`{% trans %}`** for everything else: verbs ("Save", "Cancel"),
adverbs, system messages, UI affordances. These are translation
targets, not tenant-branding targets.

## Don't use both on the same string

`{% trans "Student" %}` and `{% term "student" %}` answer different
questions. **Don't nest or compose them** — pick one. Inside a string
that mixes both ("Add Student" — a verb + a tenant concept), split:

```django
Add {% term "student" capitalize=True %}            ← correct
{% trans "Add Student" %}                            ← OK if you never override
{% trans "Add" %} {% term "student" capitalize=True %}  ← over-engineered; skip
```

## Migration policy

**No bulk rewrite of existing `{% trans %}` sites with `{% term %}`.**
The two answer different questions and `{% term %}` strips i18n coverage.

**There is now a third tag** (Wave M, 2026-05-15) that solves both at once:
`{% trans_term %}`. Use it for canonical lexicon terms when you also
want i18n fallback when no override is in effect.

## The hybrid `{% trans_term %}` tag (Wave M)

Replaces `{% trans "Student" %}` for canonical lexicon terms. Semantics:

```django
{% trans_term "Student" key="student" %}
```

1. Look up `key="student"` in the lexicon cascade
   (country → curriculum → ancestors → school → classroom).
2. **If a tenant override is in effect** (resolved value differs from
   the registry default), use the override **literally**. Tenant
   branding is locale-agnostic — a tenant who chose "Scholar" gets
   "Scholar" in every locale.
3. **If no override is in effect**, fall through to `gettext("Student")`
   for normal i18n catalog translation. English serves "Student";
   French catalog serves "Élève"; etc.

This unlocks the bulk `{% trans %}` → `{% term %}` adoption K2 explicitly
rejected. Converting `{% trans "Student" %}` → `{% trans_term "Student" key="student" %}`
is now a safe operation: tenant override wins when present, i18n catalog
applies when absent.

### When to use which

| Surface | Tag |
|---|---|
| Canonical lexicon term, no i18n catalog needed | `{% term "student" %}` |
| Canonical lexicon term, want i18n fallback when no override | `{% trans_term "Student" key="student" %}` (Wave M) |
| Non-lexicon string (verbs, system messages, error copy) | `{% trans "Save" %}` |
| Pure-display label, no override or translation expected | plain text |

### Coherence rule

The `source` argument (the gettext catalog key) **should equal the
registry default** for `key`. Otherwise the no-override branch shows
the catalog string while the override branch shows the lexicon value
— same template renders different strings depending on whether a
tenant has overridden, which is surprising. Coherent:

```django
{% trans_term "Student" key="student" %}          ← source matches registry default
{% trans_term "Students" key="student" plural=True %}
```

Incoherent (don't):
```django
{% trans_term "Pupil" key="student" %}            ← source disagrees with default
```

### Migration playbook

To convert a `{% trans %}` site:

1. Verify the source string is a canonical lexicon key
   (`apps/siteconfig/lexicon_catalog.LEXICON_REGISTRY`). If not, leave
   as `{% trans %}`.
2. Add `{% load terminology_tags %}` if not already loaded.
3. Replace `{% trans "Student" %}` with `{% trans_term "Student" key="student" %}`.
4. Plural: `{% trans "Students" %}` → `{% trans_term "Students" key="student" plural=True %}`.
5. No `.po` catalog change required — the gettext fallback uses the
   same `source` string the original `{% trans %}` did.

**Adoption is still incremental — no bulk rewrite.** Convert sites
you're already touching for other reasons.

## When `{% term %}` will help most

- New templates being authored from scratch.
- Headings, button labels, and table column headers that show a single
  noun ("Students", "Classes", "Teachers").
- Quick-action surfaces ("Add Student" / "Add Teacher" — already adopted
  in `templates/components/quick_actions.html`).
- Form labels that are pure concept names ("Class:", "Teacher:").

## When `{% term %}` won't help

- Verbs and short imperatives ("Save", "Submit", "Cancel").
- System notices and error messages — they're translation-shaped, not
  branding-shaped.
- Mixed prose paragraphs — readability suffers if you splice 3+ lexicon
  lookups into a sentence.

## See also

- `apps/siteconfig/lexicon_catalog.py` — the 41-key registry.
- `apps/siteconfig/terminology_service.py` — the cascade resolver.
- `apps/siteconfig/templatetags/terminology_tags.py` — the tag surface.
- `static/js/rmc-lexicon.js` — the JS helper (`RMC.term(...)`).
- `templates/portal/configure/lexicon_settings.html` — the tenant UI.
