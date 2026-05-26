"""Wizard views — Operator + Tenant + AI Recommend + Reset + Index.

URL routes are mounted under both ``siteconfig`` (operator) and ``studio_os``
(tenant) namespaces via ``apps/setup_studio/urls.py``.

Permission markers (audited by ``audit_role_permission_matrix.py``):
* ``# rbac-allow: super-staff-wizard-index``
* ``# rbac-allow: super-staff-wizard-engine-access``
* ``# rbac-allow: super-staff-wizard-reset-state``
* ``# rbac-allow: tenant-admin-wizard-index-via-role-registry``
* ``# rbac-allow: tenant-admin-wizard-engine-access-via-role-registry``
* ``# rbac-allow: tenant-admin-wizard-reset-state``
* ``# rbac-allow: authenticated-user-wizard-ai-recommend``
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from apps.setup_studio import (
    wizard_ai,
    wizard_engine,
    wizard_state_resolver,
    wizard_telemetry,
)

logger = logging.getLogger(__name__)

__all__ = [
    "OperatorWizardIndexView",
    "OperatorWizardView",
    "TenantWizardIndexView",
    "TenantWizardView",
    "WizardAIRecommendView",
    "WizardStateResetView",
]


def _resolve_school(request: HttpRequest) -> Any:
    """Best-effort school resolution. Tries request.school, request.tenant, request.user.school."""
    for attr in ("school", "tenant"):
        candidate = getattr(request, attr, None)
        if candidate is not None and getattr(candidate, "pk", None) is not None:
            return candidate
    user = getattr(request, "user", None)
    if user is not None:
        for attr in ("school", "tenant", "current_school"):
            candidate = getattr(user, attr, None)
            if candidate is not None and getattr(candidate, "pk", None) is not None:
                return candidate
    return None


def _build_context(
    *,
    request: HttpRequest,
    wizard: wizard_engine.WizardDefinition,
    step: wizard_engine.StepDefinition,
    audience: str,
    school: Any,
    state: dict[str, Any],
    errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed_keys = state.get("completed") or []
    prior_answer = (state.get("answers") or {}).get(step.key) or {}
    resolved_options = wizard_engine.resolve_options(step, request=request, school=school)

    ai_rationale = None
    ai_suggested_value = None
    if step.ai_recommend and step.ai_recommend.get("enabled"):
        prompt_key = step.ai_recommend.get("prompt_template_key")
        if prompt_key:
            ctx_keys = step.ai_recommend.get("context_keys") or []
            context = {k: _safe_context_value(request, school, k) for k in ctx_keys}
            result = wizard_ai.request_smart_defaults(
                request=request, school=school,
                wizard_key=wizard.wizard_key, step_key=step.key,
                prompt_key=prompt_key, context=context, options=resolved_options,
            )
            ai_rationale = result.rationale_text
            if step.input_type in ("single_choice", "rich_select"):
                for opt_key in ("recommended_apm_key", "palette_key", "vocabulary_pack_key", "value"):
                    if opt_key in result.suggestions:
                        ai_suggested_value = result.suggestions[opt_key]
                        break

    is_final_step = (wizard.steps[-1].key == step.key) if wizard.steps else True
    form_action_url = _make_url(audience, "wizard_step", wizard.wizard_key, step.key)

    completed_indices = []
    for s in wizard.steps:
        if s.key in completed_keys:
            completed_indices.append(s.key)

    back_url = None
    if state.get("completed"):
        # Back to the last completed step
        completed_list = state["completed"]
        if step.key in completed_list:
            idx = completed_list.index(step.key)
            if idx > 0:
                back_url = _make_url(audience, "wizard_step", wizard.wizard_key, completed_list[idx - 1])
        elif completed_list:
            back_url = _make_url(audience, "wizard_step", wizard.wizard_key, completed_list[-1])

    return {
        "wizard": wizard,
        "step": step,
        "audience": audience,
        "school_id": getattr(school, "pk", None),
        "wizard_label": wizard.label_token,
        "wizard_description": wizard.description_token,
        "step_label": step.label_token,
        "step_description": step.description_token,
        "completed_keys": completed_keys,
        "prior_answer": prior_answer,
        "resolved_options": resolved_options,
        "ai_rationale": ai_rationale,
        "ai_suggested_value": ai_suggested_value,
        "errors": errors or {},
        "form_action_url": form_action_url,
        "back_url": back_url,
        "is_final_step": is_final_step,
        "estimated_seconds": step.estimated_seconds,
        "help_links": [],
    }


def _safe_context_value(request: HttpRequest, school: Any, key: str) -> Any:
    """Resolve a single context key from request/school for AI smart-defaults context."""
    if school is None:
        return None
    if key == "country_code":
        return getattr(school, "country_code", None) or getattr(school, "country", None)
    if key == "state_code":
        return getattr(school, "state_code", None)
    if key == "primary_language":
        return getattr(school, "primary_language", None)
    if key == "school_type":
        return getattr(school, "school_type", None) or getattr(school, "primary_sector", None)
    if key == "accept_language_header":
        return request.META.get("HTTP_ACCEPT_LANGUAGE", "").split(",")[0] if request else None
    if key == "school_size_band":
        return getattr(school, "size_band", None)
    return None


def _make_url(audience: str, route: str, wizard_key: str | None = None, step_key: str | None = None) -> str:
    """Reverse a wizard URL under the appropriate namespace."""
    ns = "setup_studio"
    name_prefix = "operator" if audience == "operator" else "tenant"
    name = f"{ns}:{name_prefix}_{route}"
    kwargs: dict[str, Any] = {}
    if wizard_key:
        kwargs["wizard_key"] = wizard_key
    if step_key:
        kwargs["step_key"] = step_key
    try:
        return reverse(name, kwargs=kwargs)
    except Exception:  # noqa: BLE001
        return "#"


def _parse_post_payload(request: HttpRequest, step: wizard_engine.StepDefinition) -> dict[str, Any]:
    """Convert request.POST + request.FILES → wizard payload dict."""
    if step.input_type == "structured_form":
        payload: dict[str, Any] = {}
        for fld in step.fields:
            name = fld.get("name")
            if not isinstance(name, str):
                continue
            if fld.get("type") == "file":
                payload[name] = request.FILES.get(name)
            elif fld.get("type") == "boolean":
                payload[name] = request.POST.get(name) in ("1", "on", "true")
            else:
                payload[name] = request.POST.get(name)
        return payload
    if step.input_type == "multi_choice":
        return {"value": request.POST.getlist("value")}
    if step.input_type == "key_value_pairs":
        keys = request.POST.getlist("kv_key")
        values = request.POST.getlist("kv_value")
        pairs = [{"key": k, "value": v} for k, v in zip(keys, values) if k or v]
        return {"pairs": pairs}
    if step.input_type == "ranked_list":
        return {"value": request.POST.getlist("value")}
    if step.input_type == "duration":
        return {
            "days": int(request.POST.get("days") or 0),
            "hours": int(request.POST.get("hours") or 0),
            "minutes": int(request.POST.get("minutes") or 0),
        }
    if step.input_type == "file_upload" or step.input_type == "image_upload":
        return {"value": request.FILES.get("value")}
    return {"value": request.POST.get("value")}


# ---------- Views ----------


@method_decorator(staff_member_required, name="dispatch")
class OperatorWizardIndexView(LoginRequiredMixin, View):
    """Lists operator-audience wizards. # rbac-allow: super-staff-wizard-index"""

    def get(self, request: HttpRequest) -> HttpResponse:
        wizards = wizard_engine.list_wizards_for_audience("operator")
        return render(request, "setup_studio/operator_wizard_index.html", {"wizards": wizards})


