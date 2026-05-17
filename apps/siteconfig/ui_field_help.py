"""
UI field / feature explainer copy for ``rmc_info_tag``.

Layer 1: static registry (always available).
Layer 2: metadata ``FieldCatalogEntry`` + ``EntityCatalogEntry`` labels/descriptions.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

# key: "entity.field" or "surface.feature"
UI_FIELD_HELP: dict[str, dict[str, str]] = {
    "invoice.status": {
        "title": _("Invoice status"),
        "body": _(
            "Draft, sent, partial, paid, or overdue — drives reminders and parent visibility."
        ),
    },
    "invoice.reference": {
        "title": _("Invoice reference"),
        "body": _("Unique identifier used in search, exports, and payment matching."),
    },
    "applicant.stage": {
        "title": _("Applicant stage"),
        "body": _("Pipeline step from enquiry through enrollment; filters the queue."),
    },
    "gradebook.approval": {
        "title": _("Grade approval"),
        "body": _(
            "Some schools require leadership approval before marks publish to reports."
        ),
    },
    "studio.mode": {
        "title": _("Studio mode"),
        "body": _(
            "Experience, Automation, Outputs, Launch, and Control — one workspace per job."
        ),
    },
    "notification.severity": {
        "title": _("Notification severity"),
        "body": _("Alerts need action; warnings are time-sensitive; updates are informational."),
    },
    "backend.intent": {
        "title": _("Dashboard intent"),
        "body": _(
            "Operational view surfaces live KPIs; setup view emphasizes go-live checklist."
        ),
    },
    "finance.access": {
        "title": _("Finance access"),
        "body": _(
            "Role-gated — request broader access if invoices or payments are hidden."
        ),
    },
}


def _catalog_lookup(entity_code: str, field_name: str) -> dict[str, str]:
    try:
        from apps.metadata.models import (
            ENTITY_CATALOG_LIFECYCLE_ACTIVE,
            FieldCatalogEntry,
        )

        row = (
            FieldCatalogEntry.objects.select_related("entity")
            .filter(
                entity__code=entity_code,
                field_name=field_name,
                entity__lifecycle_state=ENTITY_CATALOG_LIFECYCLE_ACTIVE,
            )
            .first()
        )
        if not row:
            return {}
        title = row.label or row.field_name.replace("_", " ").title()
        body = (row.entity.description or "").strip()
        if row.data_type:
            type_hint = _("Type: %(type)s") % {"type": row.data_type}
            body = f"{body} {type_hint}".strip() if body else type_hint
        return {"title": title, "body": body}
    except Exception:
        return {}


def get_ui_field_help(entity_code: str, field_name: str = "", *, feature: str = "") -> dict[str, Any]:
    """
    Return {title, body} for popover copy.

    Prefer explicit *feature* (surface.feature) when set; else entity.field.
    """
    key = ""
    if feature:
        key = feature if "." in feature else f"surface.{feature}"
    elif entity_code and field_name:
        key = f"{entity_code}.{field_name}"
    if key:
        static = UI_FIELD_HELP.get(key)
        if static:
            return {"title": str(static["title"]), "body": str(static["body"])}
    if entity_code and field_name:
        db = _catalog_lookup(entity_code, field_name)
        if db.get("title"):
            return db
    return {"title": "", "body": ""}
