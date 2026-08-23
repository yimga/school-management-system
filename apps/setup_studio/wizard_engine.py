"""Unified Wizard Engine — registry, branching, validation orchestration.

Per ``docs/plans/UNIFIED_WIZARD_FRAMEWORK_PLAN.md`` and the implementation
detail companion. Engine is JSON-driven; each wizard is a JSON file at
``apps/setup_studio/wizards/<wizard_key>.json``. Engine loads at module
import, validates schema + resolver imports + audience markers.

Public API:

* ``WIZARD_REGISTRY`` — dict[str, WizardDefinition], populated at import.
* ``load_wizard_registry()`` — idempotent reload (used by tests).
* ``get_wizard(wizard_key)`` — single fetch.
* ``list_wizards_for_audience(audience)`` — filtered fetch.
* ``resolve_options(step, request, school)`` — call options_resolver.
* ``resolve_next_step(wizard, current_step, current_answer, progress_state)``.
* ``validate_step_answer(step, payload)`` — returns ``(is_valid, errors)``.

App code MUST NOT import ``services.ai_gateway`` directly — boundary
scanner enforces. All AI calls go through ``apps.setup_studio.wizard_ai``.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from apps.setup_studio import wizard_validators as _val


def _resolve_max_text_field_length() -> int:
    """Effective global free-text cap. Env-tunable
    (``WIZARD_MAX_TEXT_FIELD_LENGTH``) over the platform-constant default —
    no hardcoded magic number on the validation hot path."""
    raw = os.environ.get("WIZARD_MAX_TEXT_FIELD_LENGTH", "")
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return _val.DEFAULT_MAX_TEXT_FIELD_LENGTH


WIZARD_MAX_TEXT_FIELD_LENGTH = _resolve_max_text_field_length()

# Keys a ``structured_form`` payload may carry that are NOT declared fields.
# The HTTP view builds field-only payloads, so this is empty today; it exists so
# a future framework-level key (e.g. an idempotency token) can be allowlisted in
# one place instead of weakening the unexpected-attribute check.
_ALLOWED_PAYLOAD_META_KEYS: frozenset[str] = frozenset()

# Legitimate top-level payload keys for NON-structured input types, beyond the
# universal ``value`` convention. ``_parse_post_payload`` nests data under these
# keys for a few input types (key_value_pairs -> ``pairs``; duration -> day/hour/
# minute parts), while the synthetic/test path uses ``value`` for every type — so
# the allowlist is the UNION (``value`` is always permitted). Anything else is a
# smuggled / replayed key and is rejected, mirroring the structured_form check.
_INPUT_TYPE_EXTRA_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "key_value_pairs": frozenset({"pairs"}),
    "duration": frozenset({"days", "hours", "minutes"}),
}


def _allowed_payload_keys(input_type: str) -> frozenset[str]:
    """Top-level keys a non-structured payload may legitimately carry."""
    return (
        frozenset({"value"})
        | _INPUT_TYPE_EXTRA_PAYLOAD_KEYS.get(input_type, frozenset())
        | _ALLOWED_PAYLOAD_META_KEYS
    )

__all__ = [
    "Audience",
    "InputType",
    "StepDefinition",
    "WizardDefinition",
    "WIZARD_REGISTRY",
    "load_wizard_registry",
    "get_wizard",
    "list_wizards_for_audience",
    "resolve_options",
    "resolve_next_step",
    "validate_step_answer",
    "WizardError",
    "WizardNotFound",
    "StepNotFound",
    "ResolverImportError",
    "WizardSchemaError",
    "GateBlockedError",
]

logger = logging.getLogger(__name__)

Audience = Literal["operator", "tenant_admin", "teacher", "parent", "student", "staff"]
InputType = Literal[
    "single_choice", "multi_choice", "text", "long_text", "number", "decimal",
    "boolean", "file_upload", "image_upload", "color_picker", "domain_input",
    "structured_form", "draw_on_map", "csv_mapping", "rich_select",
    "ranked_list", "key_value_pairs", "datetime", "duration",
]

_VALID_INPUT_TYPES = frozenset({
    "single_choice", "multi_choice", "text", "long_text", "number", "decimal",
    "boolean", "file_upload", "image_upload", "color_picker", "domain_input",
    "structured_form", "draw_on_map", "csv_mapping", "rich_select",
    "ranked_list", "key_value_pairs", "datetime", "duration",
})

_VALID_AUDIENCES = frozenset({"operator", "tenant_admin", "teacher", "parent", "student", "staff"})


# ---------- Exceptions ----------


class WizardError(Exception):
    """Base wizard error.

    ``operator_message`` is the one sentence a person at the screen can act on,
    kept separate from ``str(exc)`` -- which names wizard.step for the log and
    means nothing to them. It stays None when the cause is not actionable (a
    missing dotted writer path is a deployment fault, not an operator's
    mistake); the view then falls back to a generic line. Declared here rather
    than attached at each raise site so every WizardError answers to it.
    """

    operator_message: str | None = None


class WizardNotFound(WizardError):
    """Requested wizard key not in registry."""


class StepNotFound(WizardError):
    """Requested step key not in wizard."""


class ResolverImportError(WizardError):
    """options_resolver / next_step_resolver / writer dotted path failed to import."""


class WizardSchemaError(WizardError):
    """JSON file doesn't match expected schema shape."""