@method_decorator(staff_member_required, name="dispatch")
class OperatorWizardView(LoginRequiredMixin, View):
    """# rbac-allow: super-staff-wizard-engine-access"""

    audience = "operator"
    template = "setup_studio/operator_wizard.html"

    def _resolve(self, request: HttpRequest, wizard_key: str, step_key: str | None):
        try:
            wizard = wizard_engine.get_wizard(wizard_key)
        except wizard_engine.WizardNotFound:
            return None, None, None
        school = _resolve_school(request)
        if school is None:
            return wizard, None, None
        state = wizard_state_resolver.start_wizard(school, wizard_key)
        if step_key is None:
            step_key = state.get("current_step_key") or wizard.first_step().key
        try:
            step = wizard.step_by_key(step_key)
        except wizard_engine.StepNotFound:
            step = wizard.first_step()
        return wizard, step, school

    def get(self, request: HttpRequest, wizard_key: str, step_key: str | None = None) -> HttpResponse:
        wizard, step, school = self._resolve(request, wizard_key, step_key)
        if wizard is None:
            return redirect("setup_studio:operator_wizard_index")
        if school is None:
            logger.warning("OperatorWizardView: no school resolved for request")
            return redirect("setup_studio:operator_wizard_index")
        state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
        if state.get("completed_at"):
            return render(request, "setup_studio/operator_wizard_index.html", {
                "wizards": wizard_engine.list_wizards_for_audience("operator"),
                "just_completed_wizard_key": wizard.wizard_key,
            })
        wizard_telemetry.emit_step_viewed(wizard.wizard_key, step.key, self.audience)
        context = _build_context(
            request=request, wizard=wizard, step=step,
            audience=self.audience, school=school, state=state,
        )
        return render(request, self.template, context)

    def post(self, request: HttpRequest, wizard_key: str, step_key: str) -> HttpResponse:
        wizard, step, school = self._resolve(request, wizard_key, step_key)
        if wizard is None or school is None:
            return redirect("setup_studio:operator_wizard_index")
        payload = _parse_post_payload(request, step)
        try:
            wizard_state_resolver.apply_step_answer(
                school, wizard.wizard_key, step.key, payload,
                actor_user_id=getattr(request.user, "pk", None),
            )
        except wizard_engine.WizardError as exc:
            logger.info("OperatorWizardView: validation failed: %s", exc)
            state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
            _, errors = wizard_engine.validate_step_answer(step, payload)
            context = _build_context(
                request=request, wizard=wizard, step=step,
                audience=self.audience, school=school, state=state, errors=errors,
            )
            return render(request, self.template, context)
        new_state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
        next_step_key = new_state.get("current_step_key")
        if next_step_key is None:
            return redirect("setup_studio:operator_wizard_index")
        return redirect("setup_studio:operator_wizard_step", wizard_key=wizard.wizard_key, step_key=next_step_key)


