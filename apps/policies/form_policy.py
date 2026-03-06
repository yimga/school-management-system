"""
Section 23.4 & 24.8: Policy-driven form field visibility, required/optional, picker options,
document requirements, validation rules, default values.
All form behavior is driven by policy["forms"][form_name] so config is metadata-driven (24.8).
"""
from typing import Any, Dict, List, Optional


def get_form_schema(policy: Dict[str, Any], form_name: str) -> Dict[str, Any]:
    """
    Return the form schema for form_name from merged policy.
    policy["forms"][form_name] should be { "fields": [ { "name", "visible", "required", "label", "choices_key", "validation", "document_required" }, ... ] }
    """
    if not policy or not isinstance(policy, dict):
        return {}
    forms = policy.get("forms") or {}
    if not isinstance(forms, dict):
        return {}
    schema = forms.get(form_name)
    if not isinstance(schema, dict):
        return {}
    return schema


def get_field_configs(form_name: str, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return list of field configs for form_name. Each item: name, visible (default True),
    required (optional), label (optional), choices_key (optional), validation (optional), document_required (optional).
    """
    schema = get_form_schema(policy, form_name)
    fields = schema.get("fields")
    if not isinstance(fields, list):
        return []
    return fields


def _resolve_choices_for_key(choices_key: str, school=None) -> list:
    """
    Resolve picker options from a policy choices_key (catalog-backed).
    Used so forms get options from metadata/registry, not hardcoded in form class.
    """
    if not choices_key:
        return []
    # Built-in keys → model/enum choices
    if choices_key == "gender":
        try:
            from apps.people.models import StudentProfile
            return list(StudentProfile.Gender.choices)
        except Exception:
            return []
    if choices_key == "relationship":
        try:
            from apps.people.models import StudentGuardian
            return list(StudentGuardian.Relationship.choices)
        except Exception:
            return []
    if choices_key == "preferred_contact":
        try:
            from apps.people.models import StudentGuardian
            return list(StudentGuardian.PreferredContact.choices)
        except Exception:
            return []
    if choices_key == "student_status":
        try:
            from apps.people.models import StudentProfile
            return list(StudentProfile.Status.choices)
        except Exception:
            return []
    if choices_key == "payment_method":
        try:
            from apps.finance.models import PaymentMethod
            qs = PaymentMethod.objects.filter(is_active=True)
            return [(str(m.id), m.name) for m in qs[:50]]
        except Exception:
            return []
    # Future: choices_key "region", "education_level" from registries
    return []


def apply_form_policy(
    form,
    form_name: str,
    policy: Dict[str, Any],
    school=None,
) -> None:
    """
    Apply policy-driven form schema to a Django form (in-place).
    - For each field in schema: set required, label; if visible is False, remove from form.fields.
    - If choices_key is set, resolve choices from catalog and set field.choices.
    - Does not add new fields; only adjusts existing form.fields.
    """
    field_configs = get_field_configs(form_name, policy)
    if not field_configs:
        return
    name_to_config = {fc.get("name"): fc for fc in field_configs if fc.get("name")}
    for name in list(form.fields.keys()):
        if name not in name_to_config:
            continue
        config = name_to_config[name]
        field = form.fields.get(name)
        if field is None:
            continue
        if config.get("visible") is False:
            del form.fields[name]
            continue
        if "required" in config:
            field.required = bool(config["required"])
        if config.get("label"):
            field.label = config["label"]
        if config.get("help_text") is not None:
            field.help_text = config["help_text"]
        choices_key = config.get("choices_key")
        if choices_key:
            choices = _resolve_choices_for_key(choices_key, school=school)
            if choices:
                field.choices = choices
        if config.get("document_required") and hasattr(field, "required"):
            # Hint for templates: this field is document-required (e.g. show upload)
            field.document_required = True  # type: ignore[attr-defined]


def default_forms_platform() -> Dict[str, Any]:
    """
    Platform-default form schemas (no tenant overrides). Used when building policy
    so that forms always have a consistent structure; tenants override via school.settings["forms"].
    """
    return {
        "link_child": {
            "fields": [
                {"name": "admission_number", "visible": True, "required": True, "label": "Admission number"},
                {"name": "relationship", "visible": True, "required": True, "choices_key": "relationship"},
                {"name": "phone", "visible": True, "required": False},
                {"name": "preferred_contact", "visible": True, "required": False, "choices_key": "preferred_contact"},
                {"name": "referral_code", "visible": True, "required": False},
                {"name": "student_date_of_birth", "visible": True, "required": False},
                {"name": "student_place_of_birth", "visible": True, "required": False},
                {"name": "student_gender", "visible": True, "required": False, "choices_key": "gender"},
                {"name": "student_status", "visible": True, "required": False, "choices_key": "student_status"},
                {"name": "student_joined_term", "visible": True, "required": False},
                {"name": "student_joined_date", "visible": True, "required": False},
                {"name": "parent_first_name", "visible": True, "required": False},
                {"name": "parent_last_name", "visible": True, "required": False},
                {"name": "parent_email", "visible": True, "required": False},
                {"name": "parent_whatsapp", "visible": True, "required": False},
                {"name": "parent_address", "visible": True, "required": False},
                {"name": "can_view_results", "visible": True, "required": False},
                {"name": "can_view_finance", "visible": True, "required": False},
            ],
        },
        "student_onboarding": {
            "fields": [
                {"name": "first_name", "visible": True, "required": True},
                {"name": "last_name", "visible": True, "required": True},
                {"name": "date_of_birth", "visible": True, "required": False},
                {"name": "gender", "visible": True, "required": False, "choices_key": "gender"},
                {"name": "place_of_birth", "visible": True, "required": False},
                {"name": "academic_year", "visible": True, "required": False},
                {"name": "specialty", "visible": True, "required": False},
                {"name": "classroom", "visible": True, "required": False},
                {"name": "admission_number", "visible": True, "required": False},
                {"name": "parent_first_name", "visible": True, "required": False},
                {"name": "parent_last_name", "visible": True, "required": False},
                {"name": "parent_email", "visible": True, "required": False},
                {"name": "parent_phone", "visible": True, "required": False},
                {"name": "parent_whatsapp", "visible": True, "required": False},
                {"name": "payment_method", "visible": True, "required": False, "choices_key": "payment_method"},
                {"name": "referral_code", "visible": True, "required": False},
                {"name": "profile_photo", "visible": True, "required": False},
            ],
        },
    }