class GateBlockedError(WizardError):
    """Permission, feature flag, or prerequisite wizard not satisfied."""


# ---------- Dataclasses ----------


@dataclass(frozen=True)
class StepDefinition:
    key: str
    label_token: str
    description_token: str
    input_type: str
    options_resolver: str | None = None
    fields: tuple[dict, ...] = field(default_factory=tuple)
    next_step_resolver: str | None = None
    branches: dict[str, str] | None = None
    ai_recommend: dict[str, Any] | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    persistence: dict[str, Any] = field(default_factory=dict)
    estimated_seconds: int = 60
    mobile_layout: str | None = None


@dataclass(frozen=True)
class WizardDefinition:
    wizard_key: str
    version: int
    audience: tuple[str, ...]
    label_token: str
    description_token: str
    icon_class: str
    estimated_minutes: int
    gates: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, bool] = field(default_factory=dict)
    steps: tuple[StepDefinition, ...] = field(default_factory=tuple)

    def step_by_key(self, step_key: str) -> StepDefinition:
        for s in self.steps:
            if s.key == step_key:
                return s
        raise StepNotFound(f"step {step_key!r} not in wizard {self.wizard_key!r}")

    def first_step(self) -> StepDefinition:
        if not self.steps:
            raise StepNotFound(f"wizard {self.wizard_key!r} has zero steps")
        return self.steps[0]


# ---------- Registry ----------


WIZARD_REGISTRY: dict[str, WizardDefinition] = {}


def _default_wizards_dir() -> Path:
    return Path(__file__).resolve().parent / "wizards"


def _parse_step(raw: dict[str, Any], wizard_key: str) -> StepDefinition:
    if not isinstance(raw, dict):
        raise WizardSchemaError(f"{wizard_key}: step must be object")

    key = raw.get("key")
    if not isinstance(key, str) or not key:
        raise WizardSchemaError(f"{wizard_key}: step.key required string")

    input_type = raw.get("input_type")
    if input_type not in _VALID_INPUT_TYPES:
        raise WizardSchemaError(f"{wizard_key}.{key}: unknown input_type {input_type!r}")

    # branches XOR next_step_resolver XOR neither
    has_branches = "branches" in raw and raw["branches"] is not None
    has_resolver = "next_step_resolver" in raw and raw["next_step_resolver"] is not None
    if has_branches and has_resolver:
        raise WizardSchemaError(
            f"{wizard_key}.{key}: branches and next_step_resolver are mutually exclusive"
        )

    return StepDefinition(
        key=key,
        label_token=str(raw.get("label_token") or f"wizards.{wizard_key}.step.{key}.label"),
        description_token=str(
            raw.get("description_token") or f"wizards.{wizard_key}.step.{key}.description"
        ),
        input_type=input_type,
        options_resolver=raw.get("options_resolver"),
        fields=tuple(raw.get("fields") or ()),
        next_step_resolver=raw.get("next_step_resolver"),
        branches=raw.get("branches"),
        ai_recommend=raw.get("ai_recommend"),
        validation=raw.get("validation") or {},
        persistence=raw.get("persistence") or {},
        estimated_seconds=int(raw.get("estimated_seconds") or 60),
        mobile_layout=raw.get("mobile_layout"),
    )