class TenantWizardIndexView(LoginRequiredMixin, View):
    """# rbac-allow: tenant-admin-wizard-index-via-role-registry"""

    def get(self, request: HttpRequest) -> HttpResponse:
        if not _user_is_tenant_admin(request):
            return redirect("/")
        wizards = wizard_engine.list_wizards_for_audience("tenant_admin")
        return render(request, "setup_studio/tenant_wizard_index.html", {"wizards": wizards})


class TenantWizardView(LoginRequiredMixin, View):
    """# rbac-allow: tenant-admin-wizard-engine-access-via-role-registry"""

    audience = "tenant_admin"
    template = "setup_studio/tenant_wizard.html"

    def _resolve(self, request: HttpRequest, wizard_key: str, step_key: str | None):
        try:
            wizard = wizard_engine.get_wizard(wizard_key)
        except wizard_engine.WizardNotFound:
            return None, None, None
        school = _resolve_school(request)
        if school is None:
            return wizard, None, None
        state = wizard_state_resolver.start_wizard(school, wizard_key)
        if step_key is None:
            step_key = state.get("current_step_key") or wizard.first_step().key
        try:
            step = wizard.step_by_key(step_key)
        except wizard_engine.StepNotFound:
            step = wizard.first_step()
        return wizard, step, school

    def get(self, request: HttpRequest, wizard_key: str, step_key: str | None = None) -> HttpResponse:
        if not _user_is_tenant_admin(request):
            return redirect("/")
        wizard, step, school = self._resolve(request, wizard_key, step_key)
        if wizard is None or school is None:
            return redirect("setup_studio:tenant_wizard_index")
        state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
        if state.get("completed_at"):
            return render(request, "setup_studio/tenant_wizard_index.html", {
                "wizards": wizard_engine.list_wizards_for_audience("tenant_admin"),
                "just_completed_wizard_key": wizard.wizard_key,
            })
        wizard_telemetry.emit_step_viewed(wizard.wizard_key, step.key, self.audience)
        context = _build_context(
            request=request, wizard=wizard, step=step,
            audience=self.audience, school=school, state=state,
        )
        return render(request, self.template, context)

    def post(self, request: HttpRequest, wizard_key: str, step_key: str) -> HttpResponse:
        if not _user_is_tenant_admin(request):
            return redirect("/")
        wizard, step, school = self._resolve(request, wizard_key, step_key)
        if wizard is None or school is None:
            return redirect("setup_studio:tenant_wizard_index")
        payload = _parse_post_payload(request, step)
        try:
            wizard_state_resolver.apply_step_answer(
                school, wizard.wizard_key, step.key, payload,
                actor_user_id=getattr(request.user, "pk", None),
            )
        except wizard_engine.WizardError as exc:
            logger.info("TenantWizardView: validation failed: %s", exc)
            state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
            _, errors = wizard_engine.validate_step_answer(step, payload)
            context = _build_context(
                request=request, wizard=wizard, step=step,
                audience=self.audience, school=school, state=state, errors=errors,
            )
            return render(request, self.template, context)
        new_state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
        next_step_key = new_state.get("current_step_key")
        if next_step_key is None:
            return redirect("setup_studio:tenant_wizard_index")
        return redirect("setup_studio:tenant_wizard_step", wizard_key=wizard.wizard_key, step_key=next_step_key)


