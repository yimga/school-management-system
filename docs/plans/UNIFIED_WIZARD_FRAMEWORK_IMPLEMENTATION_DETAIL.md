# Unified Wizard Framework — Implementation Detail (companion to UNIFIED_WIZARD_FRAMEWORK_PLAN.md)

**Status:** **PLANNED — implementation field manual.** 2026-05-26.
**Reads alongside:** `docs/plans/UNIFIED_WIZARD_FRAMEWORK_PLAN.md` (the high-level architecture, phasing, acceptance criteria).
**Purpose:** This doc is the step-by-step build sheet. Every wizard's every step is specified end-to-end (fields, validation, AI prompt, persistence target, branching, failure modes). The next implementer should be able to write code directly from this without re-deciding any UX or schema question.

---

## Table of contents

- §1 Engine code surface — exact Python signatures
- §2 JSON branching schema — every field documented
- §3 State model — example records + cache JS API
- §4 URL + template + permission map (full table)
- §5 AI prompt library — per helper, the exact prompt template
- §6 The 18 wizards — full step-by-step specs
  - §6.1 P1.0 — Engine bootstrap (no UI)
  - §6.2 P1.1 — Cross-Platform Whitelabel & Branding
  - §6.3 P1.2 — Multi-Campus Local Sovereignty
  - §6.4 P1.3 — Polymorphic Grading & Curricula
  - §6.5 P1.4 — Legacy Data Extraction Pipeline
  - §6.6 P1.5 — AI Helpcenter Knowledge Injection
  - §6.7 P1.PARENT — Parent persona onboarding
  - §6.8 P1.STAFF — Staff persona onboarding
  - §6.9 P2.1 — Local-First FinTech & Tax Matrix
  - §6.10 P2.2 — Localized Activity & Asset Marketplace
  - §6.11 P2.3 — Cashless Campus POS
  - §6.12 P2.4 — Dynamic Safeguarding / Incident / Medical
  - §6.13 P2.5 — Omnichannel Communication Routing
  - §6.14 P3.1 — JIT Operator Compliance & Safeguarding
  - §6.15 P3.2 — Human Capital, Shift, Substitute Market
  - §6.16 P3.3 — Institutional Performance & Board Reporting
  - §6.17 P3.4 — Self-Healing Observability Guard
  - §6.18 P3.5 — Dynamic Multi-Campus Scheduling
  - §6.19 P3.6 — Localized Field Trip Coordinator
  - §6.20 P3.7 — Personal Graduation Pathway & Elective
- §7 i18n strategy
- §8 Mobile UX rules per input type
- §9 Test coverage matrix
- §10 Telemetry + failure mode reference
- §11 Migration / cleanup of legacy persona wizards
- §12 Implementation order (file-by-file)

---

## §1 Engine code surface — exact Python signatures

Every public callable, every dataclass. This section is contract-binding — names + types fixed before any wizard JSON gets written.

### §1.1 `apps/setup_studio/wizard_engine.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol
from pathlib import Path
import importlib
import json

Audience = Literal["operator", "tenant_admin", "teacher", "parent", "student", "staff"]
InputType = Literal[
    "single_choice", "multi_choice", "text", "long_text", "number", "decimal",
    "boolean", "file_upload", "image_upload", "color_picker", "domain_input",
    "structured_form", "draw_on_map", "csv_mapping", "rich_select",
    "ranked_list", "key_value_pairs", "datetime", "duration",
]

@dataclass(frozen=True)
class StepDefinition:
    key: str
    label_token: str
    description_token: str
    input_type: InputType
    options_resolver: str | None = None       # "apps.foo.bar::list_things"
    fields: list[dict[str, Any]] = field(default_factory=list)  # for structured_form
    next_step_resolver: str | None = None     # "apps.foo.bar::next_after_x"
    branches: dict[str, str] | None = None    # declarative branching (mutually exclusive with next_step_resolver)
    ai_recommend: dict[str, Any] | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    persistence: dict[str, Any] = field(default_factory=dict)
    estimated_seconds: int = 60
    mobile_layout: str | None = None          # override default

@dataclass(frozen=True)
class WizardDefinition:
    wizard_key: str
    version: int
    audience: list[Audience]
    label_token: str
    description_token: str
    icon_class: str
    estimated_minutes: int
    gates: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, bool] = field(default_factory=dict)
    steps: list[StepDefinition] = field(default_factory=list)

# Registry — populated at module import from wizards/*.json
WIZARD_REGISTRY: dict[str, WizardDefinition] = {}

def load_wizard_registry(directory: Path | None = None) -> dict[str, WizardDefinition]:
    """Walk wizards/*.json, parse, validate, populate WIZARD_REGISTRY. Idempotent."""

def get_wizard(wizard_key: str) -> WizardDefinition:
    """Return WizardDefinition or raise WizardNotFound."""

def list_wizards_for_audience(audience: Audience) -> list[WizardDefinition]:
    """Filter registry by audience."""

def resolve_options(step: StepDefinition, *, request, school) -> list[dict[str, Any]]:
    """Import and call the options_resolver dotted path. Returns list of {value, label_token, metadata}."""

def resolve_next_step(
    wizard: WizardDefinition,
    *,
    current_step: StepDefinition,
    current_answer: dict[str, Any],
    progress_state: dict[str, Any],
) -> StepDefinition | None:
    """Apply declarative branches OR call next_step_resolver. Returns None at end-of-wizard."""

def validate_step_answer(
    step: StepDefinition,
    payload: dict[str, Any],
) -> tuple[bool, dict[str, str]]:
    """Returns (is_valid, {field_name: error_token}). Server-side only — never trust client validation."""

class WizardError(Exception):
    """Base."""

class WizardNotFound(WizardError): ...
class StepNotFound(WizardError): ...
class ResolverImportError(WizardError): ...
class WizardSchemaError(WizardError): ...
class GateBlockedError(WizardError):
    """Permission, feature flag, or prerequisite wizard not completed."""
```

### §1.2 `apps/setup_studio/wizard_state_resolver.py`

```python
from __future__ import annotations
from typing import Any
from django.db import transaction
from apps.schools.models import School
from apps.setup_studio.models import SetupProgress

WIZARD_STATE_SCHEMA_VERSION = 1

def get_or_create_progress(school: School) -> SetupProgress:
    """One row per school. Creates if absent."""

def get_wizard_state(school: School, wizard_key: str) -> dict[str, Any]:
    """
    Returns the wizard's slice of SetupProgress.step_state["wizards"][wizard_key].
    Shape:
      {
        "current_step_key": "...",
        "answers": {"<step_key>": {...}},
        "completed": ["...", ...],
        "schema_version": 1,
        "ai_recommendations_cache": {"<step_key>": {...}},
        "started_at": "<iso>",
        "last_modified": "<iso>",
        "ai_request_count": 0,
        "ai_fallback_count": 0,
      }
    Empty dict if wizard hasn't been started.
    """

@transaction.atomic
def apply_step_answer(
    school: School,
    wizard_key: str,
    step_key: str,
    payload: dict[str, Any],
    *,
    actor_user_id: int,
) -> dict[str, Any]:
    """
    Validates payload via wizard_engine.validate_step_answer.
    Writes to SetupProgress.step_state["wizards"][wizard_key]["answers"][step_key].
    Advances current_step_key via wizard_engine.resolve_next_step.
    Returns the new wizard state.
    Side effects (depending on step.persistence config):
      - update SiteSettings.cockpit_payload
      - update RuntimeDefaults typed columns
      - append to SetupProgress.completed_keys
      - emit observability metric `wizard.<wizard_key>.<step_key>.applied`
    """

def reset_wizard(school: School, wizard_key: str, *, actor_user_id: int) -> None:
    """Drops the wizard's slice. Used by 'restart' UI affordance and tests."""

def export_wizard_state(school: School, wizard_key: str) -> dict[str, Any]:
    """PII-sanitized export for audit and DSAR. Mirrors _sanitize_payload from migration_cloud."""

def restore_wizard_state(school: School, wizard_key: str, state: dict[str, Any], *, actor_user_id: int) -> None:
    """Reverse of export_wizard_state. For test fixtures and tenant migration."""
```

### §1.3 `apps/setup_studio/wizard_ai.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from django.http import HttpRequest
from apps.schools.models import School
from services.ai_helpers import invoke_with_request, normalize_gateway_metadata

AI_BUDGET_SECONDS = 5.0
AI_MAX_TOKENS_DEFAULT = 800

@dataclass(frozen=True)
class SmartDefaultsResult:
    suggestions: dict[str, Any]            # {field_name: suggested_value}
    confidence: dict[str, float]           # {field_name: 0.0..1.0}
    rationale_text: str | None
    used_fallback: bool
    latency_ms: int

@dataclass(frozen=True)
class BranchRationaleResult:
    rationale_text: str
    used_fallback: bool
    latency_ms: int

@dataclass(frozen=True)
class NaturalLanguageIntakeResult:
    parsed_fields: dict[str, Any]          # {target_field: value}
    unresolved_phrases: list[str]
    confidence: float
    used_fallback: bool
    latency_ms: int

@dataclass(frozen=True)
class TranslationMeshResult:
    translations: dict[str, str]           # {locale: translated_text}
    failed_locales: list[str]
    used_fallback: bool
    latency_ms: int

def request_smart_defaults(
    *, request: HttpRequest, school: School, wizard_key: str, step_key: str,
    context_keys: list[str], prior_answers: dict[str, Any],
) -> SmartDefaultsResult:
    """
    Builds sanitized context dict from context_keys (filtered against ai_context_whitelist).
    Invokes services.ai_helpers.invoke_with_request with structured prompt from prompt_library.
    Falls back to deterministic rule from step's options_resolver metadata on timeout.
    Emits metrics: wizard.ai.smart_defaults.{success,timeout,fallback}.
    """

def request_branch_rationale(
    *, request: HttpRequest, school: School, wizard_key: str, step_key: str,
    prior_answers: dict[str, Any], branch_taken: str,
) -> BranchRationaleResult: ...

def request_natural_language_intake(
    *, request: HttpRequest, school: School, wizard_key: str,
    free_text: str, target_fields: list[str],
) -> NaturalLanguageIntakeResult: ...

def request_translation_mesh(
    *, request: HttpRequest, school: School,
    source_locale: str, target_locales: list[str], message: str,
) -> TranslationMeshResult: ...

def refresh_setup_recommendations(*, request: HttpRequest, school: School) -> list[dict[str, Any]]:
    """
    Nightly Celery beat handler. Scans SetupProgress + tenant context + completion.
    Writes fresh SetupProgress.recommendations JSON.
    Bounded: max 10 recommendations per school per refresh.
    Returns the list it wrote.
    """

# Sanitization
SENSITIVE_CONTEXT_REJECT_KEYS = frozenset({
    "password", "passwd", "pwd", "hash", "secret", "token",
    "ssn", "dob", "api_key", "apikey", "private_key",
    "signature_text", "email", "phone",
    "ifsc", "iban", "swift", "pan", "aadhaar", "tin",
    "guardian_name", "student_name", "license_plate",
})