def _parse_wizard(raw: dict[str, Any], source_path: Path) -> WizardDefinition:
    if not isinstance(raw, dict):
        raise WizardSchemaError(f"{source_path}: top-level must be object")

    wizard_key = raw.get("wizard_key")
    if not isinstance(wizard_key, str) or not wizard_key:
        raise WizardSchemaError(f"{source_path}: wizard_key required string")

    audience = raw.get("audience")
    if not isinstance(audience, list) or not audience:
        raise WizardSchemaError(f"{wizard_key}: audience must be non-empty list")
    for a in audience:
        if a not in _VALID_AUDIENCES:
            raise WizardSchemaError(f"{wizard_key}: unknown audience {a!r}")

    steps_raw = raw.get("steps") or []
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WizardSchemaError(f"{wizard_key}: steps must be non-empty list")

    steps = tuple(_parse_step(s, wizard_key) for s in steps_raw)

    return WizardDefinition(
        wizard_key=wizard_key,
        version=int(raw.get("version") or 1),
        audience=tuple(audience),
        label_token=str(raw.get("label_token") or f"wizards.{wizard_key}.label"),
        description_token=str(
            raw.get("description_token") or f"wizards.{wizard_key}.description"
        ),
        icon_class=str(raw.get("icon_class") or "rmc-icon-wizard"),
        estimated_minutes=int(raw.get("estimated_minutes") or 10),
        gates=raw.get("gates") or {},
        ai=raw.get("ai") or {},
        steps=steps,
    )


def _import_dotted(path: str) -> Any:
    """Import ``module.path::callable``. Raise ResolverImportError on fail."""
    if "::" not in path:
        raise ResolverImportError(f"invalid dotted path {path!r}; expected 'module::callable'")
    mod_path, attr = path.split("::", 1)
    try:
        module = importlib.import_module(mod_path)
    except ImportError as exc:
        raise ResolverImportError(f"cannot import module {mod_path!r}: {exc}") from exc
    if not hasattr(module, attr):
        raise ResolverImportError(f"module {mod_path!r} has no attribute {attr!r}")
    obj = getattr(module, attr)
    if not callable(obj):
        raise ResolverImportError(f"{path!r} is not callable")
    return obj


def _validate_resolver_paths(wizard: WizardDefinition) -> None:
    """Best-effort: import every resolver. Failures are logged WARNING but don't crash registry.

    This keeps app-boot resilient against stub wizards while still surfacing breakage in
    ``verify_unified_wizard_framework.py`` CI gate.
    """
    for step in wizard.steps:
        for path in filter(None, [step.options_resolver, step.next_step_resolver,
                                   step.persistence.get("writer")]):
            try:
                _import_dotted(path)
            except ResolverImportError as exc:
                logger.warning(
                    "wizard %s step %s resolver import failed: %s",
                    wizard.wizard_key, step.key, exc,
                )


def load_wizard_registry(directory: Path | None = None) -> dict[str, WizardDefinition]:
    """Walk ``wizards/*.json``, parse, validate, populate WIZARD_REGISTRY.

    Idempotent. Returns the registry.

    Wizards with the metadata field ``"feature_flag_disabled": true`` are
    parsed (for schema enforcement) but not added to the live registry.
    """
    target = directory or _default_wizards_dir()
    WIZARD_REGISTRY.clear()

    if not target.exists():
        logger.info("wizard registry: directory %s does not exist", target)
        return WIZARD_REGISTRY

    for json_path in sorted(target.glob("*.json")):
        if json_path.name.startswith("_"):
            continue
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("wizard registry: failed to load %s: %s", json_path, exc)
            continue
        try:
            wizard = _parse_wizard(raw, json_path)
        except WizardSchemaError as exc:
            logger.error("wizard registry: schema error in %s: %s", json_path, exc)
            continue

        if raw.get("feature_flag_disabled") is True:
            logger.info("wizard registry: %s parsed but feature_flag_disabled", wizard.wizard_key)
            continue

        if wizard.wizard_key in WIZARD_REGISTRY:
            logger.error("wizard registry: duplicate wizard_key %s in %s", wizard.wizard_key, json_path)
            continue

        WIZARD_REGISTRY[wizard.wizard_key] = wizard
        _validate_resolver_paths(wizard)

    logger.info("wizard registry: loaded %d wizards", len(WIZARD_REGISTRY))
    return WIZARD_REGISTRY