class WizardAIRecommendView(LoginRequiredMixin, View):
    """AJAX endpoint for smart-default refresh. # rbac-allow: authenticated-user-wizard-ai-recommend"""

    def post(self, request: HttpRequest) -> HttpResponse:
        try:
            body = json.loads(request.body or "{}")
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "invalid_json"}, status=400)
        wizard_key = body.get("wizard_key")
        step_key = body.get("step_key")
        prior_answers = body.get("prior_answers") or {}
        if not (isinstance(wizard_key, str) and isinstance(step_key, str)):
            return JsonResponse({"error": "invalid_payload"}, status=400)
        try:
            wizard = wizard_engine.get_wizard(wizard_key)
            step = wizard.step_by_key(step_key)
        except (wizard_engine.WizardNotFound, wizard_engine.StepNotFound):
            return JsonResponse({"error": "wizard_or_step_not_found"}, status=404)
        if not (step.ai_recommend and step.ai_recommend.get("enabled")):
            return JsonResponse({"suggestions": {}, "used_fallback": True, "rationale_text": None})
        school = _resolve_school(request)
        prompt_key = step.ai_recommend.get("prompt_template_key") or ""
        ctx_keys = step.ai_recommend.get("context_keys") or []
        context = {k: _safe_context_value(request, school, k) for k in ctx_keys}
        options = wizard_engine.resolve_options(step, request=request, school=school)
        result = wizard_ai.request_smart_defaults(
            request=request, school=school,
            wizard_key=wizard_key, step_key=step_key,
            prompt_key=prompt_key, context=context, options=options,
        )
        return JsonResponse({
            "suggestions": result.suggestions,
            "used_fallback": result.used_fallback,
            "rationale_text": result.rationale_text,
            "latency_ms": result.latency_ms,
        })


class WizardStateResetView(LoginRequiredMixin, View):
    """POST → reset wizard state. # rbac-allow: tenant-admin-wizard-reset-state"""

    def post(self, request: HttpRequest, wizard_key: str) -> HttpResponse:
        school = _resolve_school(request)
        if school is None:
            return redirect("/")
        wizard_state_resolver.reset_wizard(
            school, wizard_key, actor_user_id=getattr(request.user, "pk", None),
        )
        audience = "operator" if getattr(request.user, "is_staff", False) else "tenant_admin"
        if audience == "operator":
            return redirect("setup_studio:operator_wizard", wizard_key=wizard_key)
        return redirect("setup_studio:tenant_wizard", wizard_key=wizard_key)


def _user_is_tenant_admin(request: HttpRequest) -> bool:
    """Lightweight role check via apps.platform_runtime.role_registry."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False):
        return True
    try:
        from apps.platform_runtime import role_registry  # type: ignore
        for role_attr in ("user_role", "role", "primary_role"):
            role = getattr(user, role_attr, None)
            if role and role in getattr(role_registry, "TENANT_ADMIN_ROLES", ("tenant_admin", "proprietor", "principal")):
                return True
    except Exception:  # noqa: BLE001
        pass
    # Fallback: rely on Django staff_member_required style — non-staff tenant users with .school must be admins.
    user_role = getattr(user, "role", None) or getattr(user, "user_role", None)
    return user_role in ("tenant_admin", "admin", "proprietor", "principal", "school_admin")
