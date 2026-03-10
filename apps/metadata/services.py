from __future__ import annotations

from typing import Any

from apps.metadata.models import (
    DynamicFieldDefinition,
    DynamicFieldValue,
    EntityCatalogEntry,
    FieldCatalogEntry,
    MetadataDependency,
)


def entity_type_for(instance_or_entity_type: Any) -> str:
    if isinstance(instance_or_entity_type, str):
        return instance_or_entity_type
    meta = getattr(instance_or_entity_type, "_meta", None)
    if meta is None:
        raise ValueError("Metadata entity must be a Django model instance or explicit entity type.")
    return f"{meta.app_label}.{meta.model_name}"


def entity_id_for(instance: Any) -> str:
    pk = getattr(instance, "pk", None)
    if pk is None:
        raise ValueError("Metadata entity must have a primary key before metadata can be resolved.")
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


def get_dynamic_field_map(instance: Any, *, school=None, keys: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    resolved_school = school_for_entity(instance, school=school)
    values = legacy_custom_attributes(instance)
    if resolved_school is None or getattr(instance, "pk", None) is None:
        if keys is None:
            return values
        return {key: values[key] for key in keys if key in values}

    queryset = DynamicFieldValue.objects.filter(
        school=resolved_school,
        entity_type=entity_type_for(instance),
        entity_id=entity_id_for(instance),
    )
    if keys:
        queryset = queryset.filter(field_key__in=list(keys))
    for row in queryset:
        values[row.field_key] = unwrap_value(row.value_json)
    if keys is None:
        return values
    return {key: values[key] for key in keys if key in values}


def get_dynamic_field_value(instance: Any, field_key: str, *, default=None, school=None):
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
        deps = MetadataDependency.objects.filter(field_id=field_id).select_related("field", "field__entity")
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


def export_entity_catalog_bundle(
    *,
    entity_codes: list[str] | None = None,
    include_dependencies: bool = False,
) -> dict[str, Any]:
    """
    Export entity/field catalog as a source-control-friendly bundle (package engine foundation).
    If entity_codes is None, export all entities. include_dependencies adds consumer edges.
    """
    qs = EntityCatalogEntry.objects.all().order_by("code")
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

