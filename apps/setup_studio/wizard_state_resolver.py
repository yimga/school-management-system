"""Wizard state model — wraps SetupProgress.step_state for the wizard engine.

Per implementation detail §3, each school has ONE SetupProgress row whose
``step_state`` JSONField is namespaced as:

    {
        "<legacy_setup_step_key>": {...},  # preserved untouched
        "wizards": {
            "<wizard_key>": {
                "current_step_key": "...",
                "answers": {"<step_key>": {...}},
                "completed": ["...", ...],
                "schema_version": 1,
                "ai_recommendations_cache": {...},
                "started_at": "<iso>",
                "last_modified": "<iso>",
                "completed_at": "<iso>",
                "ai_request_count": 0,
                "ai_fallback_count": 0,
            }
        }
    }

No migrations required — uses existing SetupProgress.step_state JSONField.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from django.db import transaction

from apps.setup_studio import wizard_engine, wizard_telemetry
from apps.setup_studio.models import SetupProgress

logger = logging.getLogger(__name__)

__all__ = [
    "WIZARD_STATE_SCHEMA_VERSION",
    "get_or_create_progress",
    "get_wizard_state",
    "start_wizard",
    "apply_step_answer",
    "reset_wizard",
    "export_wizard_state",
    "restore_wizard_state",
    "is_wizard_completed",
]

WIZARD_STATE_SCHEMA_VERSION = 1


# ---------- PII sanitization (mirrors apps.migration_cloud.models_audit._sanitize_payload) ----------

_SENSITIVE_KEY_FRAGMENTS = (
    "password", "passwd", "pwd", "secret", "token", "hash",
    "ssn", "dob", "api_key", "apikey", "private_key",
    "signature_text",
    # Wizard-specific additions:
    "pfx_bytes", "cert_bytes", "raw_pii",
)


def _is_sensitive_key(key: str) -> bool:
    lk = key.lower()
    return any(frag in lk for frag in _SENSITIVE_KEY_FRAGMENTS)


def _sanitize_for_storage(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _is_sensitive_key(str(k)):
                out[k] = "[REDACTED]"
            else:
                out[k] = _sanitize_for_storage(v)
        return out
    if isinstance(value, list):
        return [_sanitize_for_storage(v) for v in value]
    if isinstance(value, bytes):
        return f"[BYTES len={len(value)}]"
    # File-like objects (Django UploadedFile etc.) — record metadata only,
    # never the bytes. The actual file is handled by the per-domain writer
    # (apps.brand_experience.services.install_brand_assets etc.).
    if not isinstance(value, str) and (
        hasattr(value, "read") or hasattr(value, "size")
    ) and hasattr(value, "name"):
        return {
            "file_name": getattr(value, "name", None),
            "file_size": getattr(value, "size", None),
        }
    return value


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------- Public API ----------


def get_or_create_progress(school: Any) -> SetupProgress:
    """One row per school. Creates if absent."""
    if school is None or getattr(school, "pk", None) is None:
        raise ValueError("get_or_create_progress: school must have pk")
    progress, _ = SetupProgress.objects.get_or_create(school=school)
    return progress


def _read_wizards_slice(progress: SetupProgress) -> dict[str, Any]:
    step_state = progress.step_state or {}
    return step_state.get("wizards") or {}


def _write_wizards_slice(progress: SetupProgress, wizards_slice: dict[str, Any]) -> None:
    step_state = progress.step_state or {}
    if not isinstance(step_state, dict):
        step_state = {}
    step_state["wizards"] = wizards_slice
    progress.step_state = step_state


def get_wizard_state(school: Any, wizard_key: str) -> dict[str, Any]:
    """Returns the wizard's slice (empty dict if not started)."""
    progress = get_or_create_progress(school)
    wizards = _read_wizards_slice(progress)
    return wizards.get(wizard_key) or {}


def is_wizard_completed(school: Any, wizard_key: str) -> bool:
    state = get_wizard_state(school, wizard_key)
    return bool(state.get("completed_at"))


@transaction.atomic
def start_wizard(school: Any, wizard_key: str) -> dict[str, Any]:
    """Initialize state if absent. Idempotent — returns existing state if already started."""
    wizard = wizard_engine.get_wizard(wizard_key)
    progress = (
        SetupProgress.objects
        .select_for_update()
        .get_or_create(school=school)[0]
    )
    wizards = _read_wizards_slice(progress)
    existing = wizards.get(wizard_key)
    if existing:
        return existing

    fresh = {
        "current_step_key": wizard.first_step().key,
        "answers": {},
        "completed": [],
        "schema_version": WIZARD_STATE_SCHEMA_VERSION,
        "ai_recommendations_cache": {},
        "started_at": _now_iso(),
        "last_modified": _now_iso(),
        "ai_request_count": 0,
        "ai_fallback_count": 0,
    }
    wizards[wizard_key] = fresh
    _write_wizards_slice(progress, wizards)
    progress.save(update_fields=["step_state", "updated_at"])
    return fresh


