from __future__ import annotations

from collections import defaultdict
from typing import Any

from apps.metadata.models import (
    DynamicFieldDefinition,
    DynamicFieldValue,
    EntityCatalogEntry,
    ENTITY_CATALOG_LIFECYCLE_ACTIVE,
    FieldCatalogEntry,
    MetadataDependency,
)


def entity_type_for(instance_or_entity_type: Any) -> str:
    if isinstance(instance_or_entity_type, str):
        return instance_or_entity_type
    meta = getattr(instance_or_entity_type, "_meta", None)
    if meta is None:
        raise ValueError(
            "Metadata entity must be a Django model instance or explicit entity type."
        )
    return f"{meta.app_label}.{meta.model_name}"


def entity_id_for(instance: Any) -> str:
    pk = getattr(instance, "pk", None)
    if pk is None:
        raise ValueError(
            "Metadata entity must have a primary key before metadata can be resolved."
        )
    return str(pk)


def school_for_entity(instance: Any, school=None):
    if school is not None:
        return school
    return getattr(instance, "school", None)


def unwrap_value(value_json: Any) -> Any:
    if isinstance(value_json, dict) and set(value_json.keys()) == {"v"}:
        return value_json.get("v")
    return value_json


def wrap_value(value: Any) -> dict[str, Any]:
    return {"v": value}


def legacy_custom_attributes(instance: Any) -> dict[str, Any]:
    custom = getattr(instance, "custom_attributes", None)
    return dict(custom or {}) if isinstance(custom, dict) else {}


def get_dynamic_field_map(
    instance: Any, *, school=None, keys: list[str] | tuple[str, ...] | None = None
) -> dict[str, Any]:
    resolved_school = school_for_entity(instance, school=school)
    values = legacy_custom_attributes(instance)
    if resolved_school is None or getattr(instance, "pk", None) is None:
        if keys is None:
            return values
        return {key: values[key] for key in keys if key in values}

    et = entity_type_for(instance)
    eid = entity_id_for(instance)
    queryset = DynamicFieldValue.objects.filter(
        school=resolved_school,
        entity_type=et,
        entity_id=eid,
    )
    if keys:
        queryset = queryset.filter(field_key__in=list(keys))
    for row in queryset:
        values[row.field_key] = unwrap_value(row.value_json)

    if keys is None:
        return values
    return {key: values[key] for key in keys if key in values}


def get_dynamic_field_value(
    instance: Any, field_key: str, *, default=None, school=None
):
    values = get_dynamic_field_map(instance, school=school, keys=[field_key])
    return values.get(field_key, default)


def _guess_data_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "json"
    return "string"


def set_dynamic_field_value(
    instance: Any,
    field_key: str,
    value: Any,
    *,
    school=None,
    label: str = "",
    data_type: str = "",
    sync_legacy: bool = False,
):
    resolved_school = school_for_entity(instance, school=school)
    if resolved_school is None or getattr(instance, "pk", None) is None:
        if sync_legacy and hasattr(instance, "custom_attributes"):
            custom = legacy_custom_attributes(instance)
            custom[field_key] = value
            instance.custom_attributes = custom
        return None

    entity_type = entity_type_for(instance)
    DynamicFieldDefinition.objects.get_or_create(
        entity_type=entity_type,
        field_key=field_key,
        school=resolved_school,
        defaults={
            "label": label or field_key.replace("_", " ").title(),
            "data_type": data_type or _guess_data_type(value),
            "is_active": True,
            "required": False,
        },
    )
    field_value, _created = DynamicFieldValue.objects.update_or_create(
        school=resolved_school,
        entity_type=entity_type,
        entity_id=entity_id_for(instance),
        field_key=field_key,
        defaults={"value_json": wrap_value(value)},
    )
    if sync_legacy and hasattr(instance, "custom_attributes"):
        custom = legacy_custom_attributes(instance)
        custom[field_key] = value
        instance.custom_attributes = custom
    return field_value


