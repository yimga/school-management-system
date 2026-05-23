"""Tenant ExperienceTemplate marketplace views.

The operator surface lives under ``/configuration/experience-templates/*`` and
reuses ``apps.platform_runtime.views_administration.pack_*`` views directly
(see ``configuration_urls.py``). This module handles the *tenant* surface
under ``/school/studio/templates/*`` and enforces ``tenant_safe_only=True``
filtering so operator-only templates can never leak into a tenant catalog.

All views delegate to the existing pack lifecycle (``preview_pack`` /
``simulate_pack`` / ``analyze_pack_impact`` / ``apply_pack``) — no new lifecycle
code lives here.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.brand_experience.experience_templates import (
    get_overlay,
    list_overlays,
)
from apps.brand_experience.template_ai_recommender import (
    recommend_for_school,
    recommend_local_first_for_country,
)
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_contract import get_pack, list_packs
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.pack_simulation import simulate_pack


def _tenant_school(request: HttpRequest):
    """Return the tenant school resolved by middleware, or 404."""
    school = getattr(request, "tenant", None) or getattr(request, "school", None)
    if school is None:
        raise Http404("Tenant school not resolved.")
    return school


def _gate_operator_only(template_key: str) -> None:
    """Refuse access to operator-only templates from tenant views."""
    overlay = get_overlay(template_key)
    if overlay is None:
        raise Http404(f"Unknown template: {template_key}")
    if overlay.is_operator_only():
        raise Http404(f"Template {template_key} is not available in the tenant catalog.")


@login_required
@require_http_methods(["GET"])
def tenant_template_marketplace(request: HttpRequest) -> HttpResponse:
    """Browse the tenant-safe catalog with category / country / role filters."""
    school = _tenant_school(request)
    category = request.GET.get("category") or None
    country = request.GET.get("country") or None
    language = request.GET.get("language") or None
    overlays = list_overlays(
        category=category,
        country=country,
        language=language,
        tenant_safe_only=True,
    )
    packs_by_key = {p["key"]: p for p in list_packs(pack_type="experience_template", tenant_safe_only=True)}
    rows = []
    for o in overlays:
        pack = packs_by_key.get(o["key"])
        if not pack:
            continue
        rows.append({**pack, **o})
    category_counts: dict[str, int] = {}
    for row in rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    return render(
        request,
        "marketplace/templates_browse.html",
        {
            "templates": rows,
            "template_total": len(rows),
            "template_local_first_total": sum(1 for row in rows if row.get("is_local_first")),
            "template_category_total": len(category_counts),
            "selected_school": school,
            "active_category": category or "",
            "active_country": country or "",
            "active_language": language or "",
            "categories": ["tenant-admin", "teacher", "parent", "student", "staff", "specialized", "local-first"],
        },
    )


@login_required
@require_http_methods(["GET"])
def tenant_template_detail(request: HttpRequest, key: str) -> HttpResponse:
    _gate_operator_only(key)
    school = _tenant_school(request)
    pack = get_pack(key, pack_type="experience_template")
    overlay = get_overlay(key)
    return render(
        request,
        "marketplace/templates_detail.html",
        {
            "pack": pack.as_dict() if pack else {},
            "overlay": overlay.as_dict() if overlay else {},
            "selected_school": school,
        },
    )


@login_required
@require_http_methods(["GET"])
def tenant_template_preview(request: HttpRequest, key: str) -> HttpResponse:
    _gate_operator_only(key)
    school = _tenant_school(request)
    result = preview_pack(
        key, pack_type="experience_template", school=school, actor=request.user,
        platform_operator=False, emit_audit=True,
    )
    return render(
        request,
        "marketplace/templates_preview_frame.html",
        {"preview": result, "selected_school": school, "template_key": key},
    )


@login_required
@require_http_methods(["GET"])
def tenant_template_compare(request: HttpRequest, key: str) -> HttpResponse:
    _gate_operator_only(key)
    school = _tenant_school(request)
    other = request.GET.get("other", "")
    if other:
        _gate_operator_only(other)
    a = get_overlay(key)
    b = get_overlay(other) if other else None
    return render(
        request,
        "marketplace/templates_compare.html",
        {
            "a_overlay": a.as_dict() if a else {},
            "b_overlay": b.as_dict() if b else None,
            "a_pack": (get_pack(key, pack_type="experience_template") or "").as_dict() if get_pack(key, pack_type="experience_template") else {},
            "b_pack": (get_pack(other, pack_type="experience_template") or "").as_dict() if other and get_pack(other, pack_type="experience_template") else None,
            "selected_school": school,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def tenant_template_apply(request: HttpRequest, key: str) -> HttpResponse:
    _gate_operator_only(key)
    school = _tenant_school(request)
    preview = preview_pack(key, pack_type="experience_template", school=school, actor=request.user, platform_operator=False)
    simulation = simulate_pack(key, pack_type="experience_template", school=school, actor=request.user, platform_operator=False)
    impact = analyze_pack_impact(key, pack_type="experience_template", school=school, actor=request.user, platform_operator=False)
    result = None
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        result = apply_pack(
            key,
            pack_type="experience_template",
            school=school,
            actor=request.user,
            preview_snapshot=preview,
            simulation_snapshot=simulation,
            impact_snapshot=impact,
            confirmed=True,
        )
    return render(
        request,
        "marketplace/templates_apply_confirm.html",
        {
            "preview": preview,
            "simulation": simulation,
            "impact": impact,
            "result": result,
            "selected_school": school,
            "template_key": key,
        },
    )


@login_required
@require_http_methods(["GET"])
def tenant_local_first_catalog(request: HttpRequest, country_code: str) -> HttpResponse:
    school = _tenant_school(request)
    cc = (country_code or "").upper()
    rows = recommend_local_first_for_country(cc)
    return render(
        request,
        "marketplace/_local_first_catalog.html",
        {"templates": rows, "country": cc, "selected_school": school},
    )


@login_required
@require_http_methods(["GET"])
def tenant_template_ai_recommendation(request: HttpRequest) -> JsonResponse:
    school = _tenant_school(request)
    rec = recommend_for_school(school, user=request.user, request=request, use_ai=True)
    return JsonResponse(rec.as_dict())


@login_required
@require_http_methods(["GET", "POST"])
def tenant_template_rollback(request: HttpRequest, key: str) -> HttpResponse:
    """Rollback the active TemplateAssignment for this tenant + template_key.

    Delegates to the existing pack rollback engine; emits a
    ``template.rolled_back`` TemplateAuditEvent on success.
    """
    _gate_operator_only(key)
    school = _tenant_school(request)
    from apps.brand_experience.models_template import (
        TemplateAssignment,
        record_template_event,
    )
    from apps.packages.engine import rollback as rollback_package
    from apps.packages.models import InstalledPackage

    assignment = (
        TemplateAssignment.objects.filter(
            template_key=key,
            installed_package__school=school,
            installed_package__is_active=True,
        )
        .select_related("installed_package")
        .order_by("-applied_at")
        .first()
    )
    result: dict | None = None
    if request.method == "POST" and request.POST.get("confirm") == "yes" and assignment is not None:
        result = rollback_package(assignment.installed_package, actor_id=request.user.pk)
        try:
            record_template_event(
                tenant_slug=getattr(school, "slug", "") or "",
                event_type="template.rolled_back",
                template_key=key,
                local_profile_key=assignment.local_profile_key or "",
                actor_id=request.user.pk,
                payload={"rollback_ok": bool(result and result.get("ok"))},
            )
        except Exception:
            pass
    return render(
        request,
        "marketplace/templates_rollback_confirm.html",
        {
            "template_key": key,
            "assignment": assignment,
            "result": result,
            "selected_school": school,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def tenant_template_customize(request: HttpRequest, key: str) -> HttpResponse:
    """Customize the active TemplateAssignment for this tenant + template_key.

    Edits the ``customizations`` JSON on the assignment. Records a
    ``template.customized`` audit event on save.
    """
    _gate_operator_only(key)
    school = _tenant_school(request)
    from apps.brand_experience.models_template import (
        TemplateAssignment,
        record_template_event,
    )

    assignment = (
        TemplateAssignment.objects.filter(
            template_key=key,
            installed_package__school=school,
            installed_package__is_active=True,
        )
        .order_by("-applied_at")
        .first()
    )
    saved = False
    error = ""
    if request.method == "POST" and assignment is not None:
        raw = request.POST.get("customizations_json", "").strip()
        if raw:
            import json as _json
            try:
                parsed = _json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("customizations must be a JSON object")
                assignment.customizations = parsed
                assignment.save(update_fields=["customizations"])
                saved = True
                try:
                    record_template_event(
                        tenant_slug=getattr(school, "slug", "") or "",
                        event_type="template.customized",
                        template_key=key,
                        local_profile_key=assignment.local_profile_key or "",
                        actor_id=request.user.pk,
                        payload={"keys_set": sorted(list(parsed.keys()))[:10]},
                    )
                except Exception:
                    pass
            except (ValueError, TypeError) as exc:
                error = str(exc)
        else:
            error = "customizations_json field is empty"
    return render(
        request,
        "marketplace/templates_customize.html",
        {
            "template_key": key,
            "assignment": assignment,
            "saved": saved,
            "error": error,
            "selected_school": school,
        },
    )
