"""Render DynamicFieldDefinition rows as real Django form fields."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.metadata.models import DynamicFieldDefinition
from apps.metadata.services import set_dynamic_field_value

_DYNAMIC_FIELD_PREFIX = "dyn_"


def _entity_type_for_model(model) -> str:
    return f"{model._meta.app_label}.{model._meta.model_name}"


def definitions_for_entity(
    *,
    school: Any | None,
    entity_type: str,
) -> list[DynamicFieldDefinition]:
    from django.db.models import Q

    if school is not None:
        qs = DynamicFieldDefinition.objects.filter(
            Q(entity_type=entity_type, is_active=True, school=school)
            | Q(entity_type=entity_type, is_active=True, school__isnull=True)
        )
    else:
        qs = DynamicFieldDefinition.objects.filter(
            entity_type=entity_type,
            is_active=True,
            school__isnull=True,
        )
    return list(qs.order_by("field_key"))


def form_field_for_definition(defn: DynamicFieldDefinition) -> forms.Field:
    label = defn.label or defn.field_key.replace("_", " ").title()
    required = bool(defn.required)
    widget_attrs = {"class": "form-control", "data-rmc-dynamic-field": defn.field_key}
    if defn.data_type == "boolean":
        return forms.BooleanField(
            label=label,
            required=required,
            widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        )
    if defn.data_type == "number":
        return forms.DecimalField(
            label=label,
            required=required,
            max_digits=18,
            decimal_places=4,
            widget=forms.NumberInput(attrs=widget_attrs),
        )
    if defn.data_type == "date":
        return forms.DateField(
            label=label,
            required=required,
            widget=forms.DateInput(attrs={**widget_attrs, "type": "date"}),
        )
    if defn.data_type == "json":
        return forms.CharField(
            label=label,
            required=required,
            widget=forms.Textarea(attrs={**widget_attrs, "rows": 3}),
            help_text=_("JSON object"),
        )
    return forms.CharField(
        label=label,
        required=required,
        widget=forms.TextInput(attrs=widget_attrs),
    )


def attach_dynamic_fields(
    form: forms.Form,
    *,
    school: Any | None,
    entity_type: str,
    instance: Any | None = None,
) -> None:
    """Add tenant EAV fields to an existing ModelForm."""
    from apps.metadata.services import get_dynamic_field_value

    for defn in definitions_for_entity(school=school, entity_type=entity_type):
        field_name = f"{_DYNAMIC_FIELD_PREFIX}{defn.field_key}"
        form.fields[field_name] = form_field_for_definition(defn)
        if instance is not None and instance.pk:
            initial = get_dynamic_field_value(
                instance, defn.field_key, school=school or getattr(instance, "school", None)
            )
            if initial is not None:
                form.fields[field_name].initial = initial


def save_dynamic_fields_from_form(
    form: forms.Form,
    *,
    instance: Any,
    school: Any | None,
    entity_type: str,
) -> None:
    """Persist submitted dynamic fields via set_dynamic_field_value."""
    for defn in definitions_for_entity(school=school, entity_type=entity_type):
        field_name = f"{_DYNAMIC_FIELD_PREFIX}{defn.field_key}"
        if field_name not in form.cleaned_data:
            continue
        raw = form.cleaned_data.get(field_name)
        if defn.data_type == "boolean":
            value = bool(raw)
        elif defn.data_type == "number":
            if raw in (None, ""):
                value = None
            else:
                try:
                    value = float(Decimal(str(raw)))
                except (InvalidOperation, ValueError, TypeError):
                    continue
        else:
            value = raw
        if value in (None, "") and not defn.required:
            continue
        set_dynamic_field_value(
            instance,
            defn.field_key,
            value,
            school=school or getattr(instance, "school", None),
            data_type=defn.data_type,
        )


def attach_dynamic_fields_for_model(
    form: forms.Form,
    *,
    school: Any | None,
    model,
    instance: Any | None = None,
) -> None:
    attach_dynamic_fields(
        form,
        school=school,
        entity_type=_entity_type_for_model(model),
        instance=instance,
    )


def save_dynamic_fields_for_model(
    form: forms.Form,
    *,
    instance: Any,
    school: Any | None,
    model,
) -> None:
    save_dynamic_fields_from_form(
        form,
        instance=instance,
        school=school,
        entity_type=_entity_type_for_model(model),
    )
    _refresh_search_index_if_student(instance, model)


def _refresh_search_index_if_student(instance: Any, model) -> None:
    if model._meta.label_lower != "people.studentprofile":
        return
    if getattr(instance, "pk", None) is None:
        return
    from apps.people.student_search_index import build_student_search_index

    instance.search_index = build_student_search_index(instance)
    instance.save(update_fields=["search_index"])
