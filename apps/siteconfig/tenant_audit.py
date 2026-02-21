from __future__ import annotations

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist


COMMUNICATION_TENANT_MODELS: tuple[str, ...] = (
    "communication.Message",
    "communication.DirectConversation",
    "communication.Announcement",
    "communication.AnnouncementAuditLog",
    "communication.ClassAnnouncement",
    "communication.MessageThread",
    "communication.ThreadMessage",
    "communication.ThreadReadState",
    "communication.AlertRule",
    "communication.ContactRequest",
    "communication.ContactRequestAttachment",
)


def _normalize_model_label(model_label: str) -> str:
    app_label, model_name = model_label.split(".", 1)
    return f"{app_label}.{model_name}"


def has_explicit_school_field(model_label: str) -> bool:
    app_label, model_name = model_label.split(".", 1)
    model = apps.get_model(app_label, model_name)
    try:
        field = model._meta.get_field("school")
    except FieldDoesNotExist:
        return False
    return bool(
        field.is_relation
        and getattr(field, "many_to_one", False)
        and getattr(getattr(field, "related_model", None), "_meta", None)
        and field.related_model._meta.label_lower == "schools.school"
    )


def find_missing_explicit_school_fields(model_labels: list[str] | tuple[str, ...] | None = None) -> list[str]:
    labels = model_labels or COMMUNICATION_TENANT_MODELS
    missing = []
    for label in labels:
        normalized = _normalize_model_label(label)
        if not has_explicit_school_field(normalized):
            missing.append(normalized)
    return missing
