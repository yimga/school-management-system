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
from django.http import HttpRequest, HttpResponse, JsonResponse
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
from apps.setup_studio.wizard_categories import group_wizards_by_category
from apps.setup_studio.wizard_labels import humanize_wizard_error, humanize_wizard_token

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
    """Best-effort school resolution for the wizard surface.

    Tries request.school/tenant, then the CANONICAL resolver
    (``resolve_request_school`` — adds session / signup-verification /
    SchoolMembership fallbacks), then user attrs, then a session school_id.

    The canonical resolver is load-bearing here: on schema-per-tenant prod the
    bridge middleware sets ``request.school = None`` when the Client→School link
    is not yet attached (e.g. a freshly provisioned tenant), which previously
    made every studio wizard bounce back to the index ("clicking a tile reloads
    the page"). The membership fallback resolves the school from the signed-in
    admin even in that window.
    """
    for attr in ("school", "tenant"):
        candidate = getattr(request, attr, None)
        if candidate is not None and getattr(candidate, "pk", None) is not None:
            return candidate
    try:
        from apps.lifecycle.tenant_school_resolve import resolve_request_school

        resolved = resolve_request_school(request)
        if resolved is not None and getattr(resolved, "pk", None) is not None:
            return resolved
    except Exception as exc:  # noqa: BLE001 — resolution is best-effort
        logger.debug("resolve_request_school failed: %s", exc)
    user = getattr(request, "user", None)
    if user is not None:
        for attr in ("school", "tenant", "current_school"):
            candidate = getattr(user, attr, None)
            if candidate is not None and getattr(candidate, "pk", None) is not None:
                return candidate
    # Session fallback: a bound school_id survives across requests where the
    # tenant middleware did not re-attach request.school (e.g. operator host).
    try:
        session = getattr(request, "session", None) or {}
        school_id = session.get("school_id")
        if school_id:
            from apps.schools.session_school_bind import verify_session_school_bind

            if verify_session_school_bind(request, school_id):
                from apps.schools.models import School

                return School.objects.filter(pk=school_id, is_active=True).first()
    except Exception as exc:  # noqa: BLE001 — resolution is best-effort
        logger.debug("session school_id resolution failed: %s", exc)
    return None


def _resolve_resumable_wizards_for_request(request: HttpRequest) -> list[Any]:
    """v4.00.12: best-effort list of wizards the current tenant has started-not-completed in last 7 days.

    Returns [] on any failure — banner / hint UIs degrade silently rather
    than breaking the wizard index page.
    """
    try:
        school = _resolve_school(request)
        if school is None:
            return []
        from apps.setup_studio.models import SetupProgress  # local import — avoids circular at app load
        from apps.setup_studio.wizard_extras import list_resumable_wizards

        progress = SetupProgress.objects.filter(school=school).first()
        if progress is None:
            return []
        step_state = progress.step_state or {}
        wizards_namespace = step_state.get("wizards") if isinstance(step_state, dict) else None
        return list_resumable_wizards(wizards_namespace=wizards_namespace, within_days=7)
    except Exception as exc:  # noqa: BLE001 — best-effort surfacing; never breaks the page
        logger.debug("resumable wizards lookup failed: %s", exc)
        return []


def _resolve_wizard_status_map(request: HttpRequest) -> dict[str, str]:
    """Best-effort ``{wizard_key: "done"|"in_progress"}`` for the current tenant.

    Reads the SAME SetupProgress wizards namespace the resumable banner uses, so
    the bespoke index can paint per-card status + per-stage progress. Returns ``{}``
    on any failure — every card then renders honestly as "Start" rather than the
    page breaking over a status lookup.
    """
    try:
        school = _resolve_school(request)
        if school is None:
            return {}
        from apps.setup_studio.models import SetupProgress  # local import — avoids circular at app load
        from apps.setup_studio.wizard_extras import wizard_status_map

        progress = SetupProgress.objects.filter(school=school).first()
        if progress is None:
            return {}
        step_state = progress.step_state or {}
        wizards_namespace = step_state.get("wizards") if isinstance(step_state, dict) else None
        return wizard_status_map(wizards_namespace)
    except Exception as exc:  # noqa: BLE001 — status is decorative; never breaks the page
        logger.debug("wizard status map lookup failed: %s", exc)
        return {}


