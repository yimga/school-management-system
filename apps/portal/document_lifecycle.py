from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


DOCUMENT_LIFECYCLE_DRAFT = "draft"
DOCUMENT_LIFECYCLE_REVIEW = "review"
DOCUMENT_LIFECYCLE_APPROVED = "approved"
DOCUMENT_LIFECYCLE_ARCHIVED = "archived"
DOCUMENT_LIFECYCLE_RETRACTED = "retracted"

DEFAULT_DOCUMENT_LIFECYCLE_STATES = [
    DOCUMENT_LIFECYCLE_DRAFT,
    DOCUMENT_LIFECYCLE_REVIEW,
    DOCUMENT_LIFECYCLE_APPROVED,
    DOCUMENT_LIFECYCLE_ARCHIVED,
]

DOCUMENT_LIFECYCLE_CHOICES = [
    (DOCUMENT_LIFECYCLE_DRAFT, _("Draft")),
    (DOCUMENT_LIFECYCLE_REVIEW, _("In review")),
    (DOCUMENT_LIFECYCLE_APPROVED, _("Approved")),
    (DOCUMENT_LIFECYCLE_ARCHIVED, _("Archived")),
    (DOCUMENT_LIFECYCLE_RETRACTED, _("Retracted")),
]

DOCUMENT_LIFECYCLE_VALID_TRANSITIONS = {
    DOCUMENT_LIFECYCLE_DRAFT: (
        DOCUMENT_LIFECYCLE_REVIEW,
        DOCUMENT_LIFECYCLE_APPROVED,
        DOCUMENT_LIFECYCLE_RETRACTED,
    ),
    DOCUMENT_LIFECYCLE_REVIEW: (
        DOCUMENT_LIFECYCLE_APPROVED,
        DOCUMENT_LIFECYCLE_RETRACTED,
        DOCUMENT_LIFECYCLE_DRAFT,
    ),
    DOCUMENT_LIFECYCLE_APPROVED: (
        DOCUMENT_LIFECYCLE_ARCHIVED,
        DOCUMENT_LIFECYCLE_RETRACTED,
        DOCUMENT_LIFECYCLE_REVIEW,
    ),
    DOCUMENT_LIFECYCLE_ARCHIVED: (DOCUMENT_LIFECYCLE_APPROVED,),
    DOCUMENT_LIFECYCLE_RETRACTED: (),
}


def normalize_document_pack_states(pack: Any = None) -> list[str]:
    lifecycle_states = getattr(pack, "lifecycle_states", None) or []
    if not isinstance(lifecycle_states, list):
        lifecycle_states = []
    normalized = []
    for state in lifecycle_states:
        candidate = slugify(str(state or "").replace("_", "-")).replace("-", "_")
        if candidate:
            normalized.append(candidate)
    return normalized or list(DEFAULT_DOCUMENT_LIFECYCLE_STATES)


def normalize_document_retention_rule(pack: Any = None) -> dict[str, int | None]:
    payload = getattr(pack, "retention_rule", None) or {}
    if not isinstance(payload, Mapping):
        payload = {}
    archive_after_days = payload.get("archive_after_days")
    expire_after_days = payload.get("expire_after_days")
    try:
        archive_after_days = (
            int(archive_after_days) if archive_after_days not in (None, "") else None
        )
    except (TypeError, ValueError):
        archive_after_days = None
    try:
        expire_after_days = (
            int(expire_after_days) if expire_after_days not in (None, "") else None
        )
    except (TypeError, ValueError):
        expire_after_days = None
    return {
        "archive_after_days": archive_after_days,
        "expire_after_days": expire_after_days,
    }


def lifecycle_state_choices(pack: Any = None) -> list[tuple[str, str]]:
    allowed = set(normalize_document_pack_states(pack))
    allowed.add(DOCUMENT_LIFECYCLE_RETRACTED)
    return [
        (code, label) for code, label in DOCUMENT_LIFECYCLE_CHOICES if code in allowed
    ]


def is_valid_document_transition(
    previous_state: str | None, next_state: str, pack: Any = None
) -> bool:
    normalized_next = str(next_state or "").strip().lower()
    allowed_states = set(normalize_document_pack_states(pack))
    allowed_states.add(DOCUMENT_LIFECYCLE_RETRACTED)
    if normalized_next not in allowed_states:
        return False
    previous = str(previous_state or "").strip().lower()
    if not previous:
        return True
    allowed = DOCUMENT_LIFECYCLE_VALID_TRANSITIONS.get(previous, ())
    return normalized_next == previous or normalized_next in allowed


def calculate_document_retention_review_at(document: Any) -> Any:
    rule = normalize_document_retention_rule(getattr(document, "document_pack", None))
    archive_after_days = rule.get("archive_after_days")
    if archive_after_days is None:
        return None
    base_dt = (
        getattr(document, "published_at", None)
        or getattr(document, "created_at", None)
        or timezone.now()
    )
    if hasattr(base_dt, "date"):
        base_date = base_dt.date()
    else:
        base_date = timezone.now().date()
    return base_date + timedelta(days=int(archive_after_days))


def build_document_search_index(document: Any) -> str:
    values = [
        getattr(document, "title", ""),
        getattr(document, "description", ""),
        getattr(document, "document_type", ""),
        getattr(document, "lifecycle_state", ""),
        getattr(getattr(document, "category", None), "name", ""),
        getattr(getattr(document, "category", None), "slug", ""),
        getattr(getattr(document, "document_pack", None), "name", ""),
        getattr(getattr(document, "document_pack", None), "code", ""),
        getattr(getattr(document, "created_by", None), "username", ""),
    ]
    file_value = getattr(document, "file", None)
    if file_value is not None:
        values.append(getattr(file_value, "name", ""))
    roles = getattr(document, "visible_to_roles", None) or []
    if isinstance(roles, list):
        values.extend(str(role) for role in roles)
    return " ".join(
        str(value).strip() for value in values if str(value).strip()
    ).lower()
