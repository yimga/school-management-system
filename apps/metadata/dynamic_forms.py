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


def _validation_rules(defn: DynamicFieldDefinition) -> dict[str, Any]:
    rules = getattr(defn, "validation_json", None)
    return rules if isinstance(rules, dict) else {}


def form_field_for_definition(defn: DynamicFieldDefinition) -> forms.Field:
    label = defn.label or defn.field_key.replace("_", " ").title()
    required = bool(defn.required)
    widget_attrs = {"class": "form-control", "data-rmc-dynamic-field": defn.field_key}
    rules = _validation_rules(defn)
    pattern = rules.get("pattern")
    text_validators = []
    if pattern:
        from django.core.validators import RegexValidator

        text_validators.append(
            RegexValidator(
                regex=pattern,
                message=_("Enter a valid %(label)s.") % {"label": label},
            )
        )
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
        validators=text_validators,
    )


def attach_dynamic_fields(
    form: forms.Form,
    *,
    school: Any | None,
    entity_type: str,
    instance: Any | None = None,
) -> None:
    """Add tenant EAV fields to an existing ModelForm.

    Records the added field names on ``form.dynamic_field_names`` so the template
    can render exactly the dynamic inputs (the static fields are hand-rendered by
    the parent template). Without a template that emits these ``dyn_*`` inputs the
    values are never submitted and ``save_dynamic_fields_from_form`` silently
    persists nothing — see ``templates/metadata/_dynamic_fields_section.html``.
    """
    from apps.metadata.services import get_dynamic_field_value

    dynamic_field_names: list[str] = list(getattr(form, "dynamic_field_names", []) or [])
    for defn in definitions_for_entity(school=school, entity_type=entity_type):
        field_name = f"{_DYNAMIC_FIELD_PREFIX}{defn.field_key}"
        form.fields[field_name] = form_field_for_definition(defn)
        if field_name not in dynamic_field_names:
            dynamic_field_names.append(field_name)
        if instance is not None and instance.pk:
            initial = get_dynamic_field_value(
                instance, defn.field_key, school=school or getattr(instance, "school", None)
            )
            if initial is not None:
                form.fields[field_name].initial = initial
    form.dynamic_field_names = dynamic_field_names


def save_dynamic_fields_from_form(
    form: forms.Form,
    *,
    instance: Any,
    school: Any | None,
    entity_type: str,
) -> None:
    """Persist submitted dynamic fields via set_dynamic_field_value."""
    from apps.metadata.services import mask_pii_value

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
        # store_masked (e.g. Aadhaar): the raw value is validated at form clean
        # (RegexValidator) but MUST NOT be persisted in plaintext — store only a
        # masked form, so detail pages + the student search index never expose
        # the raw PII. mask_pii_value is idempotent, so an unchanged re-submit is
        # safe.
        if (
            _validation_rules(defn).get("store_masked")
            and isinstance(value, str)
            and value.strip()
        ):
            value = mask_pii_value(value)
        set_dynamic_field_value(
            instance,
            defn.field_key,
            value,
            school=school or getattr(instance, "school", None),
            data_type=defn.data_type,
        )


def dynamic_field_display_rows(
    instance: Any,
    *,
    school: Any | None,
    entity_type: str,
) -> list[dict[str, str]]:
    """Label/value rows for a DETAIL page's "Custom fields" section.

    Honors store_masked implicitly: the stored value is already masked (masking
    happens at save time), so no raw PII is surfaced here. Mirrors the shape of
    ``apps.reports.services.student_dynamic_fields_for_report``.
    """
    from apps.metadata.services import get_dynamic_field_value

    resolved_school = school or getattr(instance, "school", None)
    rows: list[dict[str, str]] = []
    for defn in definitions_for_entity(school=resolved_school, entity_type=entity_type):
        value = get_dynamic_field_value(
            instance, defn.field_key, school=resolved_school
        )
        if value is None or not str(value).strip():
            continue
        rows.append(
            {
                "label": (defn.label or defn.field_key).strip(),
                "value": str(value).strip(),
            }
        )
    return rows


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
