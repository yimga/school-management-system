# Phase 3: Metadata-driven config (24.8) & Policy-driven forms (23.4)

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md — Section 24.8, Section 23.4.

---

## 24.8 — Everything configurable metadata-driven before custom-coded

**Goal:** Any tenant-specific or configurable behaviour is driven by metadata (policy, blueprint, form schema) rather than hardcoded in views/forms.

**Implemented:**

- **Policy carries form schemas:** `get_effective_policy(school)` returns `out["forms"]` with one entry per form name (e.g. `link_child`, `student_onboarding`). Each entry is `{ "fields": [ { "name", "visible", "required", "label", "choices_key", "validation", "document_required" }, ... ] }`.
- **Platform defaults:** `apps.policies.form_policy.default_forms_platform()` provides default field configs so behaviour is consistent when no tenant override exists.
- **Tenant overrides:** `school.settings["forms"][form_name]` and (when POLICY_USE_BUNDLES) bundle `policy_snapshot["forms"]` are merged into `policy["forms"]`. No form logic reads `school.settings` directly; all reads go through `get_effective_policy` and `form_policy` helpers.
- **Single read path:** Resolver (and optional bundle) is the only place that merges `forms`; modules use `apply_form_policy(form, form_name, policy)` and do not implement their own form config parsing.

**Usage:** When adding a new configurable form, (1) add a default schema in `default_forms_platform()` or document the expected schema, (2) in the form’s `__init__` call `apply_form_policy(self, form_name, policy, school=...)`, (3) let tenants override via `school.settings["forms"][form_name]` or blueprint.

---

## 23.4 — Forms/Serializers: Policy-driven field visibility, required/optional, picker options, validation

**Goal:** Field visibility, required/optional, labels, picker options (choices), document requirements, and validation rules come from policy, not hardcoded in the form class.

**Implemented:**

- **`apps.policies.form_policy`**:
  - `get_form_schema(policy, form_name)` — returns schema dict for form.
  - `get_field_configs(form_name, policy)` — returns list of field configs.
  - `apply_form_policy(form, form_name, policy, school=None)` — mutates form: sets `required`, `label`, `help_text`; removes fields when `visible: false`; sets `field.choices` from `choices_key` via `_resolve_choices_for_key()` (catalog-backed: gender, relationship, preferred_contact, student_status, payment_method).
  - `_resolve_choices_for_key(choices_key, school)` — resolves choices from models/enums so forms use catalog-backed pickers (23.4) without hardcoding choice lists in the form.
- **Resolver:** Merges `forms` from platform defaults, bundle snapshot, and `school.settings["forms"]` so `policy["forms"]` is always present.
- **Forms wired:** `LinkChildForm` and `StudentOnboardingForm` call `apply_form_policy(self, "link_child"|"student_onboarding", policy, school=...)` in `__init__` after `super().__init__()`.

**Tenant override example:** To make “admission_number” optional and hide “referral_code” for a school, set in `school.settings`:

```json
{
  "forms": {
    "link_child": {
      "fields": [
        { "name": "admission_number", "visible": true, "required": false },
        { "name": "referral_code", "visible": false }
      ]
    }
  }
}
```

Only listed fields are overridden; others keep platform defaults.

**Validation rules:** The schema supports a `validation` key per field (e.g. `"alphanumeric"`); future work can add validators in `apply_form_policy` or in form `clean_*` using `get_field_configs()`.

**Document requirements:** Schema supports `document_required`; `apply_form_policy` sets `field.document_required = True` for templates to show upload/attach UI. Full document-requirement enforcement (e.g. blocking submit until file present) can be added in form validation.

---

## Files touched

- `apps/policies/form_policy.py` — new (get_form_schema, get_field_configs, apply_form_policy, default_forms_platform, _resolve_choices_for_key).
- `apps/policies/resolver.py` — merge `forms` from default, bundle, and school.settings.
- `apps/portal/forms.py` — LinkChildForm and StudentOnboardingForm call apply_form_policy in __init__.

---

## POLICY_USE_BUNDLES and POLICY_CACHE_TTL

- **POLICY_USE_BUNDLES:** When set (e.g. in .env or settings), `get_effective_policy(school)` merges from `TenantBlueprint.active_bundle.policy_snapshot` when the school has an active bundle. Documented in phase7_deferred_rules_24_12_to_24_15.md and .env.example (# POLICY_USE_BUNDLES=1).
- **POLICY_CACHE_TTL:** Per-tenant policy cache TTL in seconds; 0 = no cache. Documented in phase7 and .env.example (# POLICY_CACHE_TTL=300). Resolver uses it in apps/policies/resolver.py.

## Remaining forms (add via same pattern)

Key tenant-facing forms already use `apply_form_policy`:

- **link_child** — LinkChildForm (portal)
- **student_onboarding** — StudentOnboardingForm (portal)

Any other form that should be tenant-configurable: (1) add a default schema in `default_forms_platform()` or document the form name and expected fields, (2) in the form’s `__init__` call `apply_form_policy(self, form_name, policy, school=...)`, (3) allow overrides via `school.settings["forms"][form_name]` or blueprint. No hardcoded form config in views.

## Checklist

- **24.8:** Form (and future) config is metadata-driven via policy; no form-specific config hardcoded in views.
- **23.4:** Field visibility, required/optional, labels, picker options (choices_key) and document_required hint applied from policy; LinkChildForm and StudentOnboardingForm use it.
