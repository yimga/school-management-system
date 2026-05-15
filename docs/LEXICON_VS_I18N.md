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

**No bulk rewrite of existing `{% trans %}` sites.** The lexicon engine
is opt-in per template. Spot-fix on touch — when you're already in a
file for another reason and you spot an unwrapped tenant-overridable
noun, swap it.

Existing `{% trans "Student" %}` sites are a separate decision: leaving
them preserves i18n coverage for the (currently small) set of non-English
deployments. Converting them is a deliberate trade — make it a wave of
its own, not a side-effect of a polish pass.

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