@transaction.atomic
def apply_step_answer(
    school: Any,
    wizard_key: str,
    step_key: str,
    payload: dict[str, Any],
    *,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    """Validate payload, persist, advance current_step_key. Returns new state."""
    wizard = wizard_engine.get_wizard(wizard_key)
    step = wizard.step_by_key(step_key)

    is_valid, errors = wizard_engine.validate_step_answer(step, payload)
    if not is_valid:
        for fname in errors:
            wizard_telemetry.emit_step_validation_failed(wizard_key, step_key, fname)
        raise wizard_engine.WizardError(f"validation failed: {errors}")

    progress = (
        SetupProgress.objects
        .select_for_update()
        .get_or_create(school=school)[0]
    )
    wizards = _read_wizards_slice(progress)
    state = wizards.get(wizard_key) or {
        "current_step_key": wizard.first_step().key,
        "answers": {},
        "completed": [],
        "schema_version": WIZARD_STATE_SCHEMA_VERSION,
        "ai_recommendations_cache": {},
        "started_at": _now_iso(),
        "last_modified": _now_iso(),
        "ai_request_count": 0,
        "ai_fallback_count": 0,
    }

    sanitized_payload = _sanitize_for_storage(payload)
    state["answers"][step_key] = sanitized_payload
    if step_key not in state["completed"]:
        state["completed"].append(step_key)

    # Side effect: invoke persistence writer if declared
    writer_path = step.persistence.get("writer") if step.persistence else None
    if writer_path:
        try:
            writer = wizard_engine._import_dotted(writer_path)
            writer(
                school=school,
                wizard_key=wizard_key,
                step_key=step_key,
                payload=payload,  # writer gets ORIGINAL payload (incl. file objects)
                actor_user_id=actor_user_id,
            )
        except wizard_engine.ResolverImportError as exc:
            logger.error("persistence writer import failed for %s.%s: %s", wizard_key, step_key, exc)
            wizard_telemetry.emit_persistence_failed(wizard_key, step_key, writer_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("persistence writer failed for %s.%s: %s", wizard_key, step_key, exc)
            wizard_telemetry.emit_persistence_failed(wizard_key, step_key, writer_path)

    # Advance current_step_key
    next_step = wizard_engine.resolve_next_step(
        wizard,
        current_step=step,
        current_answer=payload,
        progress_state=state,
    )
    if next_step is None:
        state["current_step_key"] = None
        state["completed_at"] = _now_iso()
        try:
            started_at = datetime.fromisoformat(state["started_at"].replace("Z", "+00:00"))
            duration = int((datetime.now(tz=timezone.utc) - started_at).total_seconds())
        except (KeyError, ValueError, TypeError):
            duration = 0
        wizard_telemetry.emit_wizard_completed(wizard_key, _primary_audience(wizard), duration)
    else:
        state["current_step_key"] = next_step.key

    state["last_modified"] = _now_iso()
    wizards[wizard_key] = state
    _write_wizards_slice(progress, wizards)
    progress.save(update_fields=["step_state", "updated_at"])

    wizard_telemetry.emit_step_applied(wizard_key, step_key, _primary_audience(wizard))
    return state


@transaction.atomic
def reset_wizard(school: Any, wizard_key: str, *, actor_user_id: int | None = None) -> None:
    """Drop the wizard's slice. Used by 'restart' UI affordance and tests."""
    progress = (
        SetupProgress.objects
        .select_for_update()
        .get_or_create(school=school)[0]
    )
    wizards = _read_wizards_slice(progress)
    if wizard_key in wizards:
        del wizards[wizard_key]
        _write_wizards_slice(progress, wizards)
        progress.save(update_fields=["step_state", "updated_at"])


def export_wizard_state(school: Any, wizard_key: str) -> dict[str, Any]:
    """PII-sanitized export. Defense-in-depth — storage is already sanitized."""
    state = get_wizard_state(school, wizard_key)
    return _sanitize_for_storage(deepcopy(state))


@transaction.atomic
def restore_wizard_state(
    school: Any,
    wizard_key: str,
    state: dict[str, Any],
    *,
    actor_user_id: int | None = None,
) -> None:
    """Reverse of export. For tests + tenant migrations."""
    progress = (
        SetupProgress.objects
        .select_for_update()
        .get_or_create(school=school)[0]
    )
    wizards = _read_wizards_slice(progress)
    wizards[wizard_key] = _sanitize_for_storage(deepcopy(state))
    _write_wizards_slice(progress, wizards)
    progress.save(update_fields=["step_state", "updated_at"])


def _primary_audience(wizard: wizard_engine.WizardDefinition) -> str:
    return wizard.audience[0] if wizard.audience else "unknown"