def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Walks dict; drops any key matching SENSITIVE_CONTEXT_REJECT_KEYS (case-insensitive substring)."""
```

### §1.4 `apps/setup_studio/wizard_views.py`

```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import View
from django.http import HttpRequest, HttpResponse

class WizardViewMixin:
    audience: str
    base_template: str

    def _resolve_wizard(self, wizard_key: str) -> WizardDefinition: ...
    def _check_gates(self, wizard: WizardDefinition, request: HttpRequest, school: School) -> None:
        """Raises GateBlockedError or returns None."""
    def _render(self, request, wizard, step, state, ai_recommendations) -> HttpResponse: ...

@method_decorator(staff_member_required, name="dispatch")
class OperatorWizardView(LoginRequiredMixin, WizardViewMixin, View):
    audience = "operator"
    base_template = "setup_studio/operator_wizard.html"
    # rbac-allow: super-staff-wizard-engine-access
    def get(self, request: HttpRequest, wizard_key: str, step_key: str | None = None) -> HttpResponse: ...
    def post(self, request: HttpRequest, wizard_key: str, step_key: str) -> HttpResponse: ...

class TenantWizardView(LoginRequiredMixin, WizardViewMixin, View):
    audience = "tenant_admin"
    base_template = "setup_studio/tenant_wizard.html"
    # rbac-allow: tenant-admin-wizard-engine-access-via-role-registry
    def get(self, request: HttpRequest, wizard_key: str, step_key: str | None = None) -> HttpResponse: ...
    def post(self, request: HttpRequest, wizard_key: str, step_key: str) -> HttpResponse: ...

class WizardAIRecommendView(LoginRequiredMixin, View):
    """AJAX endpoint — POST {wizard_key, step_key, prior_answers} → JSON SmartDefaultsResult."""
    # rbac-allow: authenticated-user-wizard-ai-recommend
    def post(self, request: HttpRequest) -> HttpResponse: ...

class WizardStateResetView(LoginRequiredMixin, View):
    """POST {wizard_key} → reset. Confirms via CSRF + double-submit token in form."""
    def post(self, request: HttpRequest, wizard_key: str) -> HttpResponse: ...
```

### §1.5 `apps/setup_studio/wizard_validators.py`

Pure functions, no Django dependencies, fully unit-testable:

```python
from typing import Any

def validate_required(value: Any) -> tuple[bool, str | None]:
    """('wizard.errors.required' on empty)"""

def validate_max_length(value: str, max_len: int) -> tuple[bool, str | None]: ...
def validate_min_length(value: str, min_len: int) -> tuple[bool, str | None]: ...
def validate_pattern(value: str, regex: str) -> tuple[bool, str | None]: ...
def validate_in_choices(value: Any, choices: list[Any]) -> tuple[bool, str | None]: ...
def validate_decimal_range(value: str, *, min: str | None, max: str | None) -> tuple[bool, str | None]:
    """Operates on Decimal, never float — money_float gate."""

def validate_domain_format(value: str) -> tuple[bool, str | None]: ...
def validate_color_hex(value: str) -> tuple[bool, str | None]: ...
def validate_file_extension(filename: str, allowed: list[str]) -> tuple[bool, str | None]: ...
def validate_file_size_bytes(size: int, max_bytes: int) -> tuple[bool, str | None]: ...
def validate_csv_header(headers: list[str], required: list[str]) -> tuple[bool, str | None]: ...
def validate_pfx_certificate_shape(b: bytes) -> tuple[bool, str | None]:
    """Shape-only — confirms PKCS#12 magic. Live validation deferred."""
```

### §1.6 `apps/setup_studio/wizard_telemetry.py`

```python
from apps.observability.metrics import emit_counter, emit_histogram

def emit_step_viewed(wizard_key: str, step_key: str, audience: str) -> None: ...
def emit_step_applied(wizard_key: str, step_key: str, audience: str) -> None: ...
def emit_step_validation_failed(wizard_key: str, step_key: str, field_name: str) -> None: ...
def emit_wizard_completed(wizard_key: str, audience: str, duration_seconds: int) -> None: ...
def emit_wizard_abandoned(wizard_key: str, last_step_key: str, audience: str) -> None: ...
def emit_ai_smart_defaults_outcome(wizard_key: str, step_key: str, outcome: str, latency_ms: int) -> None: ...
def emit_ai_branch_rationale_outcome(wizard_key: str, step_key: str, outcome: str, latency_ms: int) -> None: ...

