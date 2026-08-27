"""
Section 11.4: Tenant-facing customer success - support co-pilot, guided onboarding.
"""

import logging
import uuid
import math
from collections.abc import Mapping

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST

from apps.setup_studio.services import execute_launch, get_setup_studio_payload

from .bulk_csv_student_import import apply_bulk_csv, parse_and_validate_csv
from .services import get_guided_onboarding_steps, get_support_copilot_suggestions

logger = logging.getLogger(__name__)

TENANT_CUSTOMER_SUCCESS_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    TypeError,
    ValueError,
)
GUIDED_ONBOARDING_SOFT_FAILURES = TENANT_CUSTOMER_SUCCESS_SOFT_FAILURES + (KeyError,)


def _launch_studio_shell_url() -> str:
    """PATH III.33: same-origin link to Studio OS Launch mode (break out of Setup embed)."""
    try:
        return reverse("studio_os:launch")
    except NoReverseMatch:
        return ""


def _resolve_guided_onboarding_school(request):
    try:
        from apps.lifecycle.tenant_school_resolve import resolve_request_school

        return resolve_request_school(request)
    except ImportError:
        return getattr(request, "school", None)


def _csv_upload_text(request) -> str:
    upload = request.FILES.get("csv_file")
    if upload is not None:
        raw = upload.read()
        if isinstance(raw, bytes):
            return raw.decode("utf-8-sig", errors="replace")
        return str(raw or "")
    return (request.POST.get("csv_text") or "").strip()