def _decorate_stages(groups: list[dict[str, Any]], status_map: dict[str, str]):
    """Decorate grouped stages with per-card status + per-stage/overall progress.

    Returns ``(stages, overall)`` where each stage carries a ``cards`` list of
    ``{"wizard", "status"}`` and a ``progress`` dict. ``overall`` aggregates the
    whole journey for the index hero. Pure-Python; safe with an empty status_map.
    """
    stages: list[dict[str, Any]] = []
    total_all = 0
    done_all = 0
    for g in groups:
        cards = []
        done = 0
        for wiz in g.get("wizards") or []:
            status = status_map.get(getattr(wiz, "wizard_key", ""), "not_started")
            if status == "done":
                done += 1
            title = humanize_wizard_token(getattr(wiz, "label_token", ""))
            desc = humanize_wizard_token(getattr(wiz, "description_token", ""))
            # Wizards without a real translated description humanize their
            # ``wizards.<key>.description`` slug to the SAME stem as the label
            # (both -> "Account Migration"), so the card would print its name
            # twice. Drop the description in that case.
            if desc == title:
                desc = ""
            cards.append({"wizard": wiz, "status": status, "title": title, "desc": desc})
        total = len(cards)
        total_all += total
        done_all += done
        pct = int(round(done * 100 / total)) if total else 0
        stages.append({
            **g,
            "cards": cards,
            "progress": {"done": done, "total": total, "pct": pct, "remaining": total - done},
        })
    overall = {
        "done": done_all,
        "total": total_all,
        "pct": int(round(done_all * 100 / total_all)) if total_all else 0,
        "remaining": total_all - done_all,
    }
    return stages, overall


