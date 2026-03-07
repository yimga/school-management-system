from __future__ import annotations

from typing import Any

from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue


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