def _staff_may_run_csv_import(request) -> bool:
    """Global role gate: is this KIND of user allowed to import a roster at all?

    Deliberately says nothing about WHICH school -- ``User.role`` is one
    CharField on the user, not a per-school grant. ``_resolve_csv_target_school``
    below answers the school question, and both must pass.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    role = str(getattr(user, "role", "") or "").upper()
    return role in {"ADMIN", "SUPERADMIN", "PROPRIETOR"}


def _resolve_csv_target_school(request):
    """Return ``(school, error_payload)`` for a roster-CSV write.

    ``request.school`` is a binding the middleware derived from the HOST, so it
    is authoritative. Everything else is a GUESS: ``resolve_request_school``
    falls back to a session key, then to a SignupVerification matched by email,
    then to ``SchoolMembership...order_by("-is_primary", "-id").first()``. These
    two routes are mounted on the base host as well as the tenant host, so on
    the base host a user who belongs to schools A and B had a roster written
    into whichever membership happened to sort first -- with no school selector
    in the request and no school named in the response.

    Off the tenant host we therefore require the answer to be UNAMBIGUOUS: an
    explicit ``school_id`` the user belongs to, or exactly one membership.
    """
    from apps.schools.models import School, SchoolMembership
    from apps.schools.tenant_access import user_belongs_to_school

    user = getattr(request, "user", None)
    bound = getattr(request, "school", None)
    if bound is not None:
        return bound, None

    explicit = (request.POST.get("school_id") or "").strip()
    if explicit:
        school = School.objects.filter(pk=explicit).first()
        if school is None or not user_belongs_to_school(user, school):
            return None, {"ok": False, "error": "forbidden_school"}
        return school, None

    if getattr(user, "is_superuser", False):
        # A superuser has no membership to disambiguate with, so make them say.
        return None, {"ok": False, "error": "school_id_required"}

    member_ids = list(
        SchoolMembership.objects.filter(user_id=getattr(user, "pk", None))
        .values_list("school_id", flat=True)
        .distinct()[:2]
    )
    if not member_ids:
        return None, {"ok": False, "error": "no_school"}
    if len(member_ids) > 1:
        return None, {"ok": False, "error": "ambiguous_school"}
    school = School.objects.filter(pk=member_ids[0]).first()
    if school is None:
        return None, {"ok": False, "error": "no_school"}
    return school, None


def _guided_onboarding_fallback_context(*, school=None, detail: str) -> dict:
    return {
        "steps": [],
        "school": school,
        "current_step": None,
        "progress_percent": 0,
        "setup_health_score": 0,
        "health_summary": {
            "label": "Needs attention",
            "detail": detail,
            "tone": "risk",
        },
        "recommended_next": None,
        "recommendations": [],
        "role_previews": [],
        "preview_cards": [],
        "preview_workspace": {
            "title": "Live preview workspace",
            "detail": "",
            "website_url": "#",
            "surfaces": [],
        },
        "launch_checklist": [],
        "launch_blockers": [],
        "launch_orchestration": [],
        "launch_ready": False,
        "recommended_blueprint": None,
        "blueprint_rankings": [],
        "recommended_starter_stack": None,
        "data_path_choices": [],
        "ai_recommended": False,
        "launch_studio_url": _launch_studio_shell_url(),
        "launch_data_options_url": "",
        "onboarding_steps": [],
        "csv_dry_run_url": "",
        "csv_apply_url": "",
    }


_LAUNCH_ERROR_MESSAGE_MAX_LEN = 4096


def _clip_launch_error_message(text: str) -> str:
    if len(text) <= _LAUNCH_ERROR_MESSAGE_MAX_LEN:
        return text
    return text[:_LAUNCH_ERROR_MESSAGE_MAX_LEN]


def _normalized_launch_errors(raw_errors) -> list[str]:
    if isinstance(raw_errors, str):
        normalized = raw_errors.strip()
        if not normalized:
            return []
        return [_clip_launch_error_message(normalized)]
    if isinstance(raw_errors, Mapping):
        for key in ("message", "detail", "error"):
            value = raw_errors.get(key)
            if isinstance(value, str):
                normalized = value.strip()
                if normalized:
                    return [_clip_launch_error_message(normalized)]
        return []
    if not raw_errors:
        return []
    errors = []
    for item in raw_errors:
        if isinstance(item, str):
            normalized = item.strip()
            if normalized:
                errors.append(_clip_launch_error_message(normalized))
            continue
        if isinstance(item, Mapping):
            for key in ("message", "detail", "error"):
                value = item.get(key)
                if isinstance(value, str):
                    normalized = value.strip()
                    if normalized:
                        errors.append(_clip_launch_error_message(normalized))
                        break
    return errors


def _normalized_launch_ok(raw_ok) -> bool:
    return raw_ok is True


_SUPPORT_SUGGESTION_TITLE_MAX_LEN = 512
_SUPPORT_SUGGESTION_BODY_MAX_LEN = 8192  # description, link, and similar optional text


def _required_support_string(raw_item: Mapping, key: str) -> str:
    value = raw_item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"support suggestion {key} is malformed")
    if len(value) > _SUPPORT_SUGGESTION_TITLE_MAX_LEN:
        raise ValueError(f"support suggestion {key} is malformed")
    return value


def _optional_support_string(raw_item: Mapping, key: str, *, default: str = "") -> str:
    value = raw_item.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"support suggestion {key} is malformed")
    if len(value) > _SUPPORT_SUGGESTION_BODY_MAX_LEN:
        raise ValueError(f"support suggestion {key} is malformed")
    return value


_SUPPORT_SUGGESTION_PRIORITY_MAX = 32767  # Align with PositiveSmallIntegerField upper bound.


def _optional_support_priority(raw_item: Mapping) -> int | None:
    value = raw_item.get("priority")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("support suggestion priority is malformed")
    if value < 0 or value > _SUPPORT_SUGGESTION_PRIORITY_MAX:
        raise ValueError("support suggestion priority is malformed")
    return value


def _normalized_support_suggestions(raw_suggestions) -> list[dict]:
    if not isinstance(raw_suggestions, (list, tuple)):
        return []
    suggestions = []
    for suggestion in raw_suggestions:
        if not isinstance(suggestion, Mapping):
            raise ValueError("support suggestions payload is malformed")
        suggestions.append(
            {
                "title": _required_support_string(suggestion, "title"),
                "description": _optional_support_string(suggestion, "description"),
                "link": _optional_support_string(suggestion, "link"),
                "priority": _optional_support_priority(suggestion),
            }
        )
    return suggestions


_GUIDED_ONBOARDING_STRING_MAX_LEN = 8192


def _normalized_guided_onboarding_mapping_list(
    raw_items, *, field_name: str
) -> list[Mapping]:
    if not isinstance(raw_items, (list, tuple)):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    items = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            raise ValueError(f"guided onboarding {field_name} entry is malformed")
        items.append(item)
    return items


def _normalized_guided_onboarding_mapping(
    raw_item, *, field_name: str, allow_none: bool = False
) -> Mapping | None:
    if raw_item is None and allow_none:
        return None
    if not isinstance(raw_item, Mapping):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    return raw_item


def _normalized_guided_onboarding_string_list(
    raw_items, *, field_name: str
) -> list[str]:
    if not isinstance(raw_items, (list, tuple)):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    items = []
    for item in raw_items:
        if not isinstance(item, str):
            raise ValueError(f"guided onboarding {field_name} entry is malformed")
        if len(item) > _GUIDED_ONBOARDING_STRING_MAX_LEN:
            raise ValueError(f"guided onboarding {field_name} entry is malformed")
        items.append(item)
    return items


def _normalized_guided_onboarding_percent(raw_value, *, field_name: str) -> int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    if not math.isfinite(raw_value):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    return max(0, min(100, int(raw_value)))


def _normalized_guided_onboarding_non_negative_int(raw_value, *, field_name: str) -> int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    if raw_value < 0:
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    return raw_value


def _normalized_guided_onboarding_flag(raw_value, *, field_name: str) -> bool:
    if not isinstance(raw_value, bool):
        raise ValueError(f"guided onboarding {field_name} payload is malformed")
    return raw_value


def _required_guided_onboarding_string(
    raw_item: Mapping, key: str, *, field_name: str
) -> str:
    value = raw_item.get(key)
    if not isinstance(value, str):
        raise ValueError(f"guided onboarding {field_name} {key} is malformed")
    if len(value) > _GUIDED_ONBOARDING_STRING_MAX_LEN:
        raise ValueError(f"guided onboarding {field_name} {key} is malformed")
    return value


def _optional_guided_onboarding_string(
    raw_item: Mapping, key: str, *, field_name: str, default: str = ""
) -> str:
    value = raw_item.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"guided onboarding {field_name} {key} is malformed")
    if len(value) > _GUIDED_ONBOARDING_STRING_MAX_LEN:
        raise ValueError(f"guided onboarding {field_name} {key} is malformed")
    return value


def _required_guided_onboarding_bool(
    raw_item: Mapping, key: str, *, field_name: str
) -> bool:
    return _normalized_guided_onboarding_flag(
        raw_item.get(key),
        field_name=f"{field_name} {key}",
    )


def _required_guided_onboarding_int(
    raw_item: Mapping, key: str, *, field_name: str
) -> int:
    return _normalized_guided_onboarding_non_negative_int(
        raw_item.get(key),
        field_name=f"{field_name} {key}",
    )


def _optional_guided_onboarding_string_list(
    raw_item: Mapping, key: str, *, field_name: str
) -> list[str]:
    value = raw_item.get(key, [])
    if value is None:
        return []
    return _normalized_guided_onboarding_string_list(
        value,
        field_name=f"{field_name} {key}",
    )


def _normalized_health_summary(raw_summary) -> dict:
    summary = _normalized_guided_onboarding_mapping(
        raw_summary,
        field_name="health summary",
    )
    return {
        "label": _required_guided_onboarding_string(
            summary,
            "label",
            field_name="health summary",
        ),
        "detail": _required_guided_onboarding_string(
            summary,
            "detail",
            field_name="health summary",
        ),
        "tone": _required_guided_onboarding_string(
            summary,
            "tone",
            field_name="health summary",
        ),
    }


def _normalized_guided_onboarding_steps(raw_steps) -> list[dict]:
    steps = []
    for step in _normalized_guided_onboarding_mapping_list(
        raw_steps,
        field_name="steps",
    ):
        steps.append(
            {
                "key": _required_guided_onboarding_string(
                    step,
                    "key",
                    field_name="step",
                ),
                "order": _required_guided_onboarding_int(
                    step,
                    "order",
                    field_name="step",
                ),
                "label": _required_guided_onboarding_string(
                    step,
                    "label",
                    field_name="step",
                ),
                "description": _required_guided_onboarding_string(
                    step,
                    "description",
                    field_name="step",
                ),
                "status": _required_guided_onboarding_string(
                    step,
                    "status",
                    field_name="step",
                ),
                "recommended_choice": _required_guided_onboarding_string(
                    step,
                    "recommended_choice",
                    field_name="step",
                ),
                "done": _required_guided_onboarding_bool(
                    step,
                    "done",
                    field_name="step",
                ),
            }
        )
    return steps


def _normalized_current_step(raw_step) -> dict | None:
    step = _normalized_guided_onboarding_mapping(
        raw_step,
        field_name="current step",
        allow_none=True,
    )
    if step is None:
        return None
    return {
        "key": _required_guided_onboarding_string(
            step,
            "key",
            field_name="current step",
        ),
        "group": _optional_guided_onboarding_string(
            step,
            "group",
            field_name="current step",
            default="launch",
        ),
        "label": _required_guided_onboarding_string(
            step,
            "label",
            field_name="current step",
        ),
        "description": _required_guided_onboarding_string(
            step,
            "description",
            field_name="current step",
        ),
        "recommended_choice": _required_guided_onboarding_string(
            step,
            "recommended_choice",
            field_name="current step",
        ),
        "evidence": _required_guided_onboarding_string(
            step,
            "evidence",
            field_name="current step",
        ),
        "link": _required_guided_onboarding_string(
            step,
            "link",
            field_name="current step",
        ),
        "cta_label": _required_guided_onboarding_string(
            step,
            "cta_label",
            field_name="current step",
        ),
    }


def _normalized_recommended_next(raw_next) -> dict | None:
    next_item = _normalized_guided_onboarding_mapping(
        raw_next,
        field_name="recommended next",
        allow_none=True,
    )
    if next_item is None:
        return None
    return {
        "label": _required_guided_onboarding_string(
            next_item,
            "label",
            field_name="recommended next",
        ),
        "link": _required_guided_onboarding_string(
            next_item,
            "link",
            field_name="recommended next",
        ),
        "description": _optional_guided_onboarding_string(
            next_item,
            "description",
            field_name="recommended next",
        ),
        "evidence": _optional_guided_onboarding_string(
            next_item,
            "evidence",
            field_name="recommended next",
        ),
    }


def _normalized_launch_checklist(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="launch checklist",
    ):
        items.append(
            {
                "label": _required_guided_onboarding_string(
                    item,
                    "label",
                    field_name="launch checklist item",
                ),
                "description": _required_guided_onboarding_string(
                    item,
                    "description",
                    field_name="launch checklist item",
                ),
                "done": _required_guided_onboarding_bool(
                    item,
                    "done",
                    field_name="launch checklist item",
                ),
                "is_blocker": _required_guided_onboarding_bool(
                    item,
                    "is_blocker",
                    field_name="launch checklist item",
                ),
                "status": _required_guided_onboarding_string(
                    item,
                    "status",
                    field_name="launch checklist item",
                ),
                "link": _required_guided_onboarding_string(
                    item,
                    "link",
                    field_name="launch checklist item",
                ),
                "requirement_level": _optional_guided_onboarding_string(
                    item, "requirement_level", field_name="launch checklist item"
                ) or "recommended",
                "requirement_label": _optional_guided_onboarding_string(
                    item, "requirement_label", field_name="launch checklist item"
                ) or "Recommended - finish later",
                "is_skippable": _normalized_guided_onboarding_flag(
                    item.get("is_skippable", False), field_name="launch checklist item skippable"
                ),
            }
        )
    return items


def _normalized_launch_blockers(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="launch blockers",
    ):
        items.append(
            {
                "label": _required_guided_onboarding_string(
                    item,
                    "label",
                    field_name="launch blocker",
                ),
                "detail": _required_guided_onboarding_string(
                    item,
                    "detail",
                    field_name="launch blocker",
                ),
                "link": _required_guided_onboarding_string(
                    item,
                    "link",
                    field_name="launch blocker",
                ),
                "cta_label": _required_guided_onboarding_string(
                    item,
                    "cta_label",
                    field_name="launch blocker",
                ),
            }
        )
    return items


def _normalized_launch_orchestration(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="launch orchestration",
    ):
        items.append(
            {
                "label": _required_guided_onboarding_string(
                    item,
                    "label",
                    field_name="launch orchestration item",
                ),
                "detail": _required_guided_onboarding_string(
                    item,
                    "detail",
                    field_name="launch orchestration item",
                ),
                "done": _required_guided_onboarding_bool(
                    item,
                    "done",
                    field_name="launch orchestration item",
                ),
                "status": _required_guided_onboarding_string(
                    item,
                    "status",
                    field_name="launch orchestration item",
                ),
                "link": _required_guided_onboarding_string(
                    item,
                    "link",
                    field_name="launch orchestration item",
                ),
            }
        )
    return items

def _normalized_preview_workspace(raw_workspace) -> dict:
    workspace = dict(
        _normalized_guided_onboarding_mapping(
            raw_workspace,
            field_name="preview workspace",
        )
    )
    workspace["title"] = _required_guided_onboarding_string(
        workspace,
        "title",
        field_name="preview workspace",
    )
    workspace["detail"] = _required_guided_onboarding_string(
        workspace,
        "detail",
        field_name="preview workspace",
    )
    workspace["website_url"] = _required_guided_onboarding_string(
        workspace,
        "website_url",
        field_name="preview workspace",
    )
    workspace["preview_note"] = _optional_guided_onboarding_string(
        workspace,
        "preview_note",
        field_name="preview workspace",
    )
    workspace["ready_count"] = _required_guided_onboarding_int(
        workspace,
        "ready_count",
        field_name="preview workspace",
    )
    workspace["pending_count"] = _required_guided_onboarding_int(
        workspace,
        "pending_count",
        field_name="preview workspace",
    )
    workspace["surfaces"] = _normalized_preview_workspace_surfaces(
        workspace.get("surfaces", [])
    )
    workspace["recommended_sequence"] = _normalized_preview_workspace_sequence(
        workspace.get("recommended_sequence", [])
    )
    return workspace


def _normalized_preview_cards(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="preview cards",
    ):
        items.append(
            {
                "title": _required_guided_onboarding_string(
                    item,
                    "title",
                    field_name="preview card",
                ),
                "description": _required_guided_onboarding_string(
                    item,
                    "description",
                    field_name="preview card",
                ),
                "status": _required_guided_onboarding_string(
                    item,
                    "status",
                    field_name="preview card",
                ),
                "tone": _required_guided_onboarding_string(
                    item,
                    "tone",
                    field_name="preview card",
                ),
                "url": _required_guided_onboarding_string(
                    item,
                    "url",
                    field_name="preview card",
                ),
            }
        )
    return items


def _normalized_preview_workspace_sequence(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="preview workspace recommended sequence",
    ):
        items.append(
            {
                "label": _required_guided_onboarding_string(
                    item,
                    "label",
                    field_name="preview workspace recommended sequence item",
                ),
                "detail": _required_guided_onboarding_string(
                    item,
                    "detail",
                    field_name="preview workspace recommended sequence item",
                ),
            }
        )
    return items


def _normalized_preview_workspace_surfaces(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="preview workspace surfaces",
    ):
        items.append(
            {
                "title": _required_guided_onboarding_string(
                    item,
                    "title",
                    field_name="preview workspace surface",
                ),
                "status": _required_guided_onboarding_string(
                    item,
                    "status",
                    field_name="preview workspace surface",
                ),
                "url": _required_guided_onboarding_string(
                    item,
                    "url",
                    field_name="preview workspace surface",
                ),
            }
        )
    return items


def _normalized_recommended_blueprint(raw_blueprint) -> dict | None:
    blueprint = _normalized_guided_onboarding_mapping(
        raw_blueprint,
        field_name="recommended blueprint",
        allow_none=True,
    )
    if blueprint is None:
        return None
    return {
        "title": _required_guided_onboarding_string(
            blueprint,
            "title",
            field_name="recommended blueprint",
        ),
        "detail": _required_guided_onboarding_string(
            blueprint,
            "detail",
            field_name="recommended blueprint",
        ),
        "fit_label": _optional_guided_onboarding_string(
            blueprint,
            "fit_label",
            field_name="recommended blueprint",
        ),
        "cta_url": _required_guided_onboarding_string(
            blueprint,
            "cta_url",
            field_name="recommended blueprint",
        ),
        "cta_label": _required_guided_onboarding_string(
            blueprint,
            "cta_label",
            field_name="recommended blueprint",
        ),
    }


def _normalized_recommended_starter_stack(raw_stack) -> dict | None:
    normalized = _normalized_guided_onboarding_mapping(
        raw_stack,
        field_name="recommended starter stack",
        allow_none=True,
    )
    if normalized is None:
        return None
    stack = dict(normalized)
    stack["title"] = _required_guided_onboarding_string(
        stack,
        "title",
        field_name="recommended starter stack",
    )
    stack["detail"] = _required_guided_onboarding_string(
        stack,
        "detail",
        field_name="recommended starter stack",
    )
    stack["items"] = _normalized_guided_onboarding_string_list(
        stack.get("items", []),
        field_name="recommended starter stack items",
    )
    return stack


def _normalized_blueprint_rankings(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="blueprint rankings",
    ):
        items.append(
            {
                "title": _required_guided_onboarding_string(
                    item,
                    "title",
                    field_name="blueprint ranking",
                ),
                "detail": _required_guided_onboarding_string(
                    item,
                    "detail",
                    field_name="blueprint ranking",
                ),
                "fit_label": _required_guided_onboarding_string(
                    item,
                    "fit_label",
                    field_name="blueprint ranking",
                ),
                "reason_summary": _optional_guided_onboarding_string(
                    item,
                    "reason_summary",
                    field_name="blueprint ranking",
                ),
                "fit_score": _required_guided_onboarding_int(
                    item,
                    "fit_score",
                    field_name="blueprint ranking",
                ),
                "cta_url": _required_guided_onboarding_string(
                    item,
                    "cta_url",
                    field_name="blueprint ranking",
                ),
                "cta_label": _required_guided_onboarding_string(
                    item,
                    "cta_label",
                    field_name="blueprint ranking",
                ),
            }
        )
    return items


def _normalized_data_path_choices(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="data path choices",
    ):
        items.append(
            {
                "label": _required_guided_onboarding_string(
                    item,
                    "label",
                    field_name="data path choice",
                ),
                "detail": _required_guided_onboarding_string(
                    item,
                    "detail",
                    field_name="data path choice",
                ),
                "tone": _required_guided_onboarding_string(
                    item,
                    "tone",
                    field_name="data path choice",
                ),
                "status": _required_guided_onboarding_string(
                    item,
                    "status",
                    field_name="data path choice",
                ),
                "cta_url": _required_guided_onboarding_string(
                    item,
                    "cta_url",
                    field_name="data path choice",
                ),
                "cta_label": _required_guided_onboarding_string(
                    item,
                    "cta_label",
                    field_name="data path choice",
                ),
                "recommended": _required_guided_onboarding_bool(
                    item,
                    "recommended",
                    field_name="data path choice",
                ),
            }
        )
    return items


def _normalized_role_previews(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="role previews",
    ):
        items.append(
            {
                "label": _required_guided_onboarding_string(
                    item,
                    "label",
                    field_name="role preview",
                ),
                "description": _required_guided_onboarding_string(
                    item,
                    "description",
                    field_name="role preview",
                ),
                "status_label": _required_guided_onboarding_string(
                    item,
                    "status_label",
                    field_name="role preview",
                ),
                "audit_points": _optional_guided_onboarding_string_list(
                    item,
                    "audit_points",
                    field_name="role preview",
                ),
                "url": _required_guided_onboarding_string(
                    item,
                    "url",
                    field_name="role preview",
                ),
            }
        )
    return items


def _normalized_recommendations(raw_items) -> list[dict]:
    items = []
    for item in _normalized_guided_onboarding_mapping_list(
        raw_items,
        field_name="recommendations",
    ):
        items.append(
            {
                "title": _required_guided_onboarding_string(
                    item,
                    "title",
                    field_name="recommendation",
                ),
                "detail": _required_guided_onboarding_string(
                    item,
                    "detail",
                    field_name="recommendation",
                ),
                "cta_url": _required_guided_onboarding_string(
                    item,
                    "cta_url",
                    field_name="recommendation",
                ),
                "cta_label": _required_guided_onboarding_string(
                    item,
                    "cta_label",
                    field_name="recommendation",
                ),
            }
        )
    return items


@login_required
def support_copilot_view(request):
    """Section 11.4: Support co-pilot - suggested actions from interventions, risk alerts, health.

    School-admin only, for the same reason as tenant_health_dashboard: the
    suggestions carry the risk-alert reasons and the tenant health score, which
    are operator-facing commentary about the school, not portal content for its
    parents and students.
    """
    from apps.lifecycle.tenant_school_resolve import require_tenant_lifecycle_school

    school, denied = require_tenant_lifecycle_school(request)
    if denied is not None:
        return denied
    if not school:
        return render(
            request,
            "customersuccess/support_copilot.html",
            {"suggestions": [], "school": None},
        )
    try:
        suggestions = _normalized_support_suggestions(
            get_support_copilot_suggestions(school)
        )
    except TENANT_CUSTOMER_SUCCESS_SOFT_FAILURES:
        suggestions = []
    return render(
        request,
        "customersuccess/support_copilot.html",
        {
            "suggestions": suggestions,
            "school": school,
        },
    )


@login_required
def guided_onboarding_view(request):
    """Section 11.4: Guided onboarding - Setup Studio. When not embedded, redirect to Studio Launch."""
    embed = request.GET.get("embed") == "1"
    template_name = (
        "customersuccess/guided_onboarding_embed.html"
        if embed
        else "customersuccess/guided_onboarding.html"
    )
    if not embed:
        return redirect(reverse("studio_os:launch"))
    try:
        from apps.lifecycle.tenant_school_resolve import resolve_request_school

        school = resolve_request_school(request)
    except ImportError:
        school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            template_name,
            _guided_onboarding_fallback_context(
                school=None,
                detail="No school context was detected for Setup Studio.",
            ),
        )

    try:
        studio = get_setup_studio_payload(school)
        context = {
            "steps": _normalized_guided_onboarding_steps(studio["steps"]),
            "school": school,
            "current_step": _normalized_current_step(studio["current_step"]),
            "progress_percent": _normalized_guided_onboarding_percent(
                studio["progress_percent"],
                field_name="progress percent",
            ),
            "setup_health_score": _normalized_guided_onboarding_percent(
                studio["health_score"],
                field_name="health score",
            ),
            "health_summary": _normalized_health_summary(studio["health_summary"]),
            "recommended_next": _normalized_recommended_next(
                studio["recommended_next"]
            ),
            "recommendations": _normalized_recommendations(studio["recommendations"]),
            "role_previews": _normalized_role_previews(studio["role_previews"]),
            "preview_cards": _normalized_preview_cards(studio["preview_cards"]),
            "preview_workspace": _normalized_preview_workspace(
                studio["preview_workspace"]
            ),
            "launch_checklist": _normalized_launch_checklist(
                studio["launch_checklist"]
            ),
            "launch_blockers": _normalized_launch_blockers(studio["launch_blockers"]),
            "launch_orchestration": _normalized_launch_orchestration(
                studio["launch_orchestration"]
            ),
            "launch_ready": _normalized_guided_onboarding_flag(
                studio["launch_ready"],
                field_name="launch ready",
            ),
            "launched_at": studio.get("launched_at"),
            "recommended_blueprint": _normalized_recommended_blueprint(
                studio["recommended_blueprint"]
            ),
            "blueprint_rankings": _normalized_blueprint_rankings(
                studio["blueprint_rankings"]
            ),
            "recommended_starter_stack": _normalized_recommended_starter_stack(
                studio["recommended_starter_stack"]
            ),
            "data_path_choices": _normalized_data_path_choices(
                studio["data_path_choices"]
            ),
            "ai_recommended": _normalized_guided_onboarding_flag(
                studio.get("ai_recommended", False),
                field_name="ai recommended",
            ),
        }
    except GUIDED_ONBOARDING_SOFT_FAILURES:
        return render(
            request,
            template_name,
            _guided_onboarding_fallback_context(
                school=school,
                detail="Setup Studio data is temporarily unavailable.",
            ),
        )
    context["launch_studio_url"] = _launch_studio_shell_url()
    try:
        context["launch_data_options_url"] = reverse(
            "setup_studio:onboarding_data_options"
        )
    except NoReverseMatch:
        context["launch_data_options_url"] = ""
    try:
        context["onboarding_steps"] = get_guided_onboarding_steps(school)
    except GUIDED_ONBOARDING_SOFT_FAILURES:
        context["onboarding_steps"] = []
    try:
        context["csv_dry_run_url"] = reverse("siteconfig:guided_onboarding_csv_dry_run")
        context["csv_apply_url"] = reverse("siteconfig:guided_onboarding_csv_apply")
    except NoReverseMatch:
        context["csv_dry_run_url"] = ""
        context["csv_apply_url"] = ""
    return render(
        request,
        template_name,
        context,
    )


@login_required
@require_POST
def guided_onboarding_csv_dry_run(request):
    """Validate roster CSV without writing — tenant-scoped, staff-only."""
    if not _staff_may_run_csv_import(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    school, error = _resolve_csv_target_school(request)
    if error is not None:
        return JsonResponse(error, status=403 if "forbidden" in error["error"] else 400)
    text = _csv_upload_text(request)
    if not text.strip():
        return JsonResponse({"ok": False, "error": "empty_csv"}, status=400)
    validated = parse_and_validate_csv(text)
    payload = validated.as_dict()
    payload["ok"] = True
    # Name the tenant in the response so a mis-resolution is visible to the
    # caller instead of only to the rows it lands on.
    payload["school_id"] = str(school.pk)
    payload["school_slug"] = getattr(school, "slug", "")
    return JsonResponse(payload)


@login_required
@require_POST
def guided_onboarding_csv_apply(request):
    """Apply a validated roster CSV — tenant-scoped, staff-only."""
    if not _staff_may_run_csv_import(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    school, error = _resolve_csv_target_school(request)
    if error is not None:
        return JsonResponse(error, status=403 if "forbidden" in error["error"] else 400)
    text = _csv_upload_text(request)
    if not text.strip():
        return JsonResponse({"ok": False, "error": "empty_csv"}, status=400)
    validated = parse_and_validate_csv(text)
    if not validated.is_valid:
        return JsonResponse(
            {"ok": False, "validation": validated.as_dict()},
            status=400,
        )
    apply_result = apply_bulk_csv(school_id=school.pk, validated=validated)
    payload = apply_result.as_dict()
    payload["ok"] = not apply_result.errors
    payload["school_id"] = str(school.pk)
    payload["school_slug"] = getattr(school, "slug", "")
    return JsonResponse(payload, status=200 if payload["ok"] else 400)


@login_required
@require_POST
def execute_launch_view(request):
    """Operator-triggered go-live: call execute_launch and redirect back to Setup Studio with message."""
    school = getattr(request, "school", None)
    if not school:
        messages.error(
            request, "No school context. Go-live is only available in tenant context."
        )
        return redirect("siteconfig:guided_onboarding")
    try:
        result = execute_launch(school.pk, actor_id=request.user.pk)
        ok = _normalized_launch_ok(result.get("ok"))
        errors = _normalized_launch_errors(result.get("errors"))
    except TENANT_CUSTOMER_SUCCESS_SOFT_FAILURES:
        logger.warning(
            "customersuccess.execute_launch soft failure school_id=%s",
            getattr(school, "pk", ""),
            exc_info=True,
        )
        messages.error(
            request,
            "Launch could not be executed right now. Please try again.",
        )
        return redirect("siteconfig:guided_onboarding")
    except AssertionError:
        # MUST come before the catch-all: DatabaseOperationForbidden subclasses
        # AssertionError precisely so a fail-soft guard cannot swallow a forbidden write,
        # and `except Exception` would happily swallow it.
        raise
    except Exception:  # noqa: BLE001
        # Anything the tuple above does not name - a KeyError, a ValidationError, an
        # ImportError from an optional integration - used to be a bare 500 on the ONE
        # button an activating school cannot route around. Logged in full so it is never
        # silent, surfaced with a reference so it is reportable, and returned to a page the
        # operator can act on.
        ref = uuid.uuid4().hex[:8]
        logger.error(
            "customersuccess.execute_launch unexpected failure ref=%s school_id=%s",
            ref,
            getattr(school, "pk", ""),
            exc_info=True,
        )
        messages.error(
            request,
            "Launch hit an unexpected error and was not completed. Nothing was "
            f"half-applied that we could detect. Reference {ref} - please share it if you "
            "report this.",
        )
        return redirect("siteconfig:guided_onboarding")
    if ok and not errors:
        request.session["rmc_launch_ceremony_show"] = True
        messages.success(
            request,
            "You're live — your school is approved and launch is recorded.",
        )
    else:
        if not errors:
            messages.error(
                request,
                "Launch could not be executed right now. Please try again.",
            )
        else:
            for err in errors:
                messages.error(request, err)
    if ok and not errors:
        try:
            return redirect(reverse("accounts:backend_dashboard") + "?launched=1")
        except NoReverseMatch:
            pass
    return redirect("siteconfig:guided_onboarding")


@login_required
def tenant_billing_estimate_view(request):
    """CEZGP Lane 2 — tenant billing estimate + marketing pricing crosswalk (P10 / B6)."""
    school = _resolve_guided_onboarding_school(request)
    if school is None:
        messages.error(request, "No school context for billing estimate.")
        return redirect("siteconfig:guided_onboarding")
    from .pricing_billing_clarity import tenant_billing_estimate_context

    ctx = tenant_billing_estimate_context(school=school)
    return render(
        request,
        "customersuccess/tenant_billing_estimate.html",
        {
            "school": school,
            **ctx,
        },
    )