def _wizard_index_context(wizards: list[Any], status_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Shared index context: the flat list, the grouped sections, AND the bespoke
    lifecycle ``wizard_stages`` (cards + progress) used by the redesigned index.

    The template prefers ``wizard_stages``, then ``wizard_groups``, then the flat
    ``wizards`` list, so every layer is a non-breaking enrichment.
    """
    try:
        groups = group_wizards_by_category(wizards)
    except Exception as exc:  # noqa: BLE001 — never break the index over grouping
        logger.debug("wizard grouping failed: %s", exc)
        groups = []
    try:
        stages, overall = _decorate_stages(groups, status_map or {})
    except Exception as exc:  # noqa: BLE001 — decoration is decorative; never break the index
        logger.debug("wizard stage decoration failed: %s", exc)
        stages, overall = [], {"done": 0, "total": 0, "pct": 0, "remaining": 0}
    return {
        "wizards": wizards,
        "wizard_groups": groups,
        "wizard_stages": stages,
        "overall_progress": overall,
    }


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

    # Branch rationale: for steps WITHOUT field-level smart defaults, once the
    # user has prior answers, explain why they're on this step. Surfaces through
    # the same wizard_ai_rationale.html partial. Fallback-safe; never breaks the
    # wizard (gateway-routed, budget-gated, decorative).
    step_has_smart_defaults = bool(step.ai_recommend and step.ai_recommend.get("enabled"))
    if ai_rationale is None and not step_has_smart_defaults and (state.get("answers") or {}):
        try:
            branch_result = wizard_ai.request_branch_rationale(
                request=request, school=school,
                wizard_key=wizard.wizard_key, step_key=step.key,
                prior_answers=state.get("answers") or {},
                branch_taken=step.key,
            )
            if branch_result.rationale_text:
                ai_rationale = branch_result.rationale_text
        except Exception as exc:  # noqa: BLE001 — rationale is decorative; never break the wizard
            logger.debug("wizard branch rationale failed: %s", exc)

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

    offline_intake_enabled = False
    if school is not None:
        try:
            from apps.siteconfig.config_service import get_effective_site_settings

            site_settings = get_effective_site_settings(request=request, school=school)
            backend_flags = (
                site_settings.get_backend_feature_flags()
                if hasattr(site_settings, "get_backend_feature_flags")
                else getattr(site_settings, "backend_feature_flags", {})
            )
            offline_intake_enabled = bool(
                (backend_flags or {}).get("enable_offline_intake_wizard")
            )
        except (AttributeError, ImportError, TypeError, ValueError):
            offline_intake_enabled = False

    return {
        "wizard": wizard,
        "step": step,
        "audience": audience,
        "school_id": getattr(school, "pk", None),
        "wizard_label": humanize_wizard_token(wizard.label_token),
        "wizard_description": humanize_wizard_token(wizard.description_token),
        "step_label": humanize_wizard_token(step.label_token),
        "step_description": humanize_wizard_token(step.description_token),
        "completed_keys": completed_keys,
        "prior_answer": prior_answer,
        "resolved_options": resolved_options,
        "ai_rationale": ai_rationale,
        "ai_suggested_value": ai_suggested_value,
        # Error dict values are raw ``wizards.errors.*`` slugs off the validator;
        # humanize them here (the single render seam) so every input partial shows
        # a real message. Keys stay the field name (telemetry/template lookup).
        "errors": {k: humanize_wizard_error(v) for k, v in (errors or {}).items()},
        "form_action_url": form_action_url,
        "back_url": back_url,
        "is_final_step": is_final_step,
        "estimated_seconds": step.estimated_seconds,
        "offline_intake_enabled": offline_intake_enabled,
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


def _tenant_wizard_href_template() -> str:
    """Tenant wizard detail URL carrying a literal ``{key}`` placeholder.

    The index template builds every Start/Review tile href by substituting the
    wizard key into this single template (one reverse() instead of one per tile).
    Reverses with a sentinel key, then restores the ``{key}`` placeholder so the
    result equals ``reverse("setup_studio:tenant_wizard", wizard_key=<key>)``.
    """
    sentinel = "keyplaceholder"
    try:
        url = reverse("setup_studio:tenant_wizard", kwargs={"wizard_key": sentinel})
    except Exception:  # noqa: BLE001
        return "/school/studio/wizards/{key}/"
    return url.replace(sentinel, "{key}")


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


def _maybe_handle_nl_intake(
    request: HttpRequest,
    *,
    wizard: wizard_engine.WizardDefinition,
    step: wizard_engine.StepDefinition,
    school: Any,
    audience: str,
    template: str,
) -> HttpResponse | None:
    """Natural-language intake for ``structured_form`` steps.

    When the step's NL-intake control is submitted (``intent=nl_intake``), parse
    the free-text description into DRAFT field values and re-render the SAME step
    with those values pre-filled for the user to review and edit. Nothing is
    persisted — the user must still submit the step normally to save. Returns a
    response when it handled the POST, else ``None`` so the caller proceeds with
    the normal save path. Assistive + fail-soft: never breaks the wizard.
    """
    if request.POST.get("intent") != "nl_intake":
        return None
    if step.input_type != "structured_form":
        return None

    free_text = (request.POST.get("nl_intake_text") or "").strip()
    target_fields = [
        f.get("name")
        for f in (step.fields or [])
        if isinstance(f.get("name"), str)
    ]
    state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
    context = _build_context(
        request=request, wizard=wizard, step=step,
        audience=audience, school=school, state=state,
    )
    context["nl_intake_text"] = free_text

    if free_text and target_fields:
        try:
            intake = wizard_ai.request_natural_language_intake(
                request=request, school=school, wizard_key=wizard.wizard_key,
                free_text=free_text, target_fields=target_fields,
            )
            prefill = {
                k: v
                for k, v in (intake.parsed_fields or {}).items()
                if k in target_fields and v not in (None, "")
            }
            # Merge as DRAFT values into the form — user still submits to save.
            merged = dict(context.get("prior_answer") or {})
            merged.update(prefill)
            context["prior_answer"] = merged
            context["nl_prefill"] = prefill
            context["nl_applied_fields"] = sorted(prefill.keys())
            context["nl_unresolved"] = list(intake.unresolved_phrases or [])
            context["nl_confidence"] = round(float(intake.confidence or 0.0), 2)
            context["nl_used_fallback"] = bool(intake.used_fallback)
        except Exception as exc:  # noqa: BLE001 — intake is assistive; never break the wizard
            logger.debug("wizard nl intake failed: %s", exc)

    return render(request, template, context)


# ---------- Views ----------


@method_decorator(staff_member_required, name="dispatch")
class OperatorWizardIndexView(LoginRequiredMixin, View):
    """Lists operator-audience wizards. # rbac-allow: super-staff-wizard-index"""

    def get(self, request: HttpRequest) -> HttpResponse:
        wizards = wizard_engine.list_wizards_for_audience("operator")
        status_map = _resolve_wizard_status_map(request)
        context = _wizard_index_context(wizards, status_map=status_map)
        return render(request, "setup_studio/operator_wizard_index.html", context)


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
            status_map = _resolve_wizard_status_map(request)
            context = _wizard_index_context(
                wizard_engine.list_wizards_for_audience("operator"), status_map=status_map,
            )
            # Pass the human label, not the raw key: humanize_wizard_token leaves a
            # bare key like "mfa_setup" UNCHANGED, so the completion banner must
            # receive label_token ("Set up two-factor authentication") to read cleanly.
            context["just_completed_wizard_key"] = wizard.label_token
            return render(request, "setup_studio/operator_wizard_index.html", context)
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
        nl_response = _maybe_handle_nl_intake(
            request, wizard=wizard, step=step, school=school,
            audience=self.audience, template=self.template,
        )
        if nl_response is not None:
            return nl_response
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
        # v4.00.5: audience-aware index — non-admin tenant users (parent/teacher/student/staff)
        # see the wizards targeted at their audience, not a deny redirect.
        if _user_is_tenant_admin(request):
            user_audience = "tenant_admin"
        else:
            user_audience = _user_audience(request)
        if user_audience is None:
            context = _wizard_index_context([], status_map={})
            context.update({
                "resumable_wizards": [],
                "user_audience": None,
                "wizard_audience_unmapped": True,
                "wizard_search_audience": "",
            })
            return render(request, "setup_studio/tenant_wizard_index.html", context)
        if user_audience == "tenant_admin":
            wizards = wizard_engine.list_wizards_for_audience("tenant_admin")
        else:
            wizards = wizard_engine.list_wizards_for_audience(user_audience)
        resumable = _resolve_resumable_wizards_for_request(request)
        status_map = _resolve_wizard_status_map(request)
        context = _wizard_index_context(wizards, status_map=status_map)
        context.update({
            "resumable_wizards": resumable,
            "user_audience": user_audience,
            "wizard_search_audience": user_audience if not _user_is_tenant_admin(request) else "tenant_admin",
        })
        return render(request, "setup_studio/tenant_wizard_index.html", context)


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

    def _preview_render(self, request: HttpRequest, wizard: wizard_engine.WizardDefinition, step_key: str | None) -> HttpResponse:
        """v4.00.8 #8: read-only preview — render without touching SetupProgress."""
        try:
            step = wizard.step_by_key(step_key) if step_key else wizard.first_step()
        except wizard_engine.StepNotFound:
            step = wizard.first_step()
        context = _build_context(
            request=request, wizard=wizard, step=step,
            audience=self.audience, school=None,
            state={"answers": {}, "completed": [], "started_at": "", "preview": True},
        )
        context["preview_mode"] = True
        return render(request, self.template, context)

    def get(self, request: HttpRequest, wizard_key: str, step_key: str | None = None) -> HttpResponse:
        # v4.00.5: dispatch on audience match, not just tenant_admin — so
        # parent/teacher/student/staff wizards reach their target users.
        try:
            wizard_for_audience_check = wizard_engine.get_wizard(wizard_key)
        except wizard_engine.WizardNotFound:
            return redirect("setup_studio:tenant_wizard_index")
        if not _user_can_run_wizard(request, wizard_for_audience_check):
            return redirect("/")
        # v4.00.8 #8: preview mode — ?preview=1 renders the wizard against the
        # registry without touching SetupProgress at all. Lets operators QA new
        # JSON definitions without polluting analytics. Staff-only — non-staff
        # users get redirected back to the live flow.
        if request.GET.get("preview") == "1" and getattr(request.user, "is_staff", False):
            return self._preview_render(request, wizard_for_audience_check, step_key)
        wizard, step, school = self._resolve(request, wizard_key, step_key)
        if wizard is None or school is None:
            return redirect("setup_studio:tenant_wizard_index")
        state = wizard_state_resolver.get_wizard_state(school, wizard.wizard_key)
        if state.get("completed_at"):
            # v4.00.x: a completed wizard renders the wizard SHELL in read-only
            # review mode (saved answers + a review banner) rather than bouncing
            # back to the index — so a Review tile lands on the wizard it names.
            user_audience = _user_audience(request) or "tenant_admin"
            next_suggestions = []
            try:
                from apps.setup_studio.wizard_next_steps import get_suggestions
                from apps.setup_studio.wizard_extras import resolve_wizard_label

                for s in get_suggestions(wizard.wizard_key, audience=user_audience):
                    next_suggestions.append({
                        "target_wizard_key": s.target_wizard_key,
                        "label_token": s.label_token,
                        "resolved_label": resolve_wizard_label(s.target_wizard_key),
                        "priority": s.priority,
                    })
            except Exception:  # noqa: BLE001
                next_suggestions = []
            review_step = step or wizard.first_step()
            context = _build_context(
                request=request, wizard=wizard, step=review_step,
                audience=self.audience, school=school, state=state,
            )
            context.update({
                "review_mode": True,
                "just_completed_wizard_key": wizard.label_token,
                "next_step_suggestions": next_suggestions,
                "wizard_index_url": reverse("setup_studio:tenant_wizard_index"),
            })
            return render(request, self.template, context)
        wizard_telemetry.emit_step_viewed(wizard.wizard_key, step.key, self.audience)
        context = _build_context(
            request=request, wizard=wizard, step=step,
            audience=self.audience, school=school, state=state,
        )
        return render(request, self.template, context)

    def post(self, request: HttpRequest, wizard_key: str, step_key: str) -> HttpResponse:
        try:
            wizard_for_audience_check = wizard_engine.get_wizard(wizard_key)
        except wizard_engine.WizardNotFound:
            return redirect("setup_studio:tenant_wizard_index")
        if not _user_can_run_wizard(request, wizard_for_audience_check):
            return redirect("/")
        wizard, step, school = self._resolve(request, wizard_key, step_key)
        if wizard is None or school is None:
            return redirect("setup_studio:tenant_wizard_index")
        nl_response = _maybe_handle_nl_intake(
            request, wizard=wizard, step=step, school=school,
            audience=self.audience, template=self.template,
        )
        if nl_response is not None:
            return nl_response
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
    """Django staff OR a tenant-admin User.Role (ADMIN / PROPRIETOR / PRINCIPAL)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False):
        return True
    # Compare case-insensitively against CANONICAL User.Role tokens. The previous
    # implementation read a nonexistent role_registry.TENANT_ADMIN_ROLES and fell
    # back to lowercase tuples ("admin"/"proprietor"/...) that could NEVER match the
    # uppercase User.role value — so every non-staff tenant admin was wrongly denied.
    for role_attr in ("user_role", "role", "primary_role"):
        role = getattr(user, role_attr, None)
        if role and str(role).strip().upper() in _TENANT_ADMIN_USER_ROLES:
            return True
    return False


# Canonical tenant-admin User.Role tokens (single source: apps/accounts/models.py
# User.Role). "tenant_admin"/"school_admin" are conceptual aliases of ADMIN.
_TENANT_ADMIN_USER_ROLES = frozenset({"ADMIN", "PROPRIETOR", "PRINCIPAL"})  # role-string-allow: canonical-User.Role-tenant-admin-tokens


_ROLE_TO_AUDIENCE = {
    "admin":           "tenant_admin",
    "tenant_admin":    "tenant_admin",
    "principal":       "tenant_admin",
    "proprietor":      "tenant_admin",
    "school_admin":    "tenant_admin",
    "leadership":      "tenant_admin",
    "it_admin":        "tenant_admin",
    "teacher":         "teacher",
    "dept_lead":       "teacher",
    "hod":             "teacher",
    "parent":          "parent",
    "student":         "student",
    "staff":           "staff",
    "finance_staff":   "staff",
    "academics_staff": "staff",
    "comms_staff":     "staff",
}


def _user_audience(request: HttpRequest) -> str | None:
    """Return the wizard audience slug for the request's user, or None.

    Used by TenantWizardView to allow parent/teacher/student/staff users
    onto wizards whose audience array includes their resolved audience.
    Staff always resolve to ``operator`` so staff_member_required style
    routes work — but their role-derived audience overrides when set.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    if getattr(user, "is_staff", False):
        return "operator"
    for attr in ("user_role", "role", "primary_role"):
        role = getattr(user, attr, None)
        if role:
            audience = _ROLE_TO_AUDIENCE.get(str(role).lower())
            if audience:
                return audience
    return None


def _user_can_run_wizard(request: HttpRequest, wizard: wizard_engine.WizardDefinition) -> bool:
    """Permit when the user's resolved audience appears in the wizard's audience array.

    Tenant admins and staff can always reach tenant_admin wizards via the
    legacy ``_user_is_tenant_admin`` path. The new path adds audience-matching
    so a teacher reaches teacher wizards, a parent reaches parent wizards, etc.
    """
    if _user_is_tenant_admin(request):
        # A tenant admin (role ADMIN/PROPRIETOR/PRINCIPAL on the tenant host) may
        # run tenant_admin wizards ONLY. The previous `or "operator" in audience`
        # clause leaked operator-only wizards (e.g. super_create_school,
        # jit_operator_compliance_safeguarding) to tenant admins via direct URL.
        # Operator-audience wizards are reached through the staff-gated operator
        # surface: an is_staff user falls through to the audience check below,
        # where `_user_audience` resolves to "operator" and admits them.
        if "tenant_admin" in wizard.audience:
            return True
    user_audience = _user_audience(request)
    if user_audience is None:
        return False
    return user_audience in wizard.audience
