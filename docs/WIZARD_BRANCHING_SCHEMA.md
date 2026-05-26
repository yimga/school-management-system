# Wizard Branching Schema

**Status:** Authoritative. Updated 2026-05-26 (v3.93.1).

This document is the formal source-of-truth for the JSON schema that drives
every wizard in the Unified Wizard Framework. Each file in
``apps/setup_studio/wizards/*.json`` MUST match this schema, enforced by
``scripts/scan_wizard_json_schema_drift.py`` (baseline 0, zero-tolerance).

---

## 1. Top-level object

```jsonc
{
  "wizard_key": "<unique key, ^[a-z][a-z0-9_]*$>",
  "version": 1,                              // integer, monotonically bumped per breaking change
  "audience": ["<audience1>", "<audience2>"],
  "label_token": "wizards.<wizard_key>.label",
  "description_token": "wizards.<wizard_key>.description",
  "icon_class": "rmc-icon-<glyph>",         // matches ^rmc-icon-[a-z-]+$
  "estimated_minutes": 1..60,
  "feature_flag_disabled": false,            // optional; true = parse-only, not loaded into live registry
  "gates": { ... },                          // optional
  "ai": { ... },                             // optional
  "steps": [ {...}, {...} ]                  // 1..8 entries
}
```

### audience values (closed set)

* ``operator`` — platform-level operator (staff)
* ``tenant_admin`` — school-level administrator
* ``teacher``
* ``parent``
* ``student``
* ``staff``

### gates object

All keys optional:

| Key | Type | Effect |
|---|---|---|
| ``permission_codename`` | string | View blocks unless user has this Django codename |
| ``feature_flag`` | string | View blocks unless flag is true |
| ``prerequisite_wizard`` | string | View blocks unless that wizard is completed |
| ``min_setup_health_score`` | int 0..100 | View blocks unless SetupProgress.health_score ≥ N |
| ``requires_country_in`` | list of ISO-3166 codes | View blocks unless tenant country in list |

### ai object

All keys optional, default false:

| Key | Effect |
|---|---|
| ``smart_defaults`` | per-step `ai_recommend` blocks honored |
| ``branch_rationale`` | request_branch_rationale called on branched steps |
| ``natural_language_intake`` | accepts free-text fields routed via request_natural_language_intake |
| ``translate_mesh`` | request_translation_mesh available for outbound templates |

---

## 2. Step object

```jsonc
{
  "key": "<unique within wizard, ^[a-z][a-z0-9_]*$>",
  "label_token": "wizards.<wizard_key>.step.<step_key>.label",
  "description_token": "wizards.<wizard_key>.step.<step_key>.description",
  "input_type": "<one of 19 allowed>",
  "options_resolver": "apps.<path>::<callable>",   // optional, mutually exclusive with `fields`+`choices_resolver`
  "fields": [ {...} ],                               // required for input_type=structured_form
  "next_step_resolver": "apps.<path>::<callable>",  // optional, mutually exclusive with `branches`
  "branches": { "<value>": "<step_key>", "default": "<step_key>" }, // optional
  "ai_recommend": { ... },                          // optional
  "validation": { ... },                            // optional, server-side
  "persistence": { "target": "<...>", "writer": "apps.<path>::<callable>" },
  "estimated_seconds": 10..600,
  "mobile_layout": "default|full_bleed|split|compact"
}
```

### input_type values (closed set — 19 types)

```
single_choice    multi_choice    text             long_text
number           decimal         boolean          file_upload
image_upload     color_picker    domain_input     structured_form
draw_on_map      csv_mapping     rich_select      ranked_list
key_value_pairs  datetime        duration
```

Each maps to a partial at ``templates/setup_studio/inputs/<input_type>.html``
enforced by ``scan_wizard_class_grammar.py``.

### branches XOR next_step_resolver

A step has EITHER ``branches`` OR ``next_step_resolver`` OR neither (sequential
to next step in array). NEVER both. Validator at
``wizard_engine._parse_step`` enforces.

#### Branches syntax

```jsonc
"branches": {
  "BR|IN|KE":   "next_step_a",     // pipe = any-of match
  "US":         "next_step_b",
  "default":    "next_step_c",     // matched when no other key hits
  "__end__":    "__end__"          // sentinel: end of wizard
}
```

Branch key matches the answer payload's ``value`` (single-valued steps) or
explicit ``branch_value`` field. Multi-valued steps SHOULD use a custom
``next_step_resolver`` instead.

### ai_recommend object

```jsonc
"ai_recommend": {
  "enabled": true,
  "context_keys": ["country_code", "school_type", "primary_language"],
  "max_tokens": 800,
  "prompt_template_key": "prompt.fintech.suggest_apm"
}
```

* ``context_keys`` is a whitelist — fields NOT listed here are excluded from
  the AI prompt context. Defaults to empty (NO context sent).
* ``prompt_template_key`` MUST exist in
  ``apps.setup_studio.ai_prompts.PROMPT_LIBRARY``.
* Every prompt key MUST have a matching fallback in
  ``apps.setup_studio.ai_fallbacks.FALLBACK_REGISTRY``.

### validation object (server-side, never trust client)

| Key | Type | Effect |
|---|---|---|
| ``required`` | bool | Empty value → ``wizards.errors.required`` |
| ``max_length`` | int | String longer → ``wizards.errors.max_length`` |
| ``min_length`` | int | String shorter → ``wizards.errors.min_length`` |
| ``pattern`` | string (regex) | Mismatch → ``wizards.errors.pattern_mismatch`` |
| ``decimal_min`` | string | Decimal below → ``wizards.errors.decimal_below_min`` |
| ``decimal_max`` | string | Decimal above → ``wizards.errors.decimal_above_max`` |
| ``integer_min`` | int | Integer below → ``wizards.errors.integer_below_min`` |
| ``integer_max`` | int | Integer above → ``wizards.errors.integer_above_max`` |
| ``allowed_extensions`` | list of strings | File ext outside → ``wizards.errors.file_extension_not_allowed`` |
| ``max_file_bytes`` | int | File too big → ``wizards.errors.file_too_large`` |
| ``iso_country`` | bool | Not ISO-3166 alpha-2 → ``wizards.errors.country_code_invalid`` |
| ``iso_currency`` | bool | Not ISO-4217 → ``wizards.errors.currency_code_invalid`` |
| ``color_hex`` | bool | Not ``#RRGGBB`` → ``wizards.errors.color_hex_invalid`` |
| ``domain_format`` | bool | Invalid domain → ``wizards.errors.domain_invalid`` |
| ``email_shape`` | bool | Invalid email → ``wizards.errors.email_invalid`` |

### persistence object

```jsonc
"persistence": {
  "target": "site_settings|runtime_defaults|lifecycle_stage|companion_receiver|custom",
  "field_path": "whitelabel.brand_palette_key",   // optional, target-specific
  "writer": "apps.setup_studio.wizard_resolvers::write_typography_palette"
}
```

The ``writer`` dotted path is called with kwargs:
``school, wizard_key, step_key, payload, actor_user_id``. Failure logs
``wizard.persistence.failed`` metric but does NOT crash the wizard — state
still advances to the next step and the answer persists into
``SetupProgress.step_state["wizards"]`` regardless.

---

## 3. StructuredField object (for input_type=structured_form)

```jsonc
{
  "name": "logo_file",
  "label_token": "wizards.whitelabel.field.logo_file.label",
  "type": "text|number|decimal|boolean|email|phone|date|select|textarea|color|file",
  "required": true,
  "default": <any>,
  "choices_resolver": "apps.<path>::<callable>",   // required for type=select
  "validation": { ... }                             // same keys as step.validation
}
```

---

## 4. Dotted-path format

All ``options_resolver``, ``next_step_resolver``, ``persistence.writer``,
``choices_resolver`` values match the regex:

```
^apps\.[a-z_.]+::[a-z_]+$
```

The scanner imports each path at boot via ``verify_unified_wizard_framework.py``.
Import failure on a path = scanner FAIL.

---

## 5. Tokens (i18n)

All ``*_token`` fields point at i18n message keys, NEVER literal strings.
Convention:

* ``wizards.<wizard_key>.label`` — wizard title
* ``wizards.<wizard_key>.description`` — wizard subtitle
* ``wizards.<wizard_key>.step.<step_key>.label`` — step title
* ``wizards.<wizard_key>.step.<step_key>.description`` — step subtitle
* ``wizards.<wizard_key>.step.<step_key>.field.<field_name>.label`` — field label
* ``wizards.errors.<error_key>`` — shared error messages
* ``wizards.warnings.<warning_key>`` — shared warning messages

Tokens are extracted via ``python manage.py makemessages`` and translated in
``locale/<lc>/LC_MESSAGES/django.po``.

---

## 6. CI enforcement

| Scanner | Baseline | Workflow job | What it checks |
|---|---|---|---|
| ``scan_wizard_json_schema_drift.py`` | **0** | ``wizard-json-schema-drift`` | Every JSON file matches every invariant in this doc |
| ``scan_wizard_class_grammar.py`` | **0** | ``wizard-class-grammar`` | Every ``.rmc-wizard-*`` class referenced in templates is defined in CSS |
| ``verify_unified_wizard_framework.py`` | integrity gate | wired by ``apps/setup_studio/**`` path triggers | Schema + dotted-path import + AI boundary + prompt library coverage |

A new wizard JSON file MUST pass all three before merge.

---

## 7. Lifecycle of a new wizard

1. Author ``apps/setup_studio/wizards/<wizard_key>.json`` matching this schema.
2. Implement `options_resolver` and `persistence.writer` callables in either:
   * ``apps/setup_studio/wizard_resolvers.py`` (preferred for short hand-coded lists), or
   * a per-domain module under ``apps/<domain>/`` (preferred when integrating with existing models).
3. Add `prompt_template_key` to ``apps/setup_studio/ai_prompts.py::PROMPT_LIBRARY``.
4. Add matching fallback to ``apps/setup_studio/ai_fallbacks.py::FALLBACK_REGISTRY``.
5. Add label tokens to translation catalog.
6. Run ``scripts/scan_wizard_json_schema_drift.py`` and
   ``scripts/scan_wizard_class_grammar.py`` locally; both must report 0 findings.
7. Run ``scripts/verify_unified_wizard_framework.py`` locally; all checks must
   return 0 errors.
8. Add Playwright e2e spec at ``tests/e2e/wizards/<wizard_key>.spec.js``
   (recommended — not yet gating, but planned for ``e2e-wizards.yml``).
9. Bump SW per CLAUDE.md deploy checklist.

---

## 8. Versioning

The ``version`` integer on a wizard is bumped when the **schema of stored
answers changes** in a way the engine can't migrate silently. On version bump:

* Old `step_state["wizards"][<wizard_key>]` entries with mismatched
  ``schema_version`` are dropped client-side by ``rmc-wizard-state-cache.js``.
* Server-side, the state stays as-is until the user resumes — the engine then
  re-prompts the first step and overwrites the slice.
* For breaking JSON changes, also bump SW (``CACHE_VERSION``).

---

## 9. Reserved branch keys

| Key | Meaning |
|---|---|
| ``default`` | Catch-all when no other branch matches |
| ``__end__`` | Sentinel — wizard completes |

No other reserved keys. ``branches.foo`` where ``foo`` is the literal answer
value works exactly as expected.

---

## 10. Anti-patterns (rejected by scanner or by review)

* Inlining option lists in JSON (must use ``options_resolver``).
* Multi-line ``{# … #}`` Django comments in any wizard template (use
  ``{% comment %}…{% endcomment %}``).
* Importing ``services.ai_gateway`` directly inside ``apps/setup_studio/`` —
  ``scan_ai_gateway_boundary.py`` rejects.
* Logging interpolated PII fields (``logger.info(f"... {token}")``) anywhere
  in wizard code — ``scan_pii_logging_smell.py`` rejects.
* ``float(<money>)`` in any wizard validator or writer —
  ``scan_money_float.py`` rejects.
* Literal role strings (``"ADMIN"``, ``"PROPRIETOR"``, etc.) — use
  ``User.Role`` or ``apps.platform_runtime.role_registry``.

---

## 11. Implementation reference

| File | Role |
|---|---|
| ``apps/setup_studio/wizard_engine.py`` | Registry loader + dataclasses + branching + validation |
| ``apps/setup_studio/wizard_state_resolver.py`` | SetupProgress.step_state CRUD wrapper |
| ``apps/setup_studio/wizard_validators.py`` | Pure validation functions |
| ``apps/setup_studio/wizard_ai.py`` | AI bridge (5 callables, all via services.ai_helpers) |
| ``apps/setup_studio/wizard_telemetry.py`` | Metric emitters |
| ``apps/setup_studio/wizard_views.py`` | Operator + Tenant + AI Recommend + Reset + Index views |
| ``apps/setup_studio/urls.py`` | URL routes under ``setup_studio`` namespace |
| ``apps/setup_studio/wizard_resolvers.py`` | All options resolvers + persistence writers |
| ``apps/setup_studio/ai_prompts.py`` | Prompt library + universal envelope |
| ``apps/setup_studio/ai_fallbacks.py`` | Deterministic fallback per prompt |
| ``apps/setup_studio/tasks.py`` | Celery beat handler for nightly recommendation refresh |
| ``static/css/rmc-wizard.css`` | Class grammar |
| ``static/js/rmc-wizard-state-cache.js`` | Client-side localStorage cache |
| ``templates/setup_studio/`` | Templates (base + partials + inputs) |
| ``apps/setup_studio/wizards/*.json`` | The registry — one file per wizard |

---

**Plan docs:**
* High-level: [`docs/plans/UNIFIED_WIZARD_FRAMEWORK_PLAN.md`](plans/UNIFIED_WIZARD_FRAMEWORK_PLAN.md)
* Implementation detail: [`docs/plans/UNIFIED_WIZARD_FRAMEWORK_IMPLEMENTATION_DETAIL.md`](plans/UNIFIED_WIZARD_FRAMEWORK_IMPLEMENTATION_DETAIL.md)