def get_wizard(wizard_key: str) -> WizardDefinition:
    """Return WizardDefinition or raise WizardNotFound."""
    if wizard_key not in WIZARD_REGISTRY:
        raise WizardNotFound(wizard_key)
    return WIZARD_REGISTRY[wizard_key]


def list_wizards_for_audience(audience: str) -> list[WizardDefinition]:
    """Filter registry by audience. Stable ordering by wizard_key."""
    out = [w for w in WIZARD_REGISTRY.values() if audience in w.audience]
    return sorted(out, key=lambda w: w.wizard_key)


# ---------- Options + branching ----------


def resolve_options(step: StepDefinition, *, request: Any, school: Any) -> list[dict[str, Any]]:
    """Import and call the options_resolver dotted path.

    Returns ``[]`` if step has no options_resolver. Returns a list of
    ``{value, label_token, metadata}`` dicts.
    """
    if not step.options_resolver:
        return []
    try:
        fn = _import_dotted(step.options_resolver)
        result = fn(request=request, school=school)
    except ResolverImportError as exc:
        logger.error("options_resolver import failed for step %s: %s", step.key, exc)
        return []
    except Exception as exc:  # noqa: BLE001 — resolver failure must not crash the wizard
        logger.exception("options_resolver call failed for step %s: %s", step.key, exc)
        return []

    if not isinstance(result, list):
        logger.error("options_resolver %s returned non-list", step.options_resolver)
        return []
    return result