# --- Lineage-first rule (Workstream I7) and catalog package export (I2) ---


def get_downstream_dependencies(
    *,
    entity_code: str | None = None,
    field_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return consumers that depend on the given entity (all its fields) or a specific field.
    Used for lineage-first rule: check downstream impact before metadata changes.
    """
    if field_id is not None:
        deps = MetadataDependency.objects.filter(field_id=field_id).select_related(
            "field", "field__entity"
        )
    elif entity_code is not None:
        deps = MetadataDependency.objects.filter(
            field__entity__code=entity_code,
        ).select_related("field", "field__entity")
    else:
        return []
    return [
        {
            "consumer_type": d.consumer_type,
            "consumer_code": d.consumer_code,
            "entity_code": d.field.entity.code,
            "field_name": d.field.field_name,
        }
        for d in deps
    ]


def summarize_dependency_consumers(
    *,
    consumer_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Group metadata dependencies by consumer so operator tooling can answer
    which APIs, templates, dashboards, workflows, and policies touch which
    entities and fields.
    """
    queryset = MetadataDependency.objects.select_related(
        "field", "field__entity"
    ).order_by(
        "consumer_type",
        "consumer_code",
        "field__entity__code",
        "field__field_name",
    )
    if consumer_type:
        queryset = queryset.filter(consumer_type=consumer_type)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for dep in queryset:
        key = (dep.consumer_type, dep.consumer_code)
        entry = grouped.setdefault(
            key,
            {
                "consumer_type": dep.consumer_type,
                "consumer_code": dep.consumer_code,
                "entity_codes": set(),
                "field_names": set(),
                "dependency_count": 0,
            },
        )
        entry["entity_codes"].add(dep.field.entity.code)
        entry["field_names"].add(dep.field.field_name)
        entry["dependency_count"] += 1

    items = []
    for entry in grouped.values():
        items.append(
            {
                "consumer_type": entry["consumer_type"],
                "consumer_code": entry["consumer_code"],
                "entity_codes": sorted(entry["entity_codes"]),
                "field_names": sorted(entry["field_names"]),
                "dependency_count": entry["dependency_count"],
            }
        )
    items.sort(key=lambda item: (item["consumer_type"], item["consumer_code"]))
    return items[:limit]


def build_metadata_blast_radius(
    *,
    entity_codes: list[str] | None = None,
    field_ids: list[int] | None = None,
    exclude_consumers: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Summarize downstream consumers affected by changing or rolling back metadata.
    This powers package impact previews and rollback safety checks.
    """
    entity_codes = [
        str(code).strip() for code in (entity_codes or []) if str(code).strip()
    ]
    field_ids = [
        int(field_id) for field_id in (field_ids or []) if field_id is not None
    ]
    exclude_consumers = exclude_consumers or set()

    queryset = MetadataDependency.objects.select_related("field", "field__entity")
    if field_ids:
        queryset = queryset.filter(field_id__in=field_ids)
    elif entity_codes:
        queryset = queryset.filter(field__entity__code__in=entity_codes)
    else:
        return {
            "entity_codes": [],
            "field_ids": [],
            "consumer_count": 0,
            "consumer_type_counts": {},
            "consumers": [],
        }

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for dep in queryset.order_by(
        "consumer_type", "consumer_code", "field__entity__code", "field__field_name"
    ):
        key = (dep.consumer_type, dep.consumer_code)
        if key in exclude_consumers:
            continue
        entry = grouped.setdefault(
            key,
            {
                "consumer_type": dep.consumer_type,
                "consumer_code": dep.consumer_code,
                "entity_codes": set(),
                "field_names": set(),
                "dependency_count": 0,
            },
        )
        entry["entity_codes"].add(dep.field.entity.code)
        entry["field_names"].add(dep.field.field_name)
        entry["dependency_count"] += 1

    consumer_type_counts: dict[str, int] = defaultdict(int)
    consumers: list[dict[str, Any]] = []
    for entry in grouped.values():
        consumer_type_counts[entry["consumer_type"]] += 1
        consumers.append(
            {
                "consumer_type": entry["consumer_type"],
                "consumer_code": entry["consumer_code"],
                "entity_codes": sorted(entry["entity_codes"]),
                "field_names": sorted(entry["field_names"]),
                "dependency_count": entry["dependency_count"],
            }
        )
    consumers.sort(key=lambda item: (item["consumer_type"], item["consumer_code"]))
    return {
        "entity_codes": sorted(set(entity_codes)),
        "field_ids": field_ids,
        "consumer_count": len(consumers),
        "consumer_type_counts": dict(sorted(consumer_type_counts.items())),
        "consumers": consumers,
    }


def get_package_lineage_registry(
    *,
    package_id: str | None = None,
    version: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Return package lineage with rollout and rollback visibility for operator
    tooling and the metadata catalog.
    """
    from apps.packages.models import InstalledPackage, PackageChangeLog, PackageVersion

    queryset = PackageVersion.objects.order_by("-created_at", "package_id")
    if package_id:
        queryset = queryset.filter(package_id=package_id)
    if version:
        queryset = queryset.filter(version=version)

    rows: list[dict[str, Any]] = []
    for pkg in queryset[:limit]:
        impact_summary = pkg.impact_summary or {}
        entity_codes = [
            str(code).strip()
            for code in (impact_summary.get("entity_codes") or [])
            if str(code).strip()
        ]
        blast_radius = build_metadata_blast_radius(
            entity_codes=entity_codes,
            exclude_consumers={("other", f"package:{pkg.package_id}")},
        )
        # tenant-isolation-allow: package blast-radius aggregates installs across tenants (reviewed 2026-05-14)
        active_installs = list(
            InstalledPackage.objects.filter(
                package_id=pkg.package_id,
                version=pkg.version,
                is_active=True,
            ).values("school_id", "scope", "apply_stage", "reconciliation_status")
        )
        rollback_events = [
            {
                "rollback_token": row.rollback_token,
                "school_id": str(row.school_id) if row.school_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "reconciliation_status": row.reconciliation_status,
            }
            # tenant-isolation-allow: rollback aggregation across tenants for blast-radius (reviewed 2026-05-14)
            for row in PackageChangeLog.objects.filter(
                package_id=pkg.package_id,
                version=pkg.version,
                action="rollback",
            ).order_by("-created_at")[:20]
        ]
        rows.append(
            {
                "package_id": pkg.package_id,
                "version": pkg.version,
                "dependencies": list(pkg.dependencies or []),
                "entity_codes": entity_codes,
                "sections": list((pkg.payload_sections or {}).keys()),
                "active_install_count": len(active_installs),
                "active_installs": [
                    {
                        "school_id": str(item["school_id"])
                        if item["school_id"]
                        else None,
                        "scope": item["scope"],
                        "apply_stage": item["apply_stage"],
                        "reconciliation_status": item["reconciliation_status"],
                    }
                    for item in active_installs
                ],
                "rollback_event_count": len(rollback_events),
                "rollback_events": rollback_events,
                "blast_radius": blast_radius,
            }
        )

    return rows


def export_entity_catalog_bundle(
    *,
    entity_codes: list[str] | None = None,
    include_dependencies: bool = False,
    active_only: bool = True,
) -> dict[str, Any]:
    """
    Export entity/field catalog as a source-control-friendly bundle (package engine foundation).
    If entity_codes is None, export all entities. include_dependencies adds consumer edges.
    When active_only=True (default), only active lifecycle entries are included.
    """
    qs = EntityCatalogEntry.objects.all().order_by("code")
    if active_only:
        qs = qs.filter(lifecycle_state=ENTITY_CATALOG_LIFECYCLE_ACTIVE)
    if entity_codes is not None:
        qs = qs.filter(code__in=entity_codes)
    entities = []
    for ent in qs.prefetch_related("fields"):
        fields = [
            {
                "field_name": f.field_name,
                "label": f.label,
                "data_type": f.data_type,
                "is_custom": f.is_custom,
                "is_required": f.is_required,
                "is_indexed": f.is_indexed,
                "defined_in_app": f.defined_in_app,
                "source": f.source,
            }
            for f in ent.fields.all()
        ]
        payload = {
            "code": ent.code,
            "name": ent.name,
            "description": ent.description,
            "owning_app": ent.owning_app,
            "model_label": ent.model_label,
            "is_core": ent.is_core,
            "lifecycle_state": getattr(ent, "lifecycle_state", "active") or "active",
            "fields": fields,
        }
        if include_dependencies:
            dep_list = []
            for f in ent.fields.all():
                for d in f.dependencies.all():
                    dep_list.append(
                        {
                            "consumer_type": d.consumer_type,
                            "consumer_code": d.consumer_code,
                            "field_name": f.field_name,
                        }
                    )
            payload["dependencies"] = dep_list
        entities.append(payload)
    return {"version": "1", "entities": entities}


def validate_entity_catalog_bundle(bundle: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate an entity catalog bundle (package engine I2). Returns (ok, list of error messages).
    """
    errors: list[str] = []
    if not isinstance(bundle, dict):
        errors.append("Bundle must be a dict")
        return False, errors
    if bundle.get("version") != "1":
        errors.append("Unsupported bundle version")
    entities = bundle.get("entities")
    if not isinstance(entities, list):
        errors.append("Bundle must have 'entities' list")
        return len(errors) == 0, errors
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            errors.append(f"entities[{i}] must be a dict")
            continue
        if not ent.get("code"):
            errors.append(f"entities[{i}] missing 'code'")
        for f in ent.get("fields") or []:
            if not isinstance(f, dict) or not f.get("field_name"):
                errors.append(f"entities[{i}] invalid field entry")
                break
    return len(errors) == 0, errors


def import_entity_catalog_bundle(
    bundle: dict[str, Any],
    *,
    dry_run: bool = False,
    upsert: bool = True,
) -> dict[str, Any]:
    """
    Import entity/field catalog from a bundle (package engine I2). Creates or updates entries.
    Returns summary: created_entities, updated_entities, created_fields, errors.
    """
    ok, errors = validate_entity_catalog_bundle(bundle)
    summary: dict[str, Any] = {
        "created_entities": 0,
        "updated_entities": 0,
        "created_fields": 0,
        "updated_fields": 0,
        "errors": errors,
    }
    if not ok or dry_run:
        return summary
    from django.db import transaction

    with transaction.atomic():
        for ent_payload in bundle.get("entities") or []:
            code = ent_payload.get("code")
            if not code:
                continue
            ent, created = EntityCatalogEntry.objects.update_or_create(
                code=code,
                defaults={
                    "name": ent_payload.get("name", code),
                    "description": ent_payload.get("description", ""),
                    "owning_app": ent_payload.get("owning_app", ""),
                    "model_label": ent_payload.get("model_label", ""),
                    "is_core": ent_payload.get("is_core", False),
                    "lifecycle_state": ent_payload.get("lifecycle_state", "active")
                    or "active",
                },
            )
            if created:
                summary["created_entities"] += 1
            else:
                summary["updated_entities"] += 1
            for f in ent_payload.get("fields") or []:
                field_name = f.get("field_name")
                if not field_name:
                    continue
                _, f_created = FieldCatalogEntry.objects.update_or_create(
                    entity=ent,
                    field_name=field_name,
                    defaults={
                        "label": f.get("label", ""),
                        "data_type": f.get("data_type", "string"),
                        "is_custom": f.get("is_custom", False),
                        "is_required": f.get("is_required", False),
                        "is_indexed": f.get("is_indexed", False),
                        "defined_in_app": f.get("defined_in_app", ""),
                        "source": f.get("source", "import_bundle"),
                    },
                )
                if f_created:
                    summary["created_fields"] += 1
                else:
                    summary["updated_fields"] += 1
    return summary


def metadata_catalog_queryset(get_params: Any):
    """
    Filtered queryset for control-plane metadata catalog (no slice).
    ``get_params`` supports ``q``, ``entity``, ``lifecycle``.
    """
    from django.db.models import Q

    q = (get_params.get("q") or "").strip() if hasattr(get_params, "get") else ""
    entity_code = (get_params.get("entity") or "").strip() if hasattr(get_params, "get") else ""
    lifecycle_all = (
        (get_params.get("lifecycle") or "") == "all" if hasattr(get_params, "get") else False
    )

    qs = EntityCatalogEntry.objects.prefetch_related("fields", "fields__dependencies").order_by(
        "code"
    )
    if not lifecycle_all:
        qs = qs.filter(lifecycle_state=ENTITY_CATALOG_LIFECYCLE_ACTIVE)
    if entity_code:
        qs = qs.filter(code__icontains=entity_code)
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(description__icontains=q)
        )
    return qs


METADATA_CATALOG_FIELD_PREVIEW = 10


def annotate_metadata_catalog_entities(
    entities: list[EntityCatalogEntry],
) -> list[EntityCatalogEntry]:
    for ent in entities:
        fields = list(ent.fields.all())
        ent.field_count = len(fields)
        ent.field_preview = fields[:METADATA_CATALOG_FIELD_PREVIEW]
        ent.fields_overflow = fields[METADATA_CATALOG_FIELD_PREVIEW:]
        ent.fields_overflow_count = len(ent.fields_overflow)
        ent.sample_deps = MetadataDependency.objects.filter(field__entity=ent).count()
    return entities


def get_metadata_catalog_entity_rows(
    get_params: Any,
    *,
    max_entities: int = 200,
) -> tuple[list[EntityCatalogEntry], str]:
    """
    Read-only entity/field rows for control-plane metadata catalog UIs (search + field counts + usage ref counts).
    ``get_params`` is typically ``request.GET`` (supports ``q``, ``entity``, ``lifecycle``).
    """
    q = (get_params.get("q") or "").strip() if hasattr(get_params, "get") else ""
    entity_code = (get_params.get("entity") or "").strip() if hasattr(get_params, "get") else ""

    entities = list(metadata_catalog_queryset(get_params)[:max_entities])
    annotate_metadata_catalog_entities(entities)
    query_display = q or entity_code
    return entities, query_display


def get_metadata_dynamic_field_operator_context() -> dict[str, Any]:
    """
    Read-only aggregates for the metadata dynamic field operator control-plane page.
    """
    from collections import OrderedDict
    from django.db.models import Count

    definitions = list(
        DynamicFieldDefinition.objects.select_related("school").order_by(
            "entity_type", "field_key", "id"
        )
    )
    grouped: "OrderedDict[str, list[DynamicFieldDefinition]]" = OrderedDict()
    for d in definitions:
        grouped.setdefault(d.entity_type, []).append(d)
    value_count_by_type = {
        r["entity_type"]: r["n"]
        for r in DynamicFieldValue.objects.values("entity_type").annotate(n=Count("id"))
    }
    operator_sections = [
        {
            "entity_type": et,
            "definitions": defs,
            "value_row_count": value_count_by_type.get(et, 0),
        }
        for et, defs in grouped.items()
    ]
    return {
        "grouped_definitions": grouped,
        "operator_sections": operator_sections,
        "total_definitions": len(definitions),
        "active_definitions": sum(1 for d in definitions if d.is_active),
        "total_values": DynamicFieldValue.objects.count(),
        "value_count_by_entity_type": value_count_by_type,
    }
