"""
Public marketing API (sandbox validation, no tenant data).
"""
from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.schools.marketing_media_matrix import (
    SANDBOX_MODULE_TO_SETUP_STEP,
    VALID_SANDBOX_MODULES,
)


def _validate_sandbox_payload(data: dict[str, Any]) -> tuple[bool, str, list[str]]:
    region = (data.get("region") or "").strip().upper()
    if len(region) != 2:
        return False, "Region must be a 2-letter country code", []
    size = (data.get("school_size") or "").strip().lower()
    if size not in {"small", "medium", "large"}:
        return False, "Invalid school size", []
    modules = data.get("modules") or []
    if not isinstance(modules, list) or not modules:
        return False, "Select at least one module", []
    steps: list[str] = []
    for mod in modules:
        key = str(mod).strip().lower()
        if key not in VALID_SANDBOX_MODULES:
            return False, f"Unknown module: {key}", []
        step = SANDBOX_MODULE_TO_SETUP_STEP.get(key)
        if step and step not in steps:
            steps.append(step)
    try:
        from apps.setup_studio.services import STEP_DEFINITIONS

        known = {d["key"] for d in STEP_DEFINITIONS}
        missing = [s for s in steps if s not in known]
        if missing:
            return False, "Setup steps unavailable for selection", steps
    except Exception:  # noqa: BLE001
        pass
    return True, "Configuration valid (illustrative — maps to Setup Studio steps)", steps


@csrf_protect
@require_POST
def marketing_sandbox_validate(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"valid": False, "error": "invalid_json"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"valid": False, "error": "invalid_payload"}, status=400)
    ok, message, steps = _validate_sandbox_payload(body)
    if not ok:
        return JsonResponse({"valid": False, "message": message}, status=400)
    return JsonResponse(
        {
            "valid": True,
            "message": message,
            "setup_steps": steps,
            "region": body.get("region"),
        }
    )
