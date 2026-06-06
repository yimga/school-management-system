"""Tenant agentic actions — Phase 2 (mutating, reversible, confirm-gated).

Role-gated to ADMIN / LEADERSHIP / PRINCIPAL. Exposes the reversible mutating
actions for the user's OWN school (``request.school``): propose → explicit
Confirm (server-side ``confirmed_by`` + single-use token) → execute, with a
per-action reversal. Gated by ``RMC_AI_AGENTIC_MUTATING_ENABLED`` (default off)
plus the platform AI gate; the action list is further filtered to what the
caller's role may actually run. See docs/AI_AGENTIC_ACTIONS_DESIGN.md.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import role_required
from apps.accounts.models import User


_TEMPLATE = "portal/agentic_actions.html"


def _tenant_ctx(request: HttpRequest, school):
    from services.ai_agentic import ActionContext

    tenant_id = str(getattr(school, "id", "") or "")
    user_id = str(getattr(request.user, "id", ""))
    role = str(getattr(request.user, "role", "") or "")
    roles = tuple(r for r in (role,) if r)
    return ActionContext(tenant_id=tenant_id, user_id=user_id, user_roles=roles)


def _normalize_params(spec, source) -> dict:
    """Pull only the spec's declared params from a dict-like, stripped + non-empty.
    Used identically at propose-time (token binding) and confirm-time (re-collect)
    so the params hash matches and the single-use token validates."""
    out = {}
    for key in spec.parameters:
        val = source.get(key)
        val = str(val).strip() if val is not None else ""
        if val:
            out[key] = val
    return out


def _role_permitted_actions(svc, roles):
    role_set = set(roles)
    return [a for a in svc.available_mutating_actions() if role_set & set(a.required_roles)]


@login_required
@role_required(User.Role.ADMIN, User.Role.LEADERSHIP, User.Role.PRINCIPAL)
@require_http_methods(["GET", "POST"])
def tenant_agentic_actions(request: HttpRequest) -> HttpResponse:
    from services import ai_agentic_service as svc
    from services.ai_agentic import ProposedAction

    school = getattr(request, "school", None)
    if school is None:
        return redirect("/")

    enabled = svc.agentic_mutating_enabled(school=school)
    action_ctx = _tenant_ctx(request, school)
    permitted = _role_permitted_actions(svc, action_ctx.user_roles)
    spec_by_name = {a.name: a for a in permitted}

    ctx = {
        "page_title": "Agentic actions",
        "mutating_enabled": enabled,
        "flag_name": "RMC_AI_AGENTIC_MUTATING_ENABLED",
        "actions": [
            {"name": a.name, "description": a.description, "parameters": list(a.parameters)}
            for a in permitted
        ],
        "proposals": None,
        "exec_result": None,
        "reverse_result": None,
        "prompt_text": "",
        "audit_rows": svc.recent_audit(limit=20, tenant_id=action_ctx.tenant_id),
    }

    if request.method == "POST":
        if not enabled:
            ctx["error"] = "Agentic actions are disabled. Set RMC_AI_AGENTIC_MUTATING_ENABLED to enable."
            return render(request, _TEMPLATE, ctx)

        gen = (request.POST.get("gen") or "").strip()

        if gen == "propose":
            prompt = (request.POST.get("prompt") or "").strip()
            ctx["prompt_text"] = prompt
            extra = {
                k: (request.POST.get(k) or "").strip()
                for k in ("student_id", "parent_id", "date", "reason", "preferred_time")
                if (request.POST.get(k) or "").strip()
            }
            raw = svc.propose_mutating(prompt=prompt, ctx=action_ctx, school=school, extra_params=extra)
            proposals = []
            for p in raw:
                spec = spec_by_name.get(p.action)
                if spec is None:  # not permitted for this role — drop
                    continue
                norm = _normalize_params(spec, p.params)
                token = svc.issue_confirm_token(action=p.action, params=norm, user_id=action_ctx.user_id)
                proposals.append({
                    "action": p.action,
                    "param_fields": [{"key": k, "value": norm.get(k, "")} for k in spec.parameters],
                    "rationale": p.rationale,
                    "confidence": round(p.confidence, 2),
                    "confirm_token": token,
                })
            ctx["proposals"] = proposals

        elif gen == "confirm":
            action_name = (request.POST.get("action") or "").strip()
            spec = spec_by_name.get(action_name)
            if spec is None:
                ctx["error"] = "That action is not available to your role."
            else:
                params = _normalize_params(spec, request.POST)
                proposed = ProposedAction(action=action_name, params=params)
                result = svc.confirm_and_execute(
                    proposed=proposed,
                    ctx=action_ctx,
                    confirmed_by_user_id=str(getattr(request.user, "id", "")),
                    confirm_token=(request.POST.get("confirm_token") or "").strip(),
                    school=school,
                )
                ctx["exec_result"] = _result_dict(result)

        elif gen == "reverse":
            audit_id = (request.POST.get("audit_id") or "").strip()
            result = svc.reverse_action(
                audit_id=audit_id,
                ctx=action_ctx,
                confirmed_by_user_id=str(getattr(request.user, "id", "")),
                school=school,
            )
            ctx["reverse_result"] = _result_dict(result)

        ctx["audit_rows"] = svc.recent_audit(limit=20, tenant_id=action_ctx.tenant_id)

    return render(request, _TEMPLATE, ctx)


def _result_dict(result) -> dict:
    return {
        "ok": result.ok,
        "action": result.action,
        "result": result.result,
        "error": result.error,
        "audit_id": result.audit_id,
        "blocked_reason": result.blocked_reason,
    }
