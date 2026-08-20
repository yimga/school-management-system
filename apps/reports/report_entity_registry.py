"""Operational report entity registry — how the platform reports *anything*.

Official artifacts (report cards, certificates) stay in ``apps.reports`` kernels.
Ministry/state packs stay in ``state_reporting`` / ``moe_presets``.
This module is the **operational** rail: any named entity with a tenant-scoped
model can emit CSV/JSON without a new hand-written exporter.

Coverage SOT:
  * Every ``seed_entity_catalog.CATALOG_ENTITIES`` code has a row here
    (runnable or an explicit ``deny_reason``).
  * Ad-hoc ``entity_type`` aliases resolve through ``resolve_entity``.
  * Unknown CUSTOM must fail closed — never silently dump students.

Adding a domain: append a ``ReportableEntity`` (model_label + school_lookup).
The generic ORM runner + DLP field skip do the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db.models import ForeignKey, QuerySet

_SECRET_FIELD_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "private_key",
    "api_key",
    "ciphertext",
    "hash",
)
_MAX_ROWS = 5000  # magic-number-allow: operational-report-row-cap
_KIND_OPERATIONAL = "operational"
_KIND_DENIED = "denied"


@dataclass(frozen=True)
class ReportableEntity:
    """One reportable (or explicitly not-reportable) platform entity."""

    code: str
    model_label: str
    aliases: tuple[str, ...] = ()
    school_lookup: str = "school_id"
    date_field: str | None = None
    kind: str = _KIND_OPERATIONAL
    deny_reason: str = ""

    @property
    def runnable(self) -> bool:
        return self.kind == _KIND_OPERATIONAL and not self.deny_reason


# Catalog codes from ``apps.metadata.management.commands.seed_entity_catalog``
# plus first extras (inventory). Denied rows are honest: the seed names a model
# that does not exist, or the model is shared-auth and must not be dumped.
REPORTABLE_ENTITIES: tuple[ReportableEntity, ...] = (
    ReportableEntity(
        code="person",
        model_label="accounts.User",
        aliases=("PERSON", "people.User"),
        kind=_KIND_DENIED,
        deny_reason="shared-auth-user-report-via-staff-or-guardian",
    ),
    ReportableEntity(
        code="student",
        model_label="people.StudentProfile",
        aliases=("STUDENTS", "ENROLLMENT", "people.StudentProfile"),
        date_field=None,
    ),
    ReportableEntity(
        code="parent_guardian",
        model_label="people.StudentGuardian",
        aliases=("GUARDIANS", "people.StudentGuardian"),
        school_lookup="student__school_id",
    ),
    ReportableEntity(
        code="staff",
        model_label="people.TeacherProfile",
        aliases=("STAFF", "TEACHERS", "people.TeacherProfile"),
    ),
    ReportableEntity(
        code="classroom",
        model_label="academics.Classroom",
        aliases=("CLASSROOMS", "academics.Classroom"),
    ),
    ReportableEntity(
        code="section",
        model_label="academics.Section",
        aliases=("SECTIONS", "academics.Section"),
        kind=_KIND_DENIED,
        deny_reason="catalog-stale-no-academics-Section-model-use-classroom",
    ),
    ReportableEntity(
        code="attendance",
        model_label="academics.Attendance",
        aliases=("ATTENDANCE", "academics.Attendance"),
        date_field="date",
    ),
    ReportableEntity(
        code="grade",
        model_label="evals.Evaluation",
        aliases=("GRADES", "evals.Grade", "evals.Evaluation"),
        date_field="created_at",
    ),
    ReportableEntity(
        code="invoice",
        model_label="finance.Invoice",
        aliases=("FINANCE", "INVOICES", "finance.Invoice"),
        date_field="created_at",
    ),
    ReportableEntity(
        code="payment",
        model_label="finance.Payment",
        aliases=("PAYMENTS", "finance.Payment"),
        date_field="paid_at",
    ),
    ReportableEntity(
        code="application",
        model_label="people.Applicant",
        aliases=("APPLICANTS", "people.Applicant"),
        date_field="created_at",
    ),
    ReportableEntity(
        code="communication",
        model_label="communication.Announcement",
        aliases=("ANNOUNCEMENTS", "communication.Announcement"),
        date_field="created_at",
    ),
    ReportableEntity(
        code="inventory",
        model_label="schoolops.InventoryItem",
        aliases=("INVENTORY", "schoolops.InventoryItem"),
    ),
)


def _index() -> dict[str, ReportableEntity]:
    out: dict[str, ReportableEntity] = {}
    for ent in REPORTABLE_ENTITIES:
        out[ent.code.lower()] = ent
        out[ent.model_label.lower()] = ent
        for alias in ent.aliases:
            out[str(alias).lower()] = ent
    return out


_ENTITY_INDEX: dict[str, ReportableEntity] | None = None


def all_reportable() -> tuple[ReportableEntity, ...]:
    return REPORTABLE_ENTITIES


def resolve_entity(code: str) -> ReportableEntity | None:
    """Resolve an ad-hoc type, catalog code, or ``app.Model`` label."""

    global _ENTITY_INDEX
    if _ENTITY_INDEX is None:
        _ENTITY_INDEX = _index()
    key = str(code or "").strip().lower()
    if not key:
        return None
    return _ENTITY_INDEX.get(key)


def _is_secret_field(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _SECRET_FIELD_TOKENS)


def _concrete_field_names(model) -> set[str]:
    names: set[str] = set()
    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if getattr(field, "many_to_many", False):
            continue
        if getattr(field, "one_to_many", False):
            continue
        name = str(getattr(field, "name", "") or "")
        if not name or _is_secret_field(name):
            continue
        names.add(name)
        if isinstance(field, ForeignKey):
            names.add(f"{name}_id")
    return names


def _related_prefix_ok(column: str, allowed: set[str]) -> bool:
    if "__" not in column:
        return False
    head = column.split("__", 1)[0]
    return head in allowed or f"{head}_id" in allowed


def build_entity_queryset(
    entity: ReportableEntity,
    *,
    columns: list | None,
    filters: dict | None,
    date_from=None,
    date_to=None,
    school_id=None,
    allow_global: bool = False,
) -> tuple[QuerySet, list[str]]:
    """Tenant-scoped queryset + safe column list for one registry entity."""

    if not entity.runnable:
        raise ValueError(
            f"entity {entity.code!r} is not reportable: {entity.deny_reason}"
        )
    if not school_id and not allow_global:
        raise ValueError("school_id required for tenant-scoped ad-hoc report execution")

    try:
        app_label, model_name = entity.model_label.split(".", 1)
    except ValueError as exc:
        raise ValueError(f"invalid model_label {entity.model_label!r}") from exc
    model = apps.get_model(app_label, model_name)
    # tenant-isolation-allow: operational-report-queryset-school-lookup-from-registry
    qs = model.objects.all()
    if school_id:
        qs = qs.filter(**{entity.school_lookup: school_id})

    date_field = entity.date_field
    if date_field:
        try:
            model._meta.get_field(date_field.split("__", 1)[0])
        except FieldDoesNotExist:
            date_field = None
    if date_field and date_from:
        qs = qs.filter(**{f"{date_field}__gte": date_from})
    if date_field and date_to:
        lookup = date_field
        if date_field.endswith("_at"):
            lookup = f"{date_field}__date"
        qs = qs.filter(**{f"{lookup}__lte": date_to})

    allowed = _concrete_field_names(model)
    for key, val in (filters or {}).items():
        if key in {"entity_code", "model_label", "catalog_code"}:
            continue
        if key in allowed or _related_prefix_ok(str(key), allowed):
            qs = qs.filter(**{key: val})

    requested = list(columns or [])
    headers = [
        c
        for c in requested
        if c in allowed or c == "id" or _related_prefix_ok(str(c), allowed)
    ]
    if not headers:
        headers = ["id"]
    qs = qs.order_by("pk")[:_MAX_ROWS]
    return qs, headers


def queryset_for_code(
    code: str,
    **kwargs: Any,
) -> tuple[QuerySet, list[str]]:
    entity = resolve_entity(code)
    if entity is None:
        raise ValueError(f"unknown report entity {code!r}")
    return build_entity_queryset(entity, **kwargs)