# All emit_counter calls use sanitized labels per apps/observability/metrics.py contract — no PII.
```

---

## §2 JSON branching schema — every field documented

Source of truth lives at `docs/WIZARD_BRANCHING_SCHEMA.md` (jsonschema draft-2020-12). The summary:

```jsonc
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["wizard_key", "version", "audience", "label_token", "estimated_minutes", "steps"],
  "properties": {
    "wizard_key":         { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
    "version":            { "type": "integer", "minimum": 1 },
    "audience":           { "type": "array", "items": { "enum": ["operator","tenant_admin","teacher","parent","student","staff"] }, "minItems": 1 },
    "label_token":        { "type": "string", "pattern": "^wizards\\.[a-z_]+\\.label$" },
    "description_token":  { "type": "string", "pattern": "^wizards\\.[a-z_]+\\.description$" },
    "icon_class":         { "type": "string", "pattern": "^rmc-icon-[a-z-]+$" },
    "estimated_minutes":  { "type": "integer", "minimum": 1, "maximum": 60 },
    "gates": {
      "type": "object",
      "properties": {
        "permission_codename":     { "type": "string" },
        "feature_flag":            { "type": "string" },
        "prerequisite_wizard":     { "type": "string" },
        "min_setup_health_score":  { "type": "integer", "minimum": 0, "maximum": 100 },
        "requires_country_in":     { "type": "array", "items": { "type": "string", "pattern": "^[A-Z]{2}$" } }
      }
    },
    "ai": {
      "type": "object",
      "properties": {
        "smart_defaults":          { "type": "boolean", "default": false },
        "branch_rationale":        { "type": "boolean", "default": false },
        "translate_mesh":          { "type": "boolean", "default": false },
        "natural_language_intake": { "type": "boolean", "default": false }
      }
    },
    "steps": {
      "type": "array",
      "minItems": 1,
      "maxItems": 8,
      "items": { "$ref": "#/$defs/Step" }
    }
  },
  "$defs": {
    "Step": {
      "type": "object",
      "required": ["key", "label_token", "input_type"],
      "properties": {
        "key":              { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
        "label_token":      { "type": "string" },
        "description_token":{ "type": "string" },
        "input_type":       { "enum": [
          "single_choice","multi_choice","text","long_text","number","decimal",
          "boolean","file_upload","image_upload","color_picker","domain_input",
          "structured_form","draw_on_map","csv_mapping","rich_select",
          "ranked_list","key_value_pairs","datetime","duration"
        ]},
        "options_resolver": { "type": "string", "pattern": "^apps\\.[a-z_.]+::[a-z_]+$" },
        "fields":           { "type": "array", "items": { "$ref": "#/$defs/StructuredField" } },
        "next_step_resolver":{ "type": "string", "pattern": "^apps\\.[a-z_.]+::[a-z_]+$" },
        "branches":         { "type": "object", "additionalProperties": { "type": "string" } },
        "ai_recommend": {
          "type": "object",
          "properties": {
            "enabled":      { "type": "boolean", "default": false },
            "context_keys": { "type": "array", "items": { "type": "string" } },
            "max_tokens":   { "type": "integer", "minimum": 100, "maximum": 2000 },
            "prompt_template_key": { "type": "string" }
          }
        },
        "validation": {
          "type": "object",
          "properties": {
            "required":     { "type": "boolean", "default": false },
            "max_length":   { "type": "integer" },
            "min_length":   { "type": "integer" },
            "pattern":      { "type": "string" },
            "decimal_min":  { "type": "string" },
            "decimal_max":  { "type": "string" },
            "allowed_extensions": { "type": "array", "items": { "type": "string" } },
            "max_file_bytes": { "type": "integer" }
          }
        },
        "persistence": {
          "type": "object",
          "properties": {
            "target":     { "enum": ["site_settings","runtime_defaults","lifecycle_stage","companion_receiver","custom"] },
            "field_path": { "type": "string" },
            "writer":     { "type": "string", "pattern": "^apps\\.[a-z_.]+::[a-z_]+$" }
          }
        },
        "estimated_seconds": { "type": "integer", "minimum": 10, "maximum": 600 },
        "mobile_layout":     { "enum": ["default","full_bleed","split","compact"] }
      },
      "oneOf": [
        { "required": ["branches"], "not": { "required": ["next_step_resolver"] } },
        { "required": ["next_step_resolver"], "not": { "required": ["branches"] } },
        { "not": { "anyOf": [{ "required": ["branches"] }, { "required": ["next_step_resolver"] }] } }
      ]
    },
    "StructuredField": {
      "type": "object",
      "required": ["name","label_token","type"],
      "properties": {
        "name":         { "type": "string", "pattern": "^[a-z][a-z0-9_]*$" },
        "label_token":  { "type": "string" },
        "type":         { "enum": ["text","number","decimal","boolean","email","phone","date","select","textarea","color","file"] },
        "required":     { "type": "boolean", "default": false },
        "default":      {},
        "choices_resolver": { "type": "string" },
        "validation":   { "type": "object" }
      }
    }
  }
}
```

**Key invariants:**

1. `oneOf` on step: a step has EITHER `branches` OR `next_step_resolver` OR neither (= sequential to next step in array). Never both.
2. All `*_token` fields point at i18n keys, not literal strings. Validator imports `django.utils.translation.gettext_lazy` and confirms the key exists in `apps/setup_studio/locale_wizard_keys.py` registry.
3. All `options_resolver` / `next_step_resolver` / `writer` dotted paths import successfully at startup. Failure = `WizardSchemaError` at module load, NOT at first request.
4. `gates.requires_country_in` short-circuits wizard visibility for tenants outside the listed ISO-3166 country codes.
5. `estimated_minutes` summed across all steps must roughly match `sum(step.estimated_seconds) / 60` ± 50%. Validator emits a warning, not an error.

---

## §3 State model — example records + cache JS API

### §3.1 `SetupProgress.step_state` after a tenant completes Whitelabel + half-fills Sovereignty

```jsonc
{
  "select_experience_template": {
    "template_key": "operator_pack_kerala_state_board_ml",
    "applied_at": "2026-05-26T11:14:02Z"
  },
  "wizards": {
    "cross_platform_whitelabel_branding": {
      "current_step_key": null,
      "answers": {
        "brand_asset_injection": {
          "logo_file_id": 4821,
          "favicon_file_id": 4822,
          "social_share_image_file_id": null
        },
        "typography_style_scaling": {
          "palette_key": "kerala_heritage_emerald",
          "primary_color_hex": "#0d7a4d",
          "secondary_color_hex": "#f4b840",
          "type_scale_anchor": "comfortable",
          "wcag_contrast_pass": true
        },
        "custom_domain_mapping": {
          "tenant_domain": "portal.stmary-tvm.example.org",
          "ssl_status": "provisioned",
          "verified_at": "2026-05-26T11:23:17Z"
        },
        "progressive_app_generator": {
          "manifest_compiled": true,
          "manifest_sha256": "a3f9...",
          "compiled_at": "2026-05-26T11:25:01Z"
        }
      },
      "completed": [
        "brand_asset_injection",
        "typography_style_scaling",
        "custom_domain_mapping",
        "progressive_app_generator"
      ],
      "schema_version": 1,
      "ai_recommendations_cache": {
        "typography_style_scaling": {
          "suggestions": { "palette_key": "kerala_heritage_emerald" },
          "rationale_text_token": "wizards.whitelabel.rationale.kerala_emerald",
          "confidence": { "palette_key": 0.91 },
          "computed_at": "2026-05-26T11:19:44Z"
        }
      },
      "started_at": "2026-05-26T11:12:00Z",
      "last_modified": "2026-05-26T11:25:01Z",
      "ai_request_count": 3,
      "ai_fallback_count": 0,
      "completed_at": "2026-05-26T11:25:01Z"
    },
    "multi_campus_local_sovereignty": {
      "current_step_key": "statutory_alignment",
      "answers": {
        "jurisdiction_mapping": {
          "country_code": "IN",
          "state_code": "IN-KL",
          "data_residency_region": "ap-south-1"
        },
        "dynamic_core_routing": {
          "pii_database_region": "ap-south-1",
          "cdn_pop": "mumbai",
          "applied_at": "2026-05-26T11:31:08Z"
        },
        "cultural_vocabulary_injection": {
          "vocabulary_pack_key": "in_kl_state_board_ml",
          "term_overrides": {
            "Student": "വിദ്യാർത്ഥി",
            "Teacher": "അദ്ധ്യാപകൻ",
            "Principal": "പ്രധാന അദ്ധ്യാപകൻ"
          }
        }
      },
      "completed": ["jurisdiction_mapping", "dynamic_core_routing", "cultural_vocabulary_injection"],
      "schema_version": 1,
      "ai_recommendations_cache": {},
      "started_at": "2026-05-26T11:27:00Z",
      "last_modified": "2026-05-26T11:32:10Z",
      "ai_request_count": 2,
      "ai_fallback_count": 0
    }
  }
}
```

### §3.2 `static/js/rmc-wizard-state-cache.js` public API

```javascript
window.RmcWizardStateCache = (function () {
  'use strict';

  const SCHEMA_VERSION = 1;
  const TTL_DAYS = 30;
  const KEY_PREFIX = 'rmc.wizard';

  function makeKey(schoolId, wizardKey) { /* `${KEY_PREFIX}.${schoolId}.${wizardKey}.v${SCHEMA_VERSION}` */ }

  return {
    save: function (schoolId, wizardKey, state) { /* ... */ },
    load: function (schoolId, wizardKey) { /* returns null if absent, expired, or schema mismatch */ },
    clear: function (schoolId, wizardKey) { /* ... */ },
    clearAll: function (schoolId) { /* iterates localStorage, drops matching prefix */ },
    isPresent: function (schoolId, wizardKey) { /* boolean */ },
    getSavedAtIso: function (schoolId, wizardKey) { /* iso string or null */ },
    SCHEMA_VERSION: SCHEMA_VERSION,
  };
})();
```

**Invariants:**

- Never stores PII. Server filters payload before sending to client; `_sanitize_context` runs both server-side and client-side as defense in depth.
- Schema-version mismatch on load → clear + return null (silently — no console.warn).
- `last_modified` timestamp + TTL check on every load.
- Wrapped in try/catch — localStorage quota exceeded → emit synthetic event `rmc.wizard.cache.quota_exceeded` for telemetry, return null.

### §3.3 Server-side cache restore flow

```
User opens /school/studio/wizards/cross_platform_whitelabel_branding/typography_style_scaling/
  │
  ▼
TenantWizardView.get():
  - load SetupProgress.step_state["wizards"]["cross_platform_whitelabel_branding"]
  - serialize PII-safe slice → context["server_state"]
  - render template
  │
  ▼ (template)
  - inline data block: window.__rmc_wizard_initial_state = {{ server_state | json_script }};
  - on DOM ready:
    cachedState = RmcWizardStateCache.load(schoolId, wizardKey);
    if (cachedState && cachedState.last_modified > server_state.last_modified):
      show "you have unsaved local changes from <time>" banner with [Restore] [Discard] buttons
  │
  ▼ (form submit)
  - server applies answer
  - server returns redirect to next step
  - client clears cache for completed step's answers (or all on wizard completion)
```

---

## §4 URL + template + permission map

### §4.1 URLs

| Path | View | Permission marker |
|---|---|---|
| `GET /super/wizards/` | `OperatorWizardIndexView` | `# rbac-allow: super-staff-wizard-index` |
| `GET /super/wizards/<wizard_key>/` | `OperatorWizardView` (redirects to current step) | `# rbac-allow: super-staff-wizard-engine-access` |
| `GET /super/wizards/<wizard_key>/<step_key>/` | `OperatorWizardView` | same |
| `POST /super/wizards/<wizard_key>/<step_key>/` | `OperatorWizardView` | same |
| `POST /super/wizards/<wizard_key>/reset/` | `WizardStateResetView` | `# rbac-allow: super-staff-wizard-reset-state` |
| `GET /school/studio/wizards/` | `TenantWizardIndexView` | `# rbac-allow: tenant-admin-wizard-index-via-role-registry` |
| `GET /school/studio/wizards/<wizard_key>/` | `TenantWizardView` | `# rbac-allow: tenant-admin-wizard-engine-access-via-role-registry` |
| `GET /school/studio/wizards/<wizard_key>/<step_key>/` | `TenantWizardView` | same |
| `POST /school/studio/wizards/<wizard_key>/<step_key>/` | `TenantWizardView` | same |
| `POST /school/studio/wizards/<wizard_key>/reset/` | `WizardStateResetView` | `# rbac-allow: tenant-admin-wizard-reset-state` |
| `POST /api/wizards/ai/recommend/` | `WizardAIRecommendView` (AJAX) | `# rbac-allow: authenticated-user-wizard-ai-recommend` |
| `GET /api/wizards/state/<wizard_key>/` | `WizardStateExportView` (DSAR + audit) | `# rbac-allow: tenant-admin-wizard-state-export-self-scope` |

### §4.2 Templates

| Template | Extends | Purpose |
|---|---|---|
| `templates/setup_studio/operator_wizard.html` | `control_plane_skeleton.html` | Operator shell variant |
| `templates/setup_studio/tenant_wizard.html` | `portal_base.html` | Tenant shell variant |
| `templates/setup_studio/partials/wizard_stepper.html` | — | Top progress bar; auto-collapses |
| `templates/setup_studio/partials/wizard_nav.html` | — | Back/save-draft/next buttons |
| `templates/setup_studio/partials/wizard_help_rail.html` | — | Right-side copilot rail |
| `templates/setup_studio/partials/wizard_ai_rationale.html` | — | Collapsible AI rationale box |
| `templates/setup_studio/partials/wizard_state_restore_banner.html` | — | "You have unsaved local changes" |
| `templates/setup_studio/inputs/<input_type>.html` | — | One partial per `input_type` (18 partials) |
| `templates/setup_studio/inputs/single_choice.html` | — | Radio cards |
| `templates/setup_studio/inputs/multi_choice.html` | — | Checkbox cards |
| `templates/setup_studio/inputs/text.html` | — | Single-line input |
| `templates/setup_studio/inputs/long_text.html` | — | Textarea |
| `templates/setup_studio/inputs/structured_form.html` | — | Multi-field form |
| `templates/setup_studio/inputs/draw_on_map.html` | — | Leaflet-based geo-fence drawer |
| `templates/setup_studio/inputs/csv_mapping.html` | — | Two-column drag-and-drop mapper |
| `templates/setup_studio/inputs/key_value_pairs.html` | — | Add-row table for term overrides etc. |
| `templates/setup_studio/inputs/color_picker.html` | — | HSL + hex + WCAG check |
| `templates/setup_studio/inputs/domain_input.html` | — | Domain entry with DNS check |
| `templates/setup_studio/inputs/file_upload.html` | — | Drag-drop with extension + size validation |
| `templates/setup_studio/inputs/image_upload.html` | — | File upload + preview thumbnail |
| `templates/setup_studio/inputs/rich_select.html` | — | Searchable dropdown w/ avatar/icon per option |
| `templates/setup_studio/inputs/ranked_list.html` | — | Drag-to-reorder list |
| `templates/setup_studio/inputs/datetime.html` | — | Date+time picker (timezone-aware) |
| `templates/setup_studio/inputs/duration.html` | — | Days/hours/minutes triplet |
| `templates/setup_studio/inputs/decimal.html` | — | Money input (Decimal only) |
| `templates/setup_studio/inputs/number.html` | — | Integer input |
| `templates/setup_studio/inputs/boolean.html` | — | Toggle |

### §4.3 Permission matrix

| Wizard | Operator can run? | Tenant admin can run? | Teacher? | Parent? | Student? | Staff? |
|---|---|---|---|---|---|---|
| P1.1 Whitelabel & Branding | yes | yes | no | no | no | no |
| P1.2 Multi-Campus Sovereignty | yes | no | no | no | no | no |
| P1.3 Polymorphic Grading | yes | yes | no | no | no | no |
| P1.4 Legacy Data Extraction | yes | yes (with `migration_intent` set) | no | no | no | no |
| P1.5 AI Helpcenter | no | yes | no | no | no | no |
| P1.PARENT | no | no | no | yes | no | no |
| P1.STAFF | no | no | no | no | no | yes |
| P2.1 FinTech & Tax Matrix | yes | yes (gated on billing.change_paymentsettings) | no | no | no | no |
| P2.2 Activity & Asset Marketplace | yes | yes | no | no | no | no |
| P2.3 Cashless Campus POS | yes | yes | no | no | no | no |
| P2.4 Safeguarding/Incident/Medical | yes | yes (gated on compliance role) | no | no | no | no |
| P2.5 Omnichannel Comms | yes | yes | no | no | no | no |
| P3.1 JIT Compliance | yes | no | no | no | no | no |
| P3.2 HR/Shift/Substitute | yes | yes (gated on hr role) | no | no | no | no |
| P3.3 Board Reporting | yes | yes (gated on principal/proprietor) | no | no | no | no |
| P3.4 Self-Healing Observability | yes | no | no | no | no | no |
| P3.5 Multi-Campus Scheduling | yes | yes | no | no | no | no |
| P3.6 Field Trip Coordinator | no | yes | yes | no | no | no |
| P3.7 Graduation Pathway | no | yes (configure) | no | no | yes (run for self) | no |

---

## §5 AI prompt library

All prompts live in `apps/setup_studio/ai_prompts.py` keyed by `prompt_template_key`. Routed through `services.ai_helpers.invoke_with_request`.

### §5.1 Universal prompt envelope

Every prompt is wrapped in:

```
SYSTEM:
You are the configuration assistant for RunMyCampus, a multi-tenant school
management platform. Your job is to suggest sensible defaults for setup
wizards based on the school's country, type, language, and prior answers.

CONSTRAINTS:
- Output VALID JSON matching the requested schema. No prose outside the JSON.
- Use ONLY values from the provided options list. If unsure, return an empty
  suggestion object with confidence 0.
- NEVER invent country codes, currency codes, payment vendor names, or
  regulatory body names. Only use what is given in the context.
- NEVER include personally identifiable information in rationale text.
- If you cannot determine a confident default, say so — fallback is acceptable.

USER:
<task-specific prompt body>

CONTEXT:
{{ sanitized_context_json }}

OPTIONS:
{{ resolved_options_json }}

SCHEMA (your output must match):
{{ output_schema_json }}
```

### §5.2 Specific prompt template keys

| Key | Used by step | Output schema |
|---|---|---|
| `prompt.whitelabel.suggest_palette` | P1.1 typography_style_scaling | `{palette_key, primary_color_hex, secondary_color_hex, confidence}` |
| `prompt.sovereignty.suggest_jurisdiction` | P1.2 jurisdiction_mapping | `{country_code, state_code, data_residency_region, confidence}` |
| `prompt.sovereignty.suggest_vocabulary_pack` | P1.2 cultural_vocabulary_injection | `{vocabulary_pack_key, term_override_count, confidence}` |
| `prompt.grading.suggest_track` | P1.3 track_selection | `{track_keys, assessment_metric_default, confidence}` |
| `prompt.migration.classify_csv_columns` | P1.4 field_vector_mapping | `{mappings: [{source_column, canonical_field, confidence}], unmapped: []}` |
| `prompt.helpcenter.tag_policy_section` | P1.5 context_tagging | `{audience_tags, applicable_grades, confidence}` |
| `prompt.fintech.suggest_apm` | P2.1 apm_integration | `{recommended_apm_key, fallback_apm_keys, confidence, rationale_token}` |
| `prompt.fintech.suggest_split_allocation` | P2.1 split_ledger_allocation | `{allocations: [{purpose, percentage}], confidence}` |
| `prompt.marketplace.suggest_storefront_categories` | P2.2 storefront_blueprinting | `{category_keys, confidence}` |
| `prompt.pos.suggest_terminal_layout` | P2.3 terminal_registration | `{layout_key, confidence}` |
| `prompt.safeguarding.suggest_routing` | P2.4 legal_protocol_routing | `{routing_path_key, confidence}` |
| `prompt.comms.translate_template` | P2.5 ai_translation_mapping | `{translations: {<locale>: <text>}, confidence}` |
| `prompt.compliance.suggest_access_trigger` | P3.1 assumed_access_trigger | `{trigger_keys, confidence}` |
| `prompt.hr.suggest_labor_contract` | P3.2 labor_contract_profile | `{contract_template_key, overtime_threshold_hours, confidence}` |
| `prompt.analytics.suggest_kpis` | P3.3 metric_kpi_assembly | `{kpi_keys, confidence}` |
| `prompt.observability.suggest_thresholds` | P3.4 threshold_definition | `{error_threshold, latency_threshold_ms, confidence}` |
| `prompt.scheduling.solve_conflicts` | P3.5 ai_conflict_solver | `{schedule_proposals: [{...}], conflicts_remaining: int, confidence}` |
| `prompt.fieldtrip.suggest_costs` | P3.6 logistics_definition | `{cost_per_student_decimal, cost_breakdown: {...}, confidence}` |
| `prompt.pathway.suggest_courses` | P3.7 dynamic_class_matcher | `{course_keys, schedule_fit_score, confidence}` |
| `prompt.universal.branch_rationale` | any branched step | `{rationale_text, confidence}` |
| `prompt.universal.natural_language_intake` | any step accepting free text | `{parsed_fields: {...}, unresolved_phrases: [], confidence}` |

### §5.3 Example prompt body — P2.1 APM suggestion

```
Recommend the most appropriate Alternative Payment Method (APM) for a school
collecting tuition fees based on the school's country and settlement currency.

Consider:
- Which APMs are commonly used in the country for B2C fee collection
- Whether the APM supports recurring billing (school fees are recurring)
- Whether the APM supports the school's settlement currency without FX overhead
- Whether the APM has a public API the platform can integrate

Return the top recommendation plus up to 3 fallbacks.

CONTEXT:
{
  "country_code": "IN",
  "settlement_currency": "INR",
  "school_type": "k12",
  "school_size_band": "medium",
  "prior_answers": {
    "settlement_destination": {
      "country_code": "IN",
      "currency": "INR"
    }
  }
}

OPTIONS:
[
  {"value": "upi_rupay", "label_token": "wizards.fintech.apm.upi", "metadata": {"countries": ["IN"], "recurring": true, "api": true}},
  {"value": "pix_brcode", "label_token": "wizards.fintech.apm.pix", "metadata": {"countries": ["BR"], "recurring": true, "api": true}},
  {"value": "mpesa_stk", "label_token": "wizards.fintech.apm.mpesa", "metadata": {"countries": ["KE","TZ","UG"], "recurring": false, "api": true}},
  {"value": "stripe_card", "label_token": "wizards.fintech.apm.stripe_card", "metadata": {"countries": ["*"], "recurring": true, "api": true}}
]

SCHEMA:
{
  "recommended_apm_key": "string (one of the option values)",
  "fallback_apm_keys": "array of strings (up to 3 option values)",
  "confidence": "number 0..1",
  "rationale_token": "string (one of wizards.fintech.rationale.* keys)"
}
```

### §5.4 Failure-mode contract

If AI response:
- Not valid JSON → retry once with shorter prompt → fallback to deterministic rule.
- Missing required schema fields → fallback.
- References option values NOT in OPTIONS list → fallback (model hallucinated).
- Confidence < 0.5 → present as "weak suggestion, please confirm" UI affordance.
- Latency > 5s → cancel, fallback.

Fallback for each prompt key = a deterministic Python function in `apps/setup_studio/ai_fallbacks.py`. Naming: `fallback_<prompt_key_underscored>`. Example: `fallback_prompt_fintech_suggest_apm(context, options) -> dict` returns the same schema as the AI would.

---

## §6 The 18 wizards — full step-by-step specs

Every wizard below follows the same template:
- **Meta:** wizard_key, audience, estimated_minutes, gates, AI mode
- **Each step:** key, title (token), input_type, fields, options resolver, AI behavior, validation, persistence target, next step, failure modes

### §6.1 P1.0 — Engine bootstrap (no UI)

**Not a wizard.** This is the engine itself. Implementation order — see §12.

### §6.2 P1.1 — Cross-Platform Whitelabel & Branding

**Meta:**
- `wizard_key`: `cross_platform_whitelabel_branding`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 8
- `icon_class`: `rmc-icon-brush`
- `gates`: `{permission_codename: "brand_experience.change_brandsettings"}`
- `ai`: `{smart_defaults: true, branch_rationale: false, translate_mesh: false}`

#### Step 1 — `brand_asset_injection`

- **Title:** `wizards.whitelabel.step.brand_asset_injection.label`
- **Input type:** `structured_form`
- **Fields:**
  - `logo_file` — file, required, allowed: png/svg/webp, max 2 MB
  - `favicon_file` — file, required, allowed: png/svg/ico, max 100 KB
  - `social_share_image_file` — file, optional, allowed: png/jpeg, max 3 MB, recommended 1200×630
  - `alt_text` — text, required, max 120 chars
- **AI:** none (file upload only)
- **Validation:**
  - File extensions enforced server-side via `validate_file_extension`
  - Image dimensions checked via Pillow; logo aspect ratio between 1:1 and 4:1
  - SVG sanitized via `lxml` to strip `<script>` tags and `on*` attributes
- **Persistence:** `apps/brand_experience/services::install_brand_assets(school, logo_id, favicon_id, social_id, alt_text)` — writes to `BrandAsset` table + invalidates `SiteSettings` cache.
- **Next step:** sequential → `typography_style_scaling`
- **Failure modes:**
  - SVG with embedded script → reject, surface `wizards.errors.svg_script_blocked`
  - File size exceeded → reject, surface `wizards.errors.file_too_large` with `{max_mb}` interpolation

#### Step 2 — `typography_style_scaling`

- **Title:** `wizards.whitelabel.step.typography_style_scaling.label`
- **Input type:** `structured_form`
- **Fields:**
  - `palette_key` — select, required, options from `apps.brand_experience.palette_registry::list_heritage_palettes`
  - `primary_color_hex` — color, required, auto-fills from `palette_key`
  - `secondary_color_hex` — color, required, auto-fills from `palette_key`
  - `type_scale_anchor` — select, required, choices: `compact|comfortable|spacious`
- **AI:** `smart_defaults` enabled, prompt key `prompt.whitelabel.suggest_palette`, context_keys `["country_code","school_type","primary_language"]`
- **Validation:**
  - WCAG AA contrast ratio ≥ 4.5:1 between primary and `--surface-bg` and between secondary and primary
  - Hex format `^#[0-9A-Fa-f]{6}$`
  - If WCAG fails, suggest adjusted hex via `apps/brand_experience/wcag_helper::auto_adjust_for_contrast`
- **Persistence:** writes to `RuntimeDefaults` typed columns (`brand_primary_color`, `brand_secondary_color`, `brand_type_scale_anchor`, `brand_palette_key`) per cascade contract.
- **Next step:** sequential → `custom_domain_mapping`
- **Failure modes:**
  - WCAG fail + user dismisses suggested adjustment → write anyway, emit `wizard.whitelabel.wcag_override_accepted` metric (operator can audit later)

#### Step 3 — `custom_domain_mapping`

- **Title:** `wizards.whitelabel.step.custom_domain_mapping.label`
- **Input type:** `domain_input`
- **Fields:**
  - `tenant_domain` — text, required, pattern `^([a-z0-9-]+\.)+[a-z]{2,}$`, max 253 chars
- **AI:** none
- **Validation:**
  - DNS CNAME pre-check via `apps/tenancy/services::verify_dns_pointing_to_platform(domain)` — staging vs prod handled by `RMC_DEPLOYMENT_PROFILE`
  - Domain must not be on the public suffix list at top level
  - Domain not already claimed by another tenant (`School.objects.filter(custom_domain=domain).exists()` with `# tenant-isolation-allow: domain-uniqueness-check-cross-tenant-by-design` marker)
- **Persistence:** writes to `School.custom_domain` and triggers SSL provisioning via existing platform infra (out-of-scope job, just enqueued).
- **Next step:** sequential → `progressive_app_generator`
- **Failure modes:**
  - DNS not pointing → soft warning, allow proceed (provisioning will retry)
  - Domain claimed → hard reject with `wizards.errors.domain_already_claimed`
  - SSL provisioning failure → out-of-band notification (not blocking)

#### Step 4 — `progressive_app_generator`

- **Title:** `wizards.whitelabel.step.progressive_app_generator.label`
- **Input type:** `structured_form`
- **Fields:**
  - `app_short_name` — text, required, max 12 chars
  - `app_long_name` — text, required, max 45 chars
  - `splash_background_color` — color, auto-fills from prior step's `primary_color_hex`
  - `splash_text_color` — color, auto-computed for WCAG AA against background
  - `theme_color` — color, auto-fills from `primary_color_hex`
- **AI:** none
- **Validation:** standard text length + color format checks
- **Persistence:** compiles manifest via `apps/brand_experience/pwa_manifest::compile_manifest(school)`; writes manifest JSON to `MEDIA_ROOT/manifests/<school_id>.webmanifest`; updates `School.pwa_manifest_compiled_at`.
- **Next step:** end of wizard
- **Failure modes:**
  - PWA manifest schema violation → emit `wizard.whitelabel.pwa_manifest_invalid` and surface the schema error keys
  - CDN deployment failure → deferred (out-of-scope per plan §12.10)

### §6.3 P1.2 — Multi-Campus Local Sovereignty

**Meta:**
- `wizard_key`: `multi_campus_local_sovereignty`
- `audience`: `["operator"]`
- `estimated_minutes`: 12
- `icon_class`: `rmc-icon-globe`
- `gates`: `{permission_codename: "tenancy.change_school_residency"}`
- `ai`: `{smart_defaults: true, branch_rationale: true, natural_language_intake: true}`

#### Step 1 — `jurisdiction_mapping`

- **Input type:** `structured_form`
- **Fields:**
  - `country_code` — select, required, options from `apps.platform_runtime.country_registry::list_all_countries`
  - `state_code` — select, conditional on `country_code` being in `IN|US|BR|DE|CA|AU|MX|NG`, options from `apps.platform_runtime.country_registry::list_states_for_country`
  - `data_residency_region` — select, required, options from `apps.tenancy.regions::list_compliant_regions_for_country`
- **AI:** smart_defaults with context `["primary_language","accept_language_header","tenant_billing_country"]`
- **Validation:**
  - Country code in ISO-3166-1 alpha-2
  - State code in ISO-3166-2 (only when conditional applies)
  - Data residency region must be in `list_compliant_regions_for_country(country_code)` — server enforces match
- **Persistence:** writes to `School.country_code`, `School.state_code`, `School.data_residency_region`.
- **Next step:** sequential → `dynamic_core_routing`
- **Failure modes:**
  - Mismatch between country and residency region → reject with `wizards.errors.country_residency_mismatch`
  - Region not currently provisioned (e.g. tenant chose `me-central-1` but platform doesn't have that region live) → soft block with `wizards.errors.region_not_live` + provide ETA from `apps.tenancy.regions::region_eta`

#### Step 2 — `dynamic_core_routing`

- **Input type:** `single_choice`
- **Options:** dynamically computed via `apps.tenancy.routing::list_routing_profiles_for_residency(residency_region)` — typically `default|edge_aggressive|legal_sovereign|hybrid`
- **AI:** branch_rationale enabled — explains what each profile means for the chosen country
- **Validation:** value in resolved options
- **Persistence:** writes to `School.routing_profile`; triggers async re-shard job via `apps/tenancy/tasks::reshard_school_pii(school_id)` (idempotent).
- **Next step:** branches:
  - `legal_sovereign` → `cultural_vocabulary_injection` (skip generic, go straight to localized vocabulary)
  - other → `cultural_vocabulary_injection`
- **Failure modes:**
  - Re-shard job failure → tenant remains on prior shard, surfaces banner in Studio OS Control mode

#### Step 3 — `cultural_vocabulary_injection`

- **Input type:** `structured_form`
- **Fields:**
  - `vocabulary_pack_key` — select, required, options from `apps.locale.vocabulary_packs::list_packs_for_country_and_language(country_code, primary_language)`
  - `term_overrides` — key_value_pairs, optional, max 50 entries, each pair `{english_term, localized_term}` with `english_term` from `apps.locale.vocabulary_packs::list_canonical_terms()`
- **AI:** smart_defaults with context `["country_code","state_code","primary_language","school_type"]`, prompt key `prompt.sovereignty.suggest_vocabulary_pack`
- **Validation:** each override's `english_term` in canonical list; localized term max 80 chars
- **Persistence:** writes to `SiteSettings.cockpit_payload["vocabulary"]` (Wave 8 cascade pattern); cache invalidates via `lru_cached.clear_cache()` at end of write.
- **Next step:** sequential → `statutory_alignment`
- **Failure modes:**
  - Unknown canonical term → reject the override (rest of overrides applied)
  - Localized term exceeds 80 chars → reject with `wizards.errors.localized_term_too_long`

#### Step 4 — `statutory_alignment`

- **Input type:** `multi_choice`
- **Options:** from `apps.compliance.statutory_registry::list_statutory_schemas_for_country(country_code, state_code)` — e.g. UDISE+ India, Dapodik Indonesia, NSLP United States, FERPA United States, GDPR EU member states
- **AI:** branch_rationale — explains what each schema requires
- **Validation:** at least one selection if country has mandatory schemas, otherwise optional
- **Persistence:**
  - Writes to `apps.compliance.models::SchoolStatutoryEnrollment` rows (one per selected schema)
  - Triggers reporting-template installation via `apps.compliance.services::install_statutory_templates(school, schema_keys)`
- **Next step:** end of wizard
- **Failure modes:**
  - Country has mandatory schema (e.g. India K-12 must have UDISE+) but operator unchecked it → soft warning with `wizards.warnings.mandatory_schema_skipped` + allow proceed with audit note

### §6.4 P1.3 — Polymorphic Grading & Curricula

**Meta:**
- `wizard_key`: `polymorphic_grading_curricula`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 10
- `icon_class`: `rmc-icon-chart-rising`
- `gates`: `{permission_codename: "academics.change_curriculum"}`
- `ai`: `{smart_defaults: true, branch_rationale: true}`

#### Step 1 — `track_selection`

- **Input type:** `multi_choice`
- **Options:** `apps.academics.track_registry::list_tracks_for_country(country_code, state_code)` — IB, GCE A-Levels, AP, Cambridge IGCSE, Local Ministry K-12, Vocational, Montessori, etc.
- **AI:** smart_defaults with context `["country_code","state_code","school_type","grade_levels_offered"]`
- **Validation:** at least 1 selection; mutually-exclusive pairs flagged (e.g. can't pick both "Local Ministry K-12" and "International Baccalaureate" for same student cohort — soft warning, not block)
- **Persistence:** writes to `apps.academics.models::TrackEnrollment` rows scoped to school
- **Next step:** sequential → `assessment_metrics`

#### Step 2 — `assessment_metrics`

- **Input type:** `structured_form`
- **Fields:**
  - `grading_scale` — select, required, choices: `gpa_4|gpa_5|percentage|letter|competency|points_100|points_1000`
  - `pass_threshold` — decimal, required, validation depends on `grading_scale`
  - `rubric_levels` — number, required when `grading_scale = competency`, between 3 and 7
- **AI:** branch_rationale explaining tradeoffs
- **Validation:** `decimal_range` enforces scale-appropriate bounds (e.g. GPA 4 allows 0.0-4.0)
- **Persistence:** writes to `apps.evals.models::AssessmentConfiguration`
- **Next step:** sequential → `course_schema_association`

#### Step 3 — `course_schema_association`

- **Input type:** `csv_mapping` (visual two-column drag-drop)
- **Left column:** canonical curriculum subjects per chosen tracks
- **Right column:** local-mandatory subjects (e.g. Arabic+Islamic Studies for MENA, Filipino for PH, Vietnamese for VN)
- **AI:** smart_defaults pre-suggests mappings based on country + track
- **Validation:** every local-mandatory subject must be mapped
- **Persistence:** writes to `apps.academics.models::SubjectMapping`
- **Next step:** sequential → `transcript_factory`

#### Step 4 — `transcript_factory`

- **Input type:** `rich_select`
- **Options:** transcript templates from `apps.evals.transcript_registry::list_templates_for_track(track_keys)` — each option has preview thumbnail + signature scheme (Ed25519 / RSA-PSS-SHA256) + format (PDF/A-3, SVG, JSON-LD diploma)
- **AI:** branch_rationale per template
- **Validation:** template must support all selected tracks
- **Persistence:** writes to `apps.evals.models::TranscriptTemplateAssignment`; pre-renders one sample transcript to verify pipeline works
- **Next step:** end of wizard
- **Failure modes:** sample render fail → reject template selection, surface error from PDF pipeline

### §6.5 P1.4 — Legacy Data Extraction Pipeline

**Meta:**
- `wizard_key`: `legacy_data_extraction_pipeline`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 15-25 depending on data volume
- `icon_class`: `rmc-icon-import`
- `gates`: `{permission_codename: "migration_cloud.change_bundle", prerequisite_wizard: null}` (note: deliberately no prereq — fresh schools can migrate immediately)
- `ai`: `{smart_defaults: true, natural_language_intake: false}`

#### Step 1 — `legacy_upload`

- **Input type:** `file_upload`
- **Fields:**
  - `legacy_files` — multiple, allowed: csv/xlsx/zip, max 100 MB each, max 50 files total
  - `vendor_hint` — select, optional, options from `apps.migration_cloud.vendors::list_supported_vendors()` — PowerSchool, Blackbaud, Veracross, Alma, FACTS, Skyward, Other
- **AI:** none (file upload)
- **Validation:**
  - Files routed to `apps.migration_cloud.companion_receiver` via existing wave-shipped infrastructure
  - Each file: detect_vendor() from `apps.migration_cloud.extractors.detect_vendor` — confirms vendor_hint or surfaces mismatch
  - File-level validation per vendor processor (PowerSchool CSV, Blackbaud OData export, etc.)
- **Persistence:** Creates `CompanionUploadReceipt` rows; ciphertext blobs in `CompanionCiphertextBlob`
- **Next step:** sequential → `field_vector_mapping`
- **Failure modes:**
  - Vendor mismatch → soft warning, allow override with audit note
  - File too large → reject with `wizards.errors.file_too_large`
  - Encrypted file failed decryption → surface specific receipt ID

#### Step 2 — `field_vector_mapping`

- **Input type:** `csv_mapping`
- **Left column:** detected source columns (per file or aggregated)
- **Right column:** canonical fields per `apps.migration_cloud.canonical_headers::DOMAIN_CANONICAL_HEADERS`
- **AI:** smart_defaults with `prompt.migration.classify_csv_columns` — pre-suggests mappings per canonical-headers SOT
- **Validation:**
  - Every required canonical field (students.full_name, students.date_of_birth, students.grade_level) must be mapped
  - Type compatibility (date column maps to date canonical, not text)
- **Persistence:** writes to `apps.migration_cloud.models::FieldMappingDecision` per file
- **Next step:** sequential → `inline_error_cleanup`
- **Failure modes:**
  - Unmappable required field → block, surface `wizards.errors.required_field_unmapped`
  - Type incompatibility → soft warn with proposed coercion ("we'll parse MM/DD/YYYY → ISO; OK?")

#### Step 3 — `inline_error_cleanup`

- **Input type:** custom — paginated grid view (50 rows/page) of failed-validation rows from extraction
- **Fields per row:** the failing canonical field + reason + editable input
- **AI:** none in MVP (live regex suggestions deferred to Phase 4)
- **Validation:** per-canonical-field validators from `apps.migration_cloud.validators::CANONICAL_VALIDATORS`
- **Persistence:** writes corrected values back via `apps.migration_cloud.services::apply_inline_correction(receipt_id, row_id, field, new_value)`; audited via append-only `MigrationCloudAuditEvent`
- **Next step:** sequential → `identity_core_seeding`
- **Failure modes:**
  - User skips errors → soft block (must explicitly confirm "import 47 rows with errors")
  - Correction itself fails validation → re-prompt
- **Mobile layout:** `full_bleed` — grid takes full viewport on mobile, vertical-stack one field per row

#### Step 4 — `identity_core_seeding`

- **Input type:** `structured_form`
- **Fields:**
  - `seed_mode` — select, required, choices: `dry_run|commit_to_staging|commit_to_production`
  - `notify_guardians_email` — boolean, default false (creates parent portals)
  - `enable_offline_edge_files` — boolean, default false (deploys local edge data files)
- **AI:** branch_rationale per mode
- **Validation:**
  - `commit_to_production` requires explicit confirmation modal with school_slug typed back
  - `enable_offline_edge_files` requires `apps.tenancy.routing` profile to include edge tier
- **Persistence:** invokes `apps.migration_cloud.companion_receiver::CompanionDecryptHookView` flow → `apps.people.services::bulk_seed_identities` → emits audit events
- **Next step:** end of wizard
- **Failure modes:**
  - Seeding partial failure → wizard ends with completed_with_errors state; surface error report at `/super/migration/audit/?bundle=<id>`

### §6.6 P1.5 — AI Helpcenter Knowledge Injection

**Meta:**
- `wizard_key`: `ai_helpcenter_knowledge_injection`
- `audience`: `["tenant_admin"]`
- `estimated_minutes`: 10
- `icon_class`: `rmc-icon-book-open`
- `gates`: `{permission_codename: "customersuccess.change_helpcenter"}`
- `ai`: `{smart_defaults: true, natural_language_intake: false}`

#### Step 1 — `source_scraping`

- **Input type:** `file_upload`
- **Fields:**
  - `policy_documents` — multiple, allowed: pdf/docx/md/txt, max 25 MB each, max 20 files
- **AI:** none (file upload)
- **Validation:** file extension + size; PDF must be parseable (not encrypted)
- **Persistence:** stores files in `MEDIA_ROOT/helpcenter_sources/<school_id>/`; creates `apps.customersuccess.models::HelpcenterSource` rows
- **Next step:** sequential → `context_tagging`

#### Step 2 — `context_tagging`

- **Input type:** custom per-document tagging form
- **Per document:** AI-suggested tags + audience filter
- **Fields per source:**
  - `audience_tags` — multi_choice, options: `parent_middle_school|parent_high_school|teacher|student|all_parents|all_staff` etc.
  - `applicable_grades` — multi_choice, optional, options from school's grade range
  - `effective_date` — date, optional
  - `expires_at` — date, optional
- **AI:** smart_defaults with `prompt.helpcenter.tag_policy_section` per source
- **Validation:** at least 1 audience tag per source
- **Persistence:** updates `HelpcenterSource.audience_tags` JSON
- **Next step:** sequential → `fallback_redirection_matrix`

#### Step 3 — `fallback_redirection_matrix`

- **Input type:** `key_value_pairs`
- **Fields:**
  - Each pair: `unanswered_topic_pattern` (regex string) → `escalation_route` (one of: `bursar_sms|principal_email|headteacher_review|admissions_phone|operator_ticket`)
- **AI:** none
- **Validation:** regex compiles via `re.compile` server-side; escalation_route in allowed list
- **Persistence:** writes to `apps.customersuccess.models::HelpcenterFallbackRule` rows
- **Next step:** sequential → `core_validation_test`

#### Step 4 — `core_validation_test`

- **Input type:** custom sandbox test
- **UX:** chat-like interface where admin types 5 test queries; AI responds using indexed sources; admin grades each as accurate/partial/wrong
- **AI:** uses `services.ai_helpers.invoke_with_request` with `apps.customersuccess.services::helpcenter_query(query, school)` retrieving from source corpus
- **Validation:** at least 3 of 5 graded; if <60% accurate → block deployment with `wizards.errors.helpcenter_accuracy_too_low`
- **Persistence:** sets `apps.customersuccess.models::HelpcenterDeployment.deployed_at` only when grade passes
- **Next step:** end of wizard
- **Failure modes:**
  - All 5 wrong → wizard ends with status "needs source improvement"; suggests source-quality remediation
  - LLM unavailable → fallback to deterministic-rules helpcenter (no embeddings); wizard completes with `live_ai = false` flag

### §6.7 P1.PARENT — Parent persona onboarding

**Meta:**
- `wizard_key`: `parent_onboarding`
- `audience`: `["parent"]`
- `estimated_minutes`: 6
- `icon_class`: `rmc-icon-family`
- `gates`: none — runs at first login

#### Steps

1. `profile_basics` — structured_form: full_name, preferred_language (from school's primary_language), preferred_communication_channel (sms|whatsapp|email).
2. `linked_children` — multi_choice from `apps.people.services::list_pending_invites_for_user(request.user)`. Adds child verification via OTP if invite not pre-linked.
3. `communication_preferences` — structured_form: quiet_hours (datetime range), max_messages_per_day (number, default 5), per-category opt-ins.
4. `payment_method_preview` — read-only display of school's accepted payment methods (resolved from P2.1 if completed by tenant admin). Parent confirms to proceed.
5. `consent_signatures` — multi-checkbox: privacy_policy, data_residency_acknowledgment, terms_of_service. Each carries `accepted_version` SHA-256 hash for audit chain.

Persistence: writes to `apps.accounts.models::User`, `apps.communication.models::ParentChannelPreference`, `apps.compliance.models::ConsentAcceptance`.

### §6.8 P1.STAFF — Staff persona onboarding

**Meta:** same shape as parent, with steps:

1. `profile_basics` — full_name, role (from `apps.platform_runtime.role_registry`), employee_id (optional).
2. `role_assignment` — confirmed role + permissions preview.
3. `background_check_status` — boolean + upload (if applicable per country compliance).
4. `schedule_preferences` — duration: standard_hours_per_week, preferred_break_minutes.
5. `training_module_assignment` — auto-assigned based on role (read-only confirmation).

### §6.9 P2.1 — Local-First FinTech & Tax Matrix

**Meta:**
- `wizard_key`: `local_first_fintech_tax_matrix`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 15
- `gates`: `{permission_codename: "billing.change_paymentsettings", prerequisite_wizard: "multi_campus_local_sovereignty"}`
- `ai`: `{smart_defaults: true, branch_rationale: true}`

#### Steps

1. **`settlement_destination`** — structured_form: settlement_country (from `apps.finance.fintech::list_settlement_countries`), settlement_currency (ISO 4217), settlement_bank_account_alias (optional reference).
2. **`apm_integration`** — single_choice with options resolved from `apps.finance.apm_registry::list_apms_for_country(country)` — UPI/RuPay for IN, Pix for BR, M-Pesa for KE/TZ/UG, Stripe Card universal, etc. AI smart_defaults via `prompt.fintech.suggest_apm`.
3. **`split_ledger_allocation`** — `key_value_pairs` with `purpose` keys (tuition, transportation, uniforms, cafeteria, hostel, extracurricular) and `bank_account_alias` values. AI smart_defaults via `prompt.fintech.suggest_split_allocation`. Server validates allocations sum to 100% or all marked as "separate-deposit".
4. **`e_invoicing_handshake`** — branched by country:
   - SA → ZATCA `.pfx` upload
   - MX → SAT `.cer + .key` upload
   - IN → GST GSP credentials form
   - BR → SEFAZ digital certificate
   - default → "skip — not required in this jurisdiction"
   - Validates cert shape via `validate_pfx_certificate_shape`. Live submission deferred per plan §12.5.

**Persistence:** writes to `apps.billing.models::PaymentSettings`, `apps.finance.models::SplitLedgerRule`, `apps.compliance.models::EInvoicingHandshake`.

**Failure modes:**
- Country requires e-invoicing but cert not uploaded → soft block with `wizards.warnings.einvoicing_required_in_country`; offer reminder via `setup_studio.recommendations` refresh.

### §6.10 P2.2 — Localized Activity & Asset Marketplace

**Meta:**
- `wizard_key`: `localized_activity_asset_marketplace`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 12
- `gates`: `{permission_codename: "marketplace.change_storefront", prerequisite_wizard: "local_first_fintech_tax_matrix"}` (storefront needs settlement set first)
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`storefront_blueprinting`** — structured_form: storefront_name, storefront_categories (multi_choice from `apps.marketplace.category_registry`), default_currency (auto-fills from FinTech wizard), default_tax_inclusive (boolean).
2. **`product_catalog_seed`** — csv_mapping OR `structured_form` per-item entry. Optional file upload of CSV with columns name/sku/price/tax_rate/category/image_url.
3. **`financial_routing`** — single_choice from FinTech wizard's split_ledger_allocation list — which ledger account receives this storefront's revenue.
4. **`ticket_receipt_automation`** — structured_form: receipt_template (rich_select), delivery_channel (sms|whatsapp|email|parent_portal), include_qr_code (boolean).

**Persistence:** writes to `apps.marketplace.models::Storefront`, `Product`, `MarketplaceRoutingRule`. Asset QR matrix sub-step deferred (needs `apps/asset_tracker/`).

### §6.11 P2.3 — Cashless Campus POS

**Meta:**
- `wizard_key`: `cashless_campus_pos`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 8
- `gates`: `{permission_codename: "schoolops.change_meal_plan"}`
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`terminal_registration`** — structured_form: terminal_devices (multi-row: device_name, device_type [tablet|phone|kiosk], location [cafeteria|library|tuck_shop]). Each row auto-assigned a unique `terminal_token` used for offline-capable POS auth.
2. **`credential_mapping`** — single_choice: `barcode|rfid|biometric_thumb|biometric_face`. AI smart_defaults via context including `country_code` (some countries restrict biometric).
3. **`daily_guardrails`** — structured_form: parent_default_daily_limit_decimal (Decimal, money_float-allow not needed — decimal type enforced), top_up_minimum (Decimal), top_up_maximum (Decimal), low_balance_threshold (Decimal, default $5.00 equiv).
4. **`allergen_dietary_rules`** — auto-derived from `apps.student360` allergen fields; UI shows count of students with allergens + allows operator to confirm allergen-block enforcement is enabled at POS.

**Persistence:** writes to `apps.schoolops.models::POSTerminal`, `CredentialMethod`, `apps.billing.models::WalletConfiguration`, `apps.schoolops.models::AllergenBlockingPolicy`.

### §6.12 P2.4 — Dynamic Safeguarding / Incident / Medical

**Meta:**
- `wizard_key`: `dynamic_safeguarding_incident_medical`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 12
- `gates`: `{permission_codename: "compliance.change_safeguarding"}`
- `ai`: `{branch_rationale: true}`

#### Steps

1. **`incident_categorization`** — multi_choice from `apps.compliance.incident_registry::list_categories(country_code)` — Medical Emergency, Disciplinary Action, Safeguarding Concern, Bullying Report, Substance Incident, etc.
2. **`legal_protocol_routing`** — per category, the wizard surfaces required jurisdictional forms. AI branch_rationale explains why (e.g. CA requires mandated-reporter form for safeguarding).
3. **`encrypted_stakeholder_pipeline`** — structured_form: guardian_notify_channel, school_authority_notify_chain (ordered list of roles: counselor → principal → safeguarding_lead → external).
4. **`immutable_audit_anchor`** — single_choice from `apps.compliance.audit_anchors::list_available_vaults()` — local DB append-only OR external WORM bucket OR HSM-anchored. Routes through existing audit chain from v3.39.

**Persistence:** writes to `apps.compliance.models::IncidentCategoryConfiguration`, `StakeholderRoutingChain`, `AuditAnchorConfiguration`. Anchors into existing `MigrationCloudAuditEvent` append-only chain.

### §6.13 P2.5 — Omnichannel Communication Routing

**Meta:**
- `wizard_key`: `omnichannel_communication_routing`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 10
- `gates`: `{permission_codename: "communication.change_routing"}`
- `ai`: `{smart_defaults: true, translate_mesh: true}`

#### Steps

1. **`event_definition`** — single_choice from `apps.automation.event_registry::list_supported_triggers()` — student.marked_absent_consecutive_days_N, attendance.dropped_below_pct, fee.overdue_days_N, grade.below_threshold, safeguarding.flagged, etc.
2. **`gateway_prioritization`** — ranked_list of channels: app_push, whatsapp, sms, email, ussd_fallback, voice_call. Order = priority. AI smart_defaults orders by country connectivity tier.
3. **`asynchronous_guard_rules`** — structured_form: quiet_hours_start (time), quiet_hours_end (time), max_messages_per_recipient_per_day, defer_until_business_hours (boolean), labor_law_jurisdiction (auto-fills from sovereignty).
4. **`ai_translation_mapping`** — multi_choice of target locales (from school's primary + secondary languages). When enabled, every outbound message gets translated per-locale via `request_translation_mesh`. UX shows preview of one message translated across selected locales.

**Persistence:** writes to `apps.communication.models::EventRoute`, `ChannelPriorityChain`, `QuietHoursPolicy`, `TranslationMeshConfiguration`.

### §6.14 P3.1 — JIT Operator Compliance & Safeguarding

**Meta:**
- `wizard_key`: `jit_operator_compliance_safeguarding`
- `audience`: `["operator"]`
- `estimated_minutes`: 8
- `gates`: `{permission_codename: "security.change_jit_policy"}`
- `ai`: `{branch_rationale: true}`

#### Steps

1. **`assumed_access_trigger`** — multi_choice: troubleshooting_active_bug|migration_in_progress|safeguarding_active|legal_hold|customer_request. Each tagged with default duration window.
2. **`external_guardrail_selection`** — structured_form: geo_fence_radius_meters (number), allowed_ip_ranges (CIDR list), require_2fa_within_window (boolean), require_video_attestation (boolean).
3. **`identity_masking_form`** — multi_choice of PII fields to redact on support views: student_full_name, dob, ssn_local_equivalent, parent_phone, parent_email, address, medical_notes, financial_records.
4. **`ledger_immutable_endpoint`** — single_choice: append_only_db|s3_object_lock|hsm_anchored. Routes via existing audit chain (v3.39).

**Persistence:** writes to `apps.security.models::JITAccessPolicy`, `apps.policies_rules.models::PIIMaskingPolicy`. Anchors to existing audit chain.

### §6.15 P3.2 — Human Capital, Shift, Substitute Market

**Meta:**
- `wizard_key`: `human_capital_shift_substitute_market`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 14
- `gates`: `{permission_codename: "payroll.change_laborprofile", prerequisite_wizard: "multi_campus_local_sovereignty"}`
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`labor_contract_profile`** — structured_form: max_weekly_hours, overtime_threshold_hours, overtime_multiplier (decimal), standard_paid_leave_days (number), sick_leave_days (number). AI smart_defaults per country (KE: typical 45 hours/week, FR: 35, US: varies).
2. **`regional_tax_blueprinting`** — auto-computed from sovereignty wizard's country+state; presents tax brackets read-only for confirmation; operator can override per-bracket.
3. **`absence_logic_toggles`** — structured_form: emergency_absence_cutoff_time (time, e.g. 06:00), auto_broadcast_to_subs (boolean), require_principal_approval (boolean).
4. **`substitute_match_automation`** — structured_form: substitute_pool (auto-derived from `apps.people` users with substitute role), broadcast_channels (multi_choice: sms|whatsapp|email|push), accept_window_minutes (number, default 30), max_invites_per_event (number).

**Persistence:** writes to `apps.payroll.models::LaborContractProfile`, `RegionalTaxBracket`, `apps.schoolops.models::AbsencePolicy`, `SubstituteBroadcastRule`.

### §6.16 P3.3 — Institutional Performance & Board Reporting

**Meta:**
- `wizard_key`: `institutional_performance_board_reporting`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 8
- `gates`: `{permission_codename: "reports.change_executive_report"}`
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`metric_kpi_assembly`** — multi_choice from `apps.analytics.kpi_registry::list_kpis()` — enrollment_retention_pct, tuition_collection_velocity_days, class_passing_avg_pct, teacher_retention_pct, parent_nps, safeguarding_open_incidents, etc.
2. **`cross_campus_aggregation`** — single_choice: all_campuses_consolidated|per_campus_breakdown|comparative_dashboard. Only shown if school has >1 campus.
3. **`predictive_trend_projection`** — boolean toggle: enable_ai_predictions (gates the AI conflict solver / risk model in Phase 4+).
4. **`visual_report_compilation`** — structured_form: report_template (rich_select), delivery_format (pdf|secure_link|signed_share), recipients (multi_choice from `apps.people.governance::list_board_members`).

**Persistence:** writes to `apps.reports.models::ExecutiveReportConfiguration`. PDF compile pipeline deferred per plan §12.8.

### §6.17 P3.4 — Self-Healing Observability Guard

**Meta:**
- `wizard_key`: `self_healing_observability_guard`
- `audience`: `["operator"]`
- `estimated_minutes`: 8
- `gates`: `{permission_codename: "observability.change_threshold"}`
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`threshold_definition`** — structured_form: error_rate_threshold_pct (decimal, default 0.5), latency_p95_threshold_ms (number, default 1500), uptime_target_pct (decimal, default 99.9). Routes via existing SLO registry (`apps/observability/slo.py`).
2. **`recovery_actions`** — multi_choice from `apps.observability.recovery_actions::list_actions()` — auto_failover_region|kill_offending_job|alert_oncall_sms|alert_oncall_phone|page_eng_lead|create_incident_ticket.
3. **`support_tunnel_activation`** — boolean + structured_form for JIT tunnel: max_session_duration_minutes, require_screen_recording (boolean), notify_tenant_admin_on_open (boolean). Anchors to v3.39 JIT compliance pattern.

**Persistence:** writes to `apps.observability.models::ThresholdConfiguration`, `RecoveryActionMap`, `SupportTunnelPolicy`.

### §6.18 P3.5 — Dynamic Multi-Campus Scheduling

**Meta:**
- `wizard_key`: `dynamic_multi_campus_scheduling`
- `audience`: `["operator","tenant_admin"]`
- `estimated_minutes`: 18 (longest in catalog)
- `gates`: `{permission_codename: "orchestration.change_schedule", prerequisite_wizard: "polymorphic_grading_curricula"}`
- `ai`: `{smart_defaults: true, branch_rationale: true}`

#### Steps

1. **`resource_constraints`** — structured_form: rooms (multi-row: room_name, capacity, equipment_tags), specialized_lab_gear (multi-row), teacher_availability (per-teacher weekly hour caps).
2. **`curricula_pathways`** — auto-derived from polymorphic_grading_curricula wizard's track_selection. Read-only confirmation.
3. **`ai_conflict_solver`** — runs `apps.orchestration.solvers::solve_schedule(constraints, pathways)` — deterministic OR-tools constraint solver in MVP; AI upgrade deferred per plan §12.9. Result shows draft schedule + conflicts list + AI rationale if AI enabled.
4. **`unified_rollout`** — single_choice: dry_run|publish_to_staff_preview|publish_live. Live publish writes to `apps.academics.models::CourseSchedule` and triggers calendar export to all teacher/student/parent dashboards.

**Persistence:** writes to `apps.orchestration.models::ScheduleVersion`, `apps.academics.models::CourseSchedule`.

### §6.19 P3.6 — Localized Field Trip Coordinator

**Meta:**
- `wizard_key`: `localized_field_trip_coordinator`
- `audience`: `["teacher"]`
- `estimated_minutes`: 6
- `gates`: `{permission_codename: "school_events.add_fieldtrip"}`
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`logistics_definition`** — structured_form: trip_name, destination (text), departure_datetime, return_datetime, transport_type (bus|car|train|walk|virtual), cost_per_student_decimal.
2. **`automated_authorization_pipeline`** — structured_form: parent_signature_required (boolean), payment_required (boolean), medical_release_required (boolean), photo_consent_required (boolean), notification_channel (multi_choice).
3. **`real_time_roster_ledger`** — auto-generated from teacher's class roster + opt-in/opt-out tracking + payment status. Read-only confirmation step.

**Persistence:** writes to `apps.school_events.models::FieldTrip`, `FieldTripPermission`, `FieldTripPayment`.

### §6.20 P3.7 — Personal Graduation Pathway & Elective

**Meta:**
- `wizard_key`: `personal_graduation_pathway_elective`
- `audience`: `["student","tenant_admin"]` (student runs for self; admin configures available pathways)
- `estimated_minutes`: 10
- `gates`: `{permission_codename: "academics.add_studentelective"}`
- `ai`: `{smart_defaults: true}`

#### Steps

1. **`target_objective`** — single_choice from `apps.academics.objectives::list_post_secondary_objectives(student_country, student_track)` — engineering, medicine, arts, vocational_trade, university_general, gap_year, etc.
2. **`credit_metric_audit`** — auto-derived from student's transcript; shows current credits vs target credits per objective. Read-only.
3. **`dynamic_class_matcher`** — multi_choice of available electives that fit schedule + prerequisites. AI smart_defaults via `prompt.pathway.suggest_courses`.
4. **`pathway_lock`** — confirmation step: locks student's elective selection, auto-routes to parent for digital signature, updates `apps.academics.models::StudentEnrollment`.

**Persistence:** writes to `StudentPathway`, `StudentElectiveSelection`, `EnrollmentRegisterEntry`.

---

## §7 i18n strategy

### §7.1 Token namespace

All wizard strings use the namespace `wizards.<wizard_key>.<scope>.<key>`:

- `wizards.<wizard_key>.label` — wizard title
- `wizards.<wizard_key>.description` — wizard subtitle
- `wizards.<wizard_key>.step.<step_key>.label` — step title
- `wizards.<wizard_key>.step.<step_key>.description` — step subtitle
- `wizards.<wizard_key>.step.<step_key>.field.<field_name>.label` — field label
- `wizards.<wizard_key>.step.<step_key>.field.<field_name>.helper` — helper text
- `wizards.<wizard_key>.option.<option_key>.label` — option label (for `single_choice`/`multi_choice`)
- `wizards.<wizard_key>.rationale.<rationale_key>` — AI rationale tokens
- `wizards.errors.<error_key>` — shared error messages
- `wizards.warnings.<warning_key>` — shared warning messages

### §7.2 Locale extraction

All tokens extracted via `python manage.py makemessages -l <locale>` after wizards land. Per-locale .po files at `locale/<lc>/LC_MESSAGES/django.po`.

Phase 1 minimum locale coverage:
- `en` (English) — 100% (source)
- `fr` (French) — 100% (CM, CA-QC, FR, BE, CH, SN, MA, CI markets)
- `es` (Spanish) — 100% (MX, AR, CO, CL, ES markets)
- `pt` (Portuguese) — 100% (BR, PT, AO, MZ markets)
- `ar` (Arabic) — 100% (SA, AE, EG, MA-AR, SD, JO, IQ markets), RTL
- `hi` (Hindi) — 80% (IN markets)
- `sw` (Swahili) — 80% (KE, TZ, UG markets)

Phase 2: add `de`, `it`, `ja`, `ko`, `zh-CN`, `zh-TW`, `vi`, `th`, `tl`, `id`, `ms`, `ta`, `ml`, `kn`, `bn`.

`scan_locale_coverage` baseline updates per locale per wave.

### §7.3 AI-generated rationale + translation mesh

`request_translation_mesh` provides on-demand translation for outbound messages (P2.5). Does NOT replace `.po` files for static wizard chrome — those stay translator-curated.

---

## §8 Mobile UX rules per input type

| Input type | Default mobile layout | Notes |
|---|---|---|
| `single_choice` | radio cards, full-width, 1 per row | tap-targets ≥ 48px |
| `multi_choice` | checkbox cards, full-width, 1 per row | same |
| `text` | single input, full-width | autocomplete attr per field semantics |
| `long_text` | textarea, 8 rows initial, expandable | virtual keyboard "Done" key dismisses |
| `number` / `decimal` | numeric keypad keyboard | `inputmode="decimal"` |
| `boolean` | toggle switch, full-width row with label | |
| `file_upload` | full-bleed drop zone + camera-capture trigger | `accept="image/*" capture="environment"` on image uploads |
| `image_upload` | preview card stacked above input | square thumbnails, 1:1 default |
| `color_picker` | hex input + native picker fallback | live preview swatch full-width |
| `domain_input` | single input + DNS check inline | shows DNS result above keyboard line |
| `structured_form` | one field per row, vertical stack | sticky save-draft button |
| `draw_on_map` | full-bleed map, pinch-zoom, tap-to-add-vertex | toolbar collapsed to FAB |
| `csv_mapping` | swipe-card-per-mapping (one source → one target) | vertical column flips horizontal on tablet+ |
| `rich_select` | sheet-bottom search dialog | options scroll inside sheet |
| `ranked_list` | drag-handle + tap-up/down arrows | Alt+Up/Alt+Down keyboard a11y |
| `key_value_pairs` | add-row at bottom, stacked rows | swipe-left to delete row |
| `datetime` | native picker | locale-aware format |
| `duration` | three pickers stacked (days/hours/minutes) | step values per unit |

All inputs honor `prefers-reduced-motion` for transitions and `prefers-color-scheme` for token cascade.

---

## §9 Test coverage matrix

### §9.1 Engine tests (Phase 1)

| Test file | Coverage |
|---|---|
| `tests/setup_studio/test_wizard_engine_registry.py` | registry load, schema validation, resolver imports, audience filter, gates evaluation |
| `tests/setup_studio/test_wizard_engine_branching.py` | declarative branches, resolver branches, end-of-wizard, malformed branch raises |
| `tests/setup_studio/test_wizard_engine_validation.py` | every validator function — happy + sad path each |
| `tests/setup_studio/test_wizard_state_resolver.py` | get_or_create, apply_step_answer, reset, export/restore, state namespacing |
| `tests/setup_studio/test_wizard_state_tenant_isolation.py` | one school can't read another's wizard state; concurrent writes don't corrupt |
| `tests/setup_studio/test_wizard_ai_helpers.py` | smart_defaults success + fallback + timeout; context sanitization removes 14 sensitive keys; metric emission |
| `tests/setup_studio/test_wizard_ai_boundary.py` | AST scan asserts `services.ai_gateway` NOT imported anywhere in `apps/setup_studio/wizard_*.py` |
| `tests/setup_studio/test_wizard_views_operator.py` | permission gates, step rendering, POST advance, redirect chain |
| `tests/setup_studio/test_wizard_views_tenant.py` | same for tenant |
| `tests/setup_studio/test_wizard_state_cache_serialization.py` | server-side cache serialization safe from PII bleed |
| `tests/setup_studio/test_wizard_telemetry.py` | every emit_* function — labels sanitized per observability contract |

### §9.2 Per-wizard tests (every wizard)

| Test file | Coverage |
|---|---|
| `tests/setup_studio/wizards/test_<wizard_key>_schema.py` | JSON parses, all dotted paths import |
| `tests/setup_studio/wizards/test_<wizard_key>_happy_path.py` | full happy path from step 1 to end |
| `tests/setup_studio/wizards/test_<wizard_key>_branching.py` | every branch decision per step |
| `tests/setup_studio/wizards/test_<wizard_key>_validation.py` | every validation rule |
| `tests/setup_studio/wizards/test_<wizard_key>_persistence.py` | every persistence target writes the expected shape |
| `tests/setup_studio/wizards/test_<wizard_key>_ai_smart_defaults.py` | AI fallback returns correct deterministic suggestion |
| `tests/setup_studio/wizards/test_<wizard_key>_resume.py` | mid-wizard logout/login restores state |

### §9.3 Playwright e2e (every wizard, 3 breakpoints)

`tests/e2e/wizards/<wizard_key>.spec.js` — verifies UI at 390×844, 768×1024, 1366×768. Asserts:
- Wizard mounts at expected URL
- Stepper renders with correct step count
- Each step renders without console errors
- Form submission advances to next step
- Back button restores prior step's values
- Mobile state-restore banner appears when cache present and ahead of server

### §9.4 CI integration

| Gate | Where | Triggers on |
|---|---|---|
| `verify_unified_wizard_framework.py` | `.github/workflows/architectural-boundaries.yml` | PR touches `apps/setup_studio/` or `wizards/*.json` |
| `scan_wizard_json_schema_drift.py` | same | same |
| `scan_wizard_class_grammar.py` | same | PR touches `static/css/` or `templates/setup_studio/` |
| Playwright wizard suite | `.github/workflows/e2e-wizards.yml` (new) | PR touches `wizards/` or wizard templates |

---

## §10 Telemetry + failure mode reference

### §10.1 Metric catalog

| Metric name | Type | Labels | Emitted from |
|---|---|---|---|
| `wizard.step.viewed` | counter | wizard_key, step_key, audience | `wizard_views.py:get()` |
| `wizard.step.applied` | counter | wizard_key, step_key, audience, outcome | `wizard_state_resolver.py:apply_step_answer()` |
| `wizard.step.validation_failed` | counter | wizard_key, step_key, field_name_hash | `wizard_views.py:post()` |
| `wizard.completed` | counter | wizard_key, audience | `wizard_state_resolver.py` |
| `wizard.abandoned` | counter | wizard_key, last_step_key, audience | nightly task scanning idle SetupProgress |
| `wizard.duration_seconds` | histogram | wizard_key, audience | computed on completion |
| `wizard.ai.smart_defaults.success` | counter | wizard_key, step_key | `wizard_ai.py` |
| `wizard.ai.smart_defaults.timeout` | counter | wizard_key, step_key | same |
| `wizard.ai.smart_defaults.fallback` | counter | wizard_key, step_key, reason | same |
| `wizard.ai.smart_defaults.latency_ms` | histogram | wizard_key, step_key | same |
| `wizard.ai.branch_rationale.{success,timeout,fallback}` | counter | same pattern | same |
| `wizard.ai.translate_mesh.{success,failed_per_locale}` | counter | wizard_key, locale | same |
| `wizard.cache.quota_exceeded` | counter | wizard_key | client → ajax beacon |
| `wizard.cache.schema_mismatch` | counter | wizard_key, cached_version | same |

All label values pass through `_sanitize_labels` from `apps/observability/metrics.py` — no PII bleed.

### §10.2 Failure mode response table

| Failure | User-visible response | Telemetry |
|---|---|---|
| AI timeout | "Suggestion unavailable, please proceed manually" toast; fallback default applied | `wizard.ai.*.timeout` |
| AI returned invalid JSON | Same as timeout, retry once | `wizard.ai.*.fallback` with reason `invalid_json` |
| AI returned out-of-options value | Same, ignore suggestion | `wizard.ai.*.fallback` with reason `option_not_in_set` |
| Server validation fail | Inline error per field | `wizard.step.validation_failed` |
| Persistence write fail | Toast "Save failed, retrying"; auto-retry with exponential backoff (max 3); on final fail → state cache holds; user sees "We couldn't save. Try again or contact support." | `wizard.persistence.failed` |
| Gate blocked | Redirect to `/super/wizards/` or `/school/studio/wizards/` index with toast | `wizard.gate.blocked` |
| Prerequisite wizard not completed | Toast + redirect to prerequisite wizard | `wizard.prerequisite.blocked` |
| Resume after schema bump | Banner "We've updated this wizard; please re-confirm your choices"; current_step_key reset to first step | `wizard.resume.schema_upgraded` |
| LocalStorage quota | Silent fallback to server-only state; banner explains | `wizard.cache.quota_exceeded` |
| Migration cloud receiver down (P1.4) | Wizard pauses at upload step; banner "Migration service unavailable, retry"; AJAX status check every 30s | `wizard.legacy.receiver_unavailable` |
| WCAG fail in P1.1 | Soft prompt "These colors don't meet accessibility standards. Use suggested? [Accept] [Use anyway]" | `wizard.whitelabel.wcag_override` |

---

## §11 Migration / cleanup of legacy persona wizards

### §11.1 Existing artifacts being absorbed

- `templates/student/onboarding_wizard.html` — current standalone template
- `templates/teacher/onboarding_wizard.html` — current standalone template

### §11.2 Migration approach

1. **Author JSON specs:**
   - `apps/setup_studio/wizards/student_onboarding.json`
   - `apps/setup_studio/wizards/teacher_onboarding.json`
   - Match step-by-step the existing template flow
2. **Wire new URLs:**
   - `/school/studio/wizards/student_onboarding/` for students
   - `/school/studio/wizards/teacher_onboarding/` for teachers
3. **Add 301 redirects** at existing URLs for 30 days:
   - Old: `/portal/student/onboarding/` → 301 → new URL
   - Old: `/portal/teacher/onboarding/` → 301 → new URL
4. **Day 30:** drop legacy templates + 301 redirects. Track via `docs/CSS_RETIREMENT_DOCKET.md`.
5. **Add NEW parent + staff wizards** (P1.PARENT + P1.STAFF) symmetric to absorbed wizards.

### §11.3 State migration

Existing student/teacher progress lives in `apps/portal/models::OnboardingProgress` (if it exists) or scattered `User` flags. Migration command:

```bash
python manage.py migrate_legacy_persona_wizard_state \
    --persona student \
    --apply  # without --apply runs dry
```

Reads legacy state, writes new format into `SetupProgress.step_state["wizards"]["student_onboarding"]`. Idempotent.

---

## §12 Implementation order (file-by-file)

This is the literal sequence of files to create/edit. Follow in order. Each numbered item should be a discrete commit.

### Phase 1, Wave 1 — Engine foundation (no UI yet)

1. Create `apps/setup_studio/wizard_validators.py` (pure functions, fully unit-tested first).
2. Create `apps/setup_studio/wizard_engine.py` (registry, dataclasses, resolvers).
3. Create `apps/setup_studio/wizard_state_resolver.py` (state model wrappers).
4. Create `apps/setup_studio/wizard_ai.py` (5 callables — all routed through `services.ai_helpers`).
5. Create `apps/setup_studio/wizard_telemetry.py` (metric emitters).
6. Create `apps/setup_studio/ai_prompts.py` (prompt template library).
7. Create `apps/setup_studio/ai_fallbacks.py` (deterministic fallbacks per prompt key).
8. Create `apps/setup_studio/wizards/__init__.py` (empty, marks directory).
9. Create `docs/WIZARD_BRANCHING_SCHEMA.md` (formal jsonschema + examples).
10. Create `tests/setup_studio/test_wizard_engine_*.py` files (§9.1 list).
11. Run tests; iterate; all green.

### Phase 1, Wave 2 — Frontend foundation

12. Create `static/css/rmc-wizard.css` (all `.rmc-wizard-*` classes).
13. Append `.rmc-wizard-*` entries to `static/css/rmc-class-grammar.css`.
14. Create `static/js/rmc-wizard-state-cache.js` (CSP-safe IIFE).
15. Create `templates/setup_studio/operator_wizard.html`.
16. Create `templates/setup_studio/tenant_wizard.html`.
17. Create `templates/setup_studio/partials/wizard_stepper.html`.
18. Create `templates/setup_studio/partials/wizard_nav.html`.
19. Create `templates/setup_studio/partials/wizard_help_rail.html`.
20. Create `templates/setup_studio/partials/wizard_ai_rationale.html`.
21. Create `templates/setup_studio/partials/wizard_state_restore_banner.html`.
22. Create 18 input partials under `templates/setup_studio/inputs/` (§4.2 list).
23. Wire CSS + JS into `portal_base.html` and `control_plane_skeleton.html`.

### Phase 1, Wave 3 — Views + URLs + index pages

24. Create `apps/setup_studio/wizard_views.py` (Operator + Tenant + Index views).
25. Create `apps/setup_studio/urls_wizards.py`.
26. Mount `urls_wizards` from `siteconfig.urls` (operator) and `studio_os.urls` (tenant).
27. Create wizard index templates (`templates/setup_studio/operator_wizard_index.html`, `tenant_wizard_index.html`).
28. Run e2e Playwright spec for engine-only (no wizards yet) — should resolve URLs cleanly with "No wizards available" empty state.

### Phase 1, Wave 4 — First wizard (P1.1 Whitelabel)

29. Create `apps/setup_studio/wizards/cross_platform_whitelabel_branding.json`.
30. Create per-step view templates if needed (most reuse input partials).
31. Add wizard-specific options resolvers in respective apps (`apps/brand_experience/palette_registry`, etc.).
32. Add wizard-specific next_step resolvers if any.
33. Add persistence writers (`apps/brand_experience/services::install_brand_assets`).
34. Add per-wizard tests (§9.2 list).
35. Add Playwright spec for P1.1.
36. Iterate until all green.

### Phase 1, Wave 5+ — Wizards P1.2 → P1.5 + Parent + Staff

Each: ~150 LOC JSON + ~50 LOC of new resolver/writer code + tests + Playwright. Follow same pattern as Wave 4.

### Phase 1, Wave 6 — Legacy persona migration

37. Author `student_onboarding.json` and `teacher_onboarding.json` matching existing flows.
38. Implement `migrate_legacy_persona_wizard_state` management command.
39. Wire 301 redirects.
40. Update docs + memory + MEMORY.md.

### Phase 1, Wave 7 — Verifiers + CI

41. Create `scripts/verify_unified_wizard_framework.py`.
42. Create `scripts/scan_wizard_json_schema_drift.py`.
43. Create `scripts/scan_wizard_class_grammar.py`.
44. Update `.github/workflows/architectural-boundaries.yml`.
45. Bump SW to `sms-v3.65.x-unified-wizard-foundation-<date>`.
46. Update `docs/CSS_RETIREMENT_DOCKET.md`.
47. Update `MEMORY.md` and write `project_unified_wizard_framework_phase_1_<date>.md`.

### Phase 2 — Revenue + compliance + comms (batch 1411)

Each wizard P2.1–P2.5: ~150 LOC JSON + resolver/writer code + tests + Playwright. New scanners as needed.

### Phase 3 — Operations (batch 1412)

Each wizard P3.1–P3.7: ~150 LOC JSON + resolver/writer code + tests + Playwright. Final cleanup, final SW bump, final memory + docket update.

---

**End of detailed implementation field manual.**

**Companion plan doc:** `docs/plans/UNIFIED_WIZARD_FRAMEWORK_PLAN.md`
**Memory:** `memory/project_unified_wizard_framework_planned_2026_05_26.md`
**Authored:** 2026-05-26 by Claude Opus 4.7 (1M context)
