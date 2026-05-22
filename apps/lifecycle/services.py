"""Lifecycle service layer: record / advance / introspect.

Public API:
    record_stage(school, stage, actor=None, note="", payload=None) -> SchoolLifecycleStage
    current_stage(school) -> Stage value or None
    timeline_for(school, limit=200) -> queryset
    actor_hash(user_or_id) -> 12-hex string

All writes go through record_stage() so PII sanitization is enforced
centrally. Direct .objects.create() calls are an anti-pattern.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Iterable, Optional

from django.db import transaction

from .models import SchoolLifecycleStage, TERMINAL_STAGES

logger = logging.getLogger(__name__)


# Keys never persisted in stage.payload. Mirrors the Migration Cloud
# audit-event sanitizer to keep the same hygiene contract across the
# platform.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "hash",
        "secret",
        "token",
        "ssn",
        "dob",
        "api_key",
        "apikey",
        "private_key",
        "signature_text",
        "email",
        "slug",
    }
)


def actor_hash(user_or_id: Any) -> str:
    """Return a 12-char SHA-256 hex prefix for an actor id.

    Returns empty string for None / anonymous / unresolvable. Never
    raises — this is a logging concern, not a request-blocking concern.
    """
    if user_or_id is None:
        return ""
    raw_id: Optional[str] = None
    if hasattr(user_or_id, "id") and getattr(user_or_id, "id", None) is not None:
        raw_id = str(user_or_id.id)
    elif hasattr(user_or_id, "pk") and getattr(user_or_id, "pk", None) is not None:
        raw_id = str(user_or_id.pk)
    elif isinstance(user_or_id, (str, int)):
        raw_id = str(user_or_id)
    if not raw_id:
        return ""
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:12]


def _sanitize_payload(payload: Optional[dict]) -> dict:
    """Drop any key whose lowercased name matches the sensitive-key list.

    Walks one level deep — nested dicts get the same treatment. Lists
    pass through unchanged (caller's responsibility to not stuff raw
    secrets into list values).
    """
    if not payload:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if key.lower() in _SENSITIVE_KEYS:
            continue
        if isinstance(value, dict):
            out[key] = _sanitize_payload(value)
        else:
            out[key] = value
    return out


def record_stage(
    school,
    stage: str,
    *,
    actor: Any = None,
    note: str = "",
    payload: Optional[dict] = None,
) -> SchoolLifecycleStage:
    """Append a new lifecycle stage row.

    Safe to call from signals, mgmt commands, tasks, or view handlers.
    Never raises on duplicate stage (lifecycle is intentionally
    append-only: a school can re-enter MIGRATING after OPERATING).
    Refuses to write past a terminal stage — returns the existing
    terminal row instead.
    """
    if not school or not getattr(school, "id", None):
        raise ValueError("record_stage requires a saved School instance")
    valid_stages = {choice[0] for choice in SchoolLifecycleStage.Stage.choices}
    if stage not in valid_stages:
        raise ValueError(f"unknown lifecycle stage: {stage!r}")
    with transaction.atomic():
        latest = (
            SchoolLifecycleStage.objects.filter(school=school)
            .order_by("-created_at")
            .first()
        )
        if latest is not None and latest.stage in TERMINAL_STAGES:
            logger.warning(
                "lifecycle.record_stage.refused_past_terminal school_id=%s prev=%s requested=%s",
                school.id,
                latest.stage,
                stage,
            )
            return latest
        row = SchoolLifecycleStage.objects.create(
            school=school,
            stage=stage,
            actor_hash=actor_hash(actor),
            note=(note or "")[:200],
            payload=_sanitize_payload(payload),
        )
    return row


def current_stage(school) -> Optional[str]:
    """Latest stage value for a school, or None if never recorded."""
    if not school or not getattr(school, "id", None):
        return None
    row = (
        SchoolLifecycleStage.objects.filter(school=school)
        .order_by("-created_at")
        .only("stage")
        .first()
    )
    return row.stage if row else None


def timeline_for(school, *, limit: int = 200) -> Iterable[SchoolLifecycleStage]:
    """Return the ordered timeline for a school (newest first)."""
    if not school or not getattr(school, "id", None):
        return SchoolLifecycleStage.objects.none()
    return (
        SchoolLifecycleStage.objects.filter(school=school)
        .order_by("-created_at")[: max(1, int(limit))]
    )


def stage_counts(stages: Iterable[SchoolLifecycleStage]) -> dict:
    """Aggregate a timeline into a {stage: count} dict for the dashboard."""
    out: dict = {}
    for row in stages:
        out[row.stage] = out.get(row.stage, 0) + 1
    return out