def resolve_next_step(
    wizard: WizardDefinition,
    *,
    current_step: StepDefinition,
    current_answer: dict[str, Any] | None = None,
    progress_state: dict[str, Any] | None = None,
) -> StepDefinition | None:
    """Apply declarative branches OR call next_step_resolver. ``None`` = end of wizard."""
    current_answer = current_answer or {}
    progress_state = progress_state or {}

    # Declarative branches: branch keys can be exact match OR pipe-delimited set
    # (e.g. "BR|IN|KE" → matches if answer ∈ {"BR","IN","KE"}).
    if current_step.branches:
        # branch key is matched against the single-valued answer when input is single_choice,
        # OR against an explicit "branch_value" field in the answer payload.
        branch_value = current_answer.get("branch_value")
        if branch_value is None:
            for cand in ("value", "selected", "choice"):
                if cand in current_answer:
                    branch_value = current_answer[cand]
                    break

        next_key = None
        if branch_value is not None:
            for branch_pattern, target_key in current_step.branches.items():
                if branch_pattern == "default":
                    continue
                tokens = {t.strip() for t in branch_pattern.split("|")}
                if str(branch_value) in tokens:
                    next_key = target_key
                    break
        if next_key is None:
            next_key = current_step.branches.get("default")
        if next_key is None or next_key == "__end__":
            return None
        try:
            return wizard.step_by_key(next_key)
        except StepNotFound:
            logger.error("branch target %s not found in wizard %s", next_key, wizard.wizard_key)
            return None

    # Callable resolver
    if current_step.next_step_resolver:
        try:
            fn = _import_dotted(current_step.next_step_resolver)
            next_key = fn(progress_state=progress_state, current_answer=current_answer)
        except ResolverImportError as exc:
            logger.error("next_step_resolver import failed for %s: %s", current_step.key, exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.exception("next_step_resolver call failed for %s: %s", current_step.key, exc)
            return None
        if next_key is None or next_key == "__end__":
            return None
        try:
            return wizard.step_by_key(str(next_key))
        except StepNotFound:
            logger.error("next_step_resolver returned unknown key %s", next_key)
            return None

    # Sequential — next in array
    found_current = False
    for s in wizard.steps:
        if found_current:
            return s
        if s.key == current_step.key:
            found_current = True
    return None


# ---------- Validation ----------


def _run_validator(rule_name: str, value: Any, rule_value: Any) -> tuple[bool, str | None]:
    if rule_name == "required" and rule_value:
        return _val.validate_required(value)
    if rule_name == "max_length" and isinstance(rule_value, int):
        return _val.validate_max_length(value, rule_value)
    if rule_name == "min_length" and isinstance(rule_value, int):
        return _val.validate_min_length(value, rule_value)
    if rule_name == "pattern" and isinstance(rule_value, str):
        return _val.validate_pattern(value, rule_value)
    if rule_name == "decimal_min":
        return _val.validate_decimal_range(value, min=str(rule_value), max=None)
    if rule_name == "decimal_max":
        return _val.validate_decimal_range(value, min=None, max=str(rule_value))
    if rule_name == "integer_min":
        return _val.validate_integer_range(value, min=int(rule_value), max=None)
    if rule_name == "integer_max":
        return _val.validate_integer_range(value, min=None, max=int(rule_value))
    if rule_name == "allowed_extensions" and isinstance(rule_value, list):
        return _val.validate_file_extension(value, rule_value)
    if rule_name == "max_file_bytes" and isinstance(rule_value, int):
        return _val.validate_file_size_bytes(value, rule_value)
    if rule_name == "iso_country":
        return _val.validate_iso_country_code(value)
    if rule_name == "iso_currency":
        return _val.validate_iso_currency_code(value)
    if rule_name == "color_hex":
        return _val.validate_color_hex(value)
    if rule_name == "domain_format":
        return _val.validate_domain_format(value)
    if rule_name == "email_shape":
        return _val.validate_email_shape(value)
    return True, None


def validate_step_answer(
    step: StepDefinition,
    payload: dict[str, Any],
) -> tuple[bool, dict[str, str]]:
    """Returns ``(is_valid, {field_name: error_token})``.

    For ``structured_form``, iterates ``fields`` and validates each per its declared rules.
    For other input types, validates the top-level payload (which always has a ``value`` key
    by convention) against ``step.validation``.
    """
    errors: dict[str, str] = {}

    if step.input_type == "structured_form":
        declared_names = {
            fld.get("name")
            for fld in step.fields
            if isinstance(fld.get("name"), str)
        }
        # Reject unexpected attributes. The HTTP view only ever builds declared
        # keys, so this can't bite the normal flow — it hardens the public
        # apply_step_answer() boundary against programmatic / replayed payloads
        # that smuggle un-validated keys into stored state.
        for key in payload:
            if key not in declared_names and key not in _ALLOWED_PAYLOAD_META_KEYS:
                errors.setdefault(str(key), "wizards.errors.unexpected_field")
        for fld in step.fields:
            name = fld.get("name")
            if not isinstance(name, str):
                continue
            v = payload.get(name)
            if fld.get("required"):
                ok, err = _val.validate_required(v)
                if not ok:
                    errors[name] = err or "wizards.errors.required"
                    continue
            rules = fld.get("validation") or {}
            for rule_name, rule_value in rules.items():
                ok, err = _run_validator(rule_name, v, rule_value)
                if not ok:
                    errors[name] = err or "wizards.errors.unknown"
                    break
            if name not in errors and "max_length" not in rules:
                ok, err = _val.validate_text_within_cap(v, WIZARD_MAX_TEXT_FIELD_LENGTH)
                if not ok:
                    errors[name] = err or "wizards.errors.text_too_long"
    else:
        # Reject unexpected attributes (parity with structured_form above). The
        # HTTP view only ever builds the keys in _allowed_payload_keys, so this
        # can't bite the normal flow — it hardens the public apply_step_answer()
        # boundary against programmatic / replayed payloads on non-form steps.
        allowed = _allowed_payload_keys(step.input_type)
        for key in payload:
            if key not in allowed:
                errors.setdefault(str(key), "wizards.errors.unexpected_field")
        v = payload.get("value")
        if step.validation.get("required"):
            ok, err = _val.validate_required(v)
            if not ok:
                errors["value"] = err or "wizards.errors.required"
        if "value" not in errors:
            for rule_name, rule_value in step.validation.items():
                if rule_name == "required":
                    continue
                ok, err = _run_validator(rule_name, v, rule_value)
                if not ok:
                    errors["value"] = err or "wizards.errors.unknown"
                    break
        if "value" not in errors and "max_length" not in step.validation:
            ok, err = _val.validate_text_within_cap(v, WIZARD_MAX_TEXT_FIELD_LENGTH)
            if not ok:
                errors["value"] = err or "wizards.errors.text_too_long"

    return (len(errors) == 0, errors)


# ---------- Boot ----------

try:
    load_wizard_registry()
except Exception as exc:  # noqa: BLE001
    logger.exception("wizard registry: boot failure: %s", exc)
