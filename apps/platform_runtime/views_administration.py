from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.platform_runtime.administration_catalog import (
    BLUEPRINTS,
    compute_configuration_summary,
    enrich_tenant_configuration_sections,
    enriched_modules,
    module_by_key,
    resolved_pack_rows,
    resolved_registry_rows,
)
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_contract import get_blueprint, list_blueprints
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.readiness_meters import blueprint_readiness, pack_readiness
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.configuration_change_requests import (
    apply_approved_change_request,
    approve_change_request,
    cancel_change_request,
    create_change_request,
    reject_change_request,
    schedule_change_request,
)
from apps.platform_runtime.configuration_change_set import (
    generate_blueprint_change_set,
    generate_pack_change_set,
)
from apps.platform_runtime.installation_health import (
    calculate_blueprint_installation_health,
    calculate_pack_installation_health,
)
from apps.platform_runtime.models import BlueprintInstallation, ConfigurationChangeRequest
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.operational_center_nav import (
    blueprint_marketplace_frame_context,
    tenant_blueprint_setup_frame_context,
    tenant_pack_setup_frame_context,
    change_requests_frame_context,
    configuration_center_frame_context,
    pack_marketplace_frame_context,
    school_configuration_frame_context,
    tenant_import_setup_frame_context,
)
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_contract import get_pack, list_packs
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.pack_rollback import (
    deactivate_pack_installation,
    rollback_pack_installation,
)
from apps.platform_runtime.pack_simulation import simulate_pack
from apps.platform_runtime.registry_health import evaluate_registry_health
from apps.schools.control_plane import require_control_plane_access
from apps.schools.models import School
from apps.schools.setup_health import setup_health_score


@require_control_plane_access
def configuration_center(request):
    return render(
        request,
        "platform_runtime/configuration_center.html",
        {
            "modules": enriched_modules(),
            "summary": compute_configuration_summary(),
            "page_marker": "rmc-platform-configuration-center",
            "os_center_key": "platform_configuration_center",
            **configuration_center_frame_context(),
        },
    )


@require_control_plane_access
def configuration_module_detail(request, module_key: str):
    module = module_by_key(module_key)
    if module is None:
        return HttpResponseForbidden("Unknown platform configuration module.")
    context = {
        "module": module,
        "page_marker": f"rmc-configuration-module-{module_key}",
        "os_center_key": "platform_configuration_center",
        "center_purpose": module["purpose"],
    }
    if module_key == "blueprints":
        context["blueprints"] = BLUEPRINTS
    elif module_key in {"packages", "workflow-packs", "dashboard-packs", "policy-bundles"}:
        context["packs"] = resolved_pack_rows(module_key)
        context["pack_key"] = module_key
    elif module_key == "registries":
        context["registries"] = resolved_registry_rows()
    elif module_key == "experience":
        from apps.siteconfig.theme_experience_surfaces import (
            build_platform_theme_experience_surfaces,
        )

        context["theme_experience_surfaces"] = build_platform_theme_experience_surfaces()
    else:
        context["related_modules"] = enriched_modules()
    return render(request, "platform_runtime/configuration_module_detail.html", context)


@require_control_plane_access
def registry_health_view(request):
    from apps.platform_runtime.administration_catalog import REGISTRIES

    result = evaluate_registry_health(
        [dict(row) for row in REGISTRIES],
        route_inventory={str(row.get("route") or "") for row in REGISTRIES},
    )
    return render(
        request,
        "platform_runtime/registry_health.html",
        {
            "health": result,
            "page_marker": "rmc-registry-health-dashboard",
            "os_center_key": "platform_configuration_center",
        },
    )


def _selected_school(request):
    slug = (request.GET.get("school") or request.POST.get("school") or "").strip()
    if not slug:
        return School.objects.filter(is_active=True).order_by("name").first()
    return School.objects.filter(slug=slug).first()


@require_control_plane_access
def blueprint_marketplace(request):
    from django.core.paginator import Paginator

    schools = School.objects.filter(is_active=True).order_by("name")[:50]
    blueprint_page = Paginator(list_blueprints(), 12).get_page(
        request.GET.get("page") or 1
    )
    return render(
        request,
        "platform_runtime/blueprint_marketplace.html",
        {
            "blueprints": blueprint_page.object_list,
            "page_obj": blueprint_page,
            "schools": schools,
            "selected_school": _selected_school(request),
            "page_marker": "rmc-blueprint-marketplace-depth",
            **blueprint_marketplace_frame_context(),
        },
    )


@require_control_plane_access
def blueprint_detail(request, key: str):
    blueprint = get_blueprint(key)
    if blueprint is None:
        return HttpResponseForbidden("Unknown blueprint.")
    return render(
        request,
        "platform_runtime/blueprint_detail.html",
        {
            "blueprint": blueprint.as_dict(),
            "selected_school": _selected_school(request),
        },
    )


@require_control_plane_access
def blueprint_preview_view(request, key: str):
    school = _selected_school(request)
    result = preview_blueprint(
        key,
        school=school,
        actor=request.user,
        platform_operator=True,
        emit_audit=True,
    )
    return render(
        request,
        "platform_runtime/blueprint_preview.html",
        {"preview": result, "selected_school": school},
    )


@require_control_plane_access
def blueprint_impact_view(request, key: str):
    school = _selected_school(request)
    result = analyze_blueprint_impact(
        key,
        school=school,
        actor=request.user,
        platform_operator=True,
        emit_audit=True,
    )
    return render(
        request,
        "platform_runtime/blueprint_impact.html",
        {"impact": result, "selected_school": school},
    )


@require_control_plane_access
def blueprint_apply_view(request, key: str):
    school = _selected_school(request)
    preview = preview_blueprint(key, school=school, actor=request.user, platform_operator=True)
    change_set = generate_blueprint_change_set(key, school=school, actor=request.user, platform_operator=True)
    result = None
    change_request = None
    if request.method == "POST":
        if change_set["requires_approval"] or request.POST.get("action") == "request_approval":
            change_request = create_change_request(
                ConfigurationChangeRequest.RequestType.BLUEPRINT_APPLY,
                target_key=key,
                target_type="blueprint",
                school=school,
                actor=request.user,
                reason=request.POST.get("reason", ""),
                platform_operator=True,
            )
            return redirect("configuration:change_request_detail", request_id=change_request.pk)
        else:
            result = apply_blueprint(
                key,
                school=school,
                actor=request.user,
                preview_snapshot=preview,
                confirmed=request.POST.get("confirm") == "yes",
                platform_operator=True,
            )
            if result.get("ok"):
                return redirect("configuration:blueprint_installation_detail", installation_id=result["installation_id"])
    return render(
        request,
        "platform_runtime/blueprint_apply.html",
        {"preview": preview, "change_set": change_set, "result": result, "change_request": change_request, "selected_school": school},
    )


@require_control_plane_access
def blueprint_installations(request):
    installations = BlueprintInstallation.objects.select_related("school", "applied_by")[:100]
    return render(
        request,
        "platform_runtime/blueprint_installations.html",
        {"installations": installations},
    )


@require_control_plane_access
def blueprint_installation_detail(request, installation_id: int):
    installation = get_object_or_404(
        BlueprintInstallation.objects.select_related("school", "applied_by"),
        pk=installation_id,
    )
    return render(
        request,
        "platform_runtime/blueprint_installation_detail.html",
        {"installation": installation, "health": calculate_blueprint_installation_health(installation)},
    )


@require_control_plane_access
def blueprint_rollback_view(request, installation_id: int):
    installation = get_object_or_404(
        BlueprintInstallation.objects.select_related("school", "applied_by"),
        pk=installation_id,
    )
    result = None
    if request.method == "POST":
        result = rollback_blueprint_installation(
            installation,
            actor=request.user,
            confirmed=request.POST.get("confirm") == "yes",
        )
    return render(
        request,
        "platform_runtime/blueprint_rollback.html",
        {"installation": installation, "result": result},
    )


PACK_ROUTE_TYPES = {
    "workflow-packs": "workflow_pack",
    "dashboard-packs": "dashboard_pack",
    "policy-bundles": "policy_bundle",
    "experience-templates": "experience_template",
}


def _pack_template_prefix(pack_type: str) -> str:
    return pack_type.replace("_", "-")


@require_control_plane_access
def pack_marketplace(request, pack_route: str):
    from django.core.paginator import Paginator

    pack_type = PACK_ROUTE_TYPES.get(pack_route)
    if not pack_type:
        return HttpResponseForbidden("Unknown pack route.")
    pack_page = Paginator(list_packs(pack_type=pack_type), 12).get_page(
        request.GET.get("page") or 1
    )
    return render(
        request,
        "platform_runtime/pack_marketplace.html",
        {
            "packs": pack_page.object_list,
            "page_obj": pack_page,
            "pack_route": pack_route,
            "pack_type": pack_type,
            "selected_school": _selected_school(request),
            "schools": School.objects.filter(is_active=True).order_by("name")[:50],
            **pack_marketplace_frame_context(),
        },
    )


@require_control_plane_access
def pack_detail(request, pack_route: str, key: str):
    pack_type = PACK_ROUTE_TYPES.get(pack_route)
    pack = get_pack(key, pack_type=pack_type)
    if pack is None:
        return HttpResponseForbidden("Unknown pack.")
    return render(
        request,
        "platform_runtime/pack_detail.html",
        {
            "pack": pack.as_dict(),
            "pack_route": pack_route,
            "selected_school": _selected_school(request),
            "change_set": generate_pack_change_set(pack.key, pack_type=pack_type, school=_selected_school(request), actor=request.user, platform_operator=True),
        },
    )


@require_control_plane_access
def pack_preview_view(request, pack_route: str, key: str):
    pack_type = PACK_ROUTE_TYPES.get(pack_route)
    school = _selected_school(request)
    result = preview_pack(key, pack_type=pack_type, school=school, actor=request.user, platform_operator=True, emit_audit=True)
    return render(request, "platform_runtime/pack_preview.html", {"preview": result, "pack_route": pack_route, "selected_school": school})


@require_control_plane_access
def pack_simulation_view(request, pack_route: str, key: str):
    pack_type = PACK_ROUTE_TYPES.get(pack_route)
    school = _selected_school(request)
    result = simulate_pack(key, pack_type=pack_type, school=school, actor=request.user, scenario=request.GET.get("scenario") or "standard", platform_operator=True, emit_audit=True)
    return render(request, "platform_runtime/pack_simulation.html", {"simulation": result, "pack_route": pack_route, "selected_school": school})


@require_control_plane_access
def pack_impact_view(request, pack_route: str, key: str):
    pack_type = PACK_ROUTE_TYPES.get(pack_route)
    school = _selected_school(request)
    result = analyze_pack_impact(key, pack_type=pack_type, school=school, actor=request.user, platform_operator=True, emit_audit=True)
    return render(request, "platform_runtime/pack_impact.html", {"impact": result, "pack_route": pack_route, "selected_school": school})


@require_control_plane_access
def pack_apply_view(request, pack_route: str, key: str):
    pack_type = PACK_ROUTE_TYPES.get(pack_route)
    school = _selected_school(request)
    preview = preview_pack(key, pack_type=pack_type, school=school, actor=request.user, platform_operator=True)
    simulation = simulate_pack(key, pack_type=pack_type, school=school, actor=request.user, platform_operator=True)
    impact = analyze_pack_impact(key, pack_type=pack_type, school=school, actor=request.user, platform_operator=True)
    change_set = generate_pack_change_set(key, pack_type=pack_type, school=school, actor=request.user, platform_operator=True)
    result = None
    change_request = None
    if request.method == "POST":
        if change_set["requires_approval"] or request.POST.get("action") == "request_approval":
            change_request = create_change_request(
                ConfigurationChangeRequest.RequestType.PACK_APPLY,
                target_key=key,
                target_type=pack_type,
                school=school,
                actor=request.user,
                reason=request.POST.get("reason", ""),
                platform_operator=True,
            )
            return redirect("configuration:change_request_detail", request_id=change_request.pk)
        else:
            result = apply_pack(
                key,
                pack_type=pack_type,
                school=school,
                actor=request.user,
                preview_snapshot=preview,
                simulation_snapshot=simulation,
                impact_snapshot=impact,
                confirmed=request.POST.get("confirm") == "yes",
                platform_operator=True,
            )
            if result.get("ok"):
                return redirect("configuration:pack_installation_detail", installation_id=result["installation_id"])
    return render(request, "platform_runtime/pack_apply.html", {"preview": preview, "simulation": simulation, "impact": impact, "change_set": change_set, "change_request": change_request, "result": result, "pack_route": pack_route, "selected_school": school})


@require_control_plane_access
def pack_installations(request):
    installations = PackInstallation.objects.select_related("school", "applied_by", "blueprint_installation")[:100]
    return render(request, "platform_runtime/pack_installations.html", {"installations": installations})


@require_control_plane_access
def pack_installation_detail(request, installation_id: int):
    installation = get_object_or_404(PackInstallation.objects.select_related("school", "applied_by", "blueprint_installation"), pk=installation_id)
    return render(request, "platform_runtime/pack_installation_detail.html", {"installation": installation, "health": calculate_pack_installation_health(installation)})


@require_control_plane_access
def pack_rollback_view(request, installation_id: int):
    installation = get_object_or_404(PackInstallation.objects.select_related("school", "applied_by"), pk=installation_id)
    result = None
    if request.method == "POST":
        if request.POST.get("mode") == "deactivate":
            result = deactivate_pack_installation(installation, actor=request.user, confirmed=request.POST.get("confirm") == "yes")
        else:
            result = rollback_pack_installation(installation, actor=request.user, confirmed=request.POST.get("confirm") == "yes")
    return render(request, "platform_runtime/pack_rollback.html", {"installation": installation, "result": result})


def tenant_configuration_forbidden(request, *args, **kwargs):
    return HttpResponseForbidden("Platform configuration requires control-plane access.")


def internal_admin_alias_redirect(request, remaining: str = ""):
    target = "/admin/"
    if remaining:
        target = f"{target}{remaining}"
    if request.GET:
        target = f"{target}?{request.GET.urlencode()}"
    return redirect(target)


@login_required
def school_configuration_center(request):
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return HttpResponseForbidden("Tenant school configuration access required.")
    # Real school readiness (school created / branding / dashboard / plan) from
    # setup_health_score — replaces the hardcoded "74" so the bar reaches 100
    # only when the four setup facts are actually satisfied.
    health = setup_health_score(school)
    school_readiness = {
        "value": health["score"],
        "unmet": [label for _name, passed, label in health["checks"] if not passed],
        "complete": health["score"] >= 100,
    }
    from apps.platform_runtime.page_status_tags import (
        STATUS_ATTENTION,
        STATUS_HEALTHY,
        STATUS_NEEDS_SETUP,
        build_masthead,
        chip,
    )

    status_key = (
        STATUS_HEALTHY
        if school_readiness["complete"]
        else (STATUS_NEEDS_SETUP if school_readiness["unmet"] else STATUS_ATTENTION)
    )
    chips = [
        chip(
            label=f"{school_readiness['value']}% ready",
            tone="success" if school_readiness["complete"] else "warning",
        ),
    ]
    for label in school_readiness["unmet"][:3]:
        chips.append(chip(label=label, tone="danger"))
    masthead = build_masthead(
        archetype="setup",
        host="tenant",
        eyebrow="Setup · this school",
        title="Configuration",
        purpose=(
            "Live readiness for school settings, blueprints, packs, and money. "
            "Blockers first — definitions in info tags."
        ),
        chips=chips,
        primary_url="/school/setup/blueprints/",
        primary_label="Continue setup",
        secondary_url="/school/audit/",
        secondary_label="Review audit trail",
        status_key=status_key,
        freshness_label="Live readiness",
    )
    return render(
        request,
        "platform_runtime/school_configuration_center.html",
        {
            "school": school,
            "sections": enrich_tenant_configuration_sections(school),
            "school_readiness": school_readiness,
            "page_marker": "rmc-school-configuration-center",
            **school_configuration_frame_context(),
            **masthead,
        },
    )


@login_required
def tenant_import_setup(request):
    from apps.lifecycle.tenant_school_resolve import require_tenant_lifecycle_school

    school, denied = require_tenant_lifecycle_school(request)
    if denied is not None:
        return denied

    def _card_url(name: str, fallback: str) -> str:
        # Resolve against the live (tenant) urlconf so the CTA always lands on a
        # routed view. The previous hardcoded paths (``/admin/accounts/student/import/``,
        # ``/siteconfig/onboarding/step/staff/``, ``/migration/``) are NOT mounted on
        # the tenant host, so every card 404'd. Fall back to the known tenant path if
        # a name is ever renamed rather than 500-ing the whole imports page.
        try:
            return reverse(name)
        except NoReverseMatch:
            return fallback

    import_cards = [
        {
            "key": "students",
            "title": "Students and guardians",
            "detail": "Start with a clean roster so attendance, reports, fees, and parent access have real records.",
            "template_label": "Student CSV template",
            "cta_label": "Open student import",
            "cta_url": _card_url("accounts:migration_wizard", "/authentication/backend/migration-wizard/"),
        },
        {
            "key": "staff",
            "title": "Staff and teachers",
            "detail": "Load staff before assigning classes, subjects, attendance owners, or approval flows.",
            "template_label": "Staff CSV template",
            "cta_label": "Open staff setup",
            "cta_url": _card_url("accounts:backend_teacher_list", "/authentication/backend/teachers/"),
        },
        {
            "key": "fees",
            "title": "Fees and balances",
            "detail": "Bring fee categories and balances after the roster is ready; keep manual receipts auditable.",
            "template_label": "Finance import checklist",
            "cta_label": "Open finance setup",
            "cta_url": _card_url("finance:payment_readiness_setup", "/finance/payment-setup/"),
        },
        {
            "key": "migration_cloud",
            "title": "Migration Cloud",
            "detail": "Use connector intake when the source system is PowerSchool, Veracross, FACTS, spreadsheets, or a custom SIS.",
            "template_label": "Connector handoff",
            "cta_label": "Open migration intake",
            "cta_url": _card_url(
                "migration_cloud_connector:connector-home",
                "/school/setup/migration-cloud/",
            ),
        },
    ]
    return render(
        request,
        "platform_runtime/tenant_import_setup.html",
        {
            "school": school,
            "import_cards": import_cards,
            "page_marker": "rmc-tenant-import-setup",
            # Frame header (eyebrow / title / purpose / status badge / nav groups).
            # Sibling setup views all spread their frame context; this one omitted
            # it, so the operational-center header rendered bare.
            **tenant_import_setup_frame_context(),
        },
    )


@login_required
def tenant_blueprint_setup(request):
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return HttpResponseForbidden("Tenant school configuration access required.")
    blueprints = list_blueprints(tenant_safe_only=True)
    selected_key = (
        request.POST.get("blueprint") or request.GET.get("blueprint") or blueprints[0]["key"]
    ).strip()
    preview = preview_blueprint(
        selected_key,
        school=school,
        actor=request.user,
        platform_operator=False,
        emit_audit=request.GET.get("preview") == "1",
    )
    result = None
    if request.method == "POST":
        change_set = generate_blueprint_change_set(selected_key, school=school, actor=request.user, platform_operator=False)
        if change_set["requires_approval"]:
            change_request = create_change_request(
                ConfigurationChangeRequest.RequestType.BLUEPRINT_APPLY,
                target_key=selected_key,
                target_type="blueprint",
                school=school,
                actor=request.user,
                reason=request.POST.get("reason", "Tenant school setup request"),
                platform_operator=False,
            )
            result = {"ok": True, "change_request_id": change_request.pk, "status": change_request.status}
        else:
            result = apply_blueprint(
                selected_key,
                school=school,
                actor=request.user,
                confirmed=request.POST.get("confirm") == "yes",
                platform_operator=False,
            )
    return render(
        request,
        "platform_runtime/tenant_blueprint_setup.html",
        {
            "school": school,
            "blueprints": blueprints,
            "selected_key": selected_key,
            "preview": preview,
            # Real, per-tenant readiness derived from this preview (applyable /
            # conflict-free / offline proof / live-payment onboarding) — replaces
            # the old hardcoded "72" placeholder so the bar can actually reach 100.
            "blueprint_readiness": blueprint_readiness(preview),
            "result": result,
            "page_marker": "rmc-tenant-blueprint-setup",
            **tenant_blueprint_setup_frame_context(),
        },
    )


@login_required
def tenant_pack_setup(request):
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return HttpResponseForbidden("Tenant school configuration access required.")
    packs = list_packs(tenant_safe_only=True)
    selected_key = (request.POST.get("pack") or request.GET.get("pack") or packs[0]["key"]).strip()
    pack_type = request.POST.get("pack_type") or request.GET.get("pack_type") or next((p["pack_type"] for p in packs if p["key"] == selected_key), "workflow_pack")
    preview = preview_pack(selected_key, pack_type=pack_type, school=school, actor=request.user, platform_operator=False, emit_audit=request.GET.get("preview") == "1")
    change_set = generate_pack_change_set(selected_key, pack_type=pack_type, school=school, actor=request.user, platform_operator=False)
    simulation = simulate_pack(selected_key, pack_type=pack_type, school=school, actor=request.user, platform_operator=False) if request.GET.get("simulate") == "1" else None
    installations = PackInstallation.objects.filter(school=school).order_by("-created_at")[:25]
    result = None
    if request.method == "POST":
        if request.POST.get("installation_id") and request.POST.get("mode") in {"deactivate", "rollback"}:
            installation = get_object_or_404(PackInstallation, pk=request.POST["installation_id"], school=school)
            if request.POST["mode"] == "deactivate":
                result = deactivate_pack_installation(installation, actor=request.user, confirmed=request.POST.get("confirm") == "yes")
            else:
                result = rollback_pack_installation(installation, actor=request.user, confirmed=request.POST.get("confirm") == "yes")
        else:
            if change_set["requires_approval"]:
                change_request = create_change_request(
                    ConfigurationChangeRequest.RequestType.PACK_APPLY,
                    target_key=selected_key,
                    target_type=pack_type,
                    school=school,
                    actor=request.user,
                    reason=request.POST.get("reason", "Tenant school setup request"),
                    platform_operator=False,
                )
                result = {"ok": True, "change_request_id": change_request.pk, "status": change_request.status}
            else:
                result = apply_pack(
                    selected_key,
                    pack_type=pack_type,
                    school=school,
                    actor=request.user,
                    confirmed=request.POST.get("confirm") == "yes",
                    platform_operator=False,
                )
    return render(
        request,
        "platform_runtime/tenant_pack_setup.html",
        {
            "school": school,
            "packs": packs,
            "selected_key": selected_key,
            "selected_pack_type": pack_type,
            "preview": preview,
            # Real per-tenant pack readiness (applyable / conflict-free /
            # dependencies resolved) — replaces the hardcoded "70" placeholder.
            "pack_readiness": pack_readiness(preview),
            "change_set": change_set,
            "simulation": simulation,
            "installations": installations,
            "result": result,
            "page_marker": "rmc-tenant-pack-setup",
            **tenant_pack_setup_frame_context(),
        },
    )


@require_control_plane_access
def change_requests(request):
    from django.core.paginator import Paginator

    from apps.platform_runtime.models import ConfigurationChangeRequest as CCR

    qs = ConfigurationChangeRequest.objects.select_related(
        "school", "requested_by"
    ).order_by("-updated_at", "-pk")
    summary = {
        "pending": qs.filter(
            status__in=(
                CCR.Status.REQUESTED,
                CCR.Status.PENDING_APPROVAL,
                CCR.Status.DRAFT,
            )
        ).count(),
        "scheduled": qs.filter(status=CCR.Status.SCHEDULED).count(),
        "applied": qs.filter(status=CCR.Status.APPLIED).count(),
        "rejected": qs.filter(status=CCR.Status.REJECTED).count(),
        "failed": qs.filter(status=CCR.Status.FAILED).count(),
    }
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    q = request.GET.copy()
    q.pop("page", None)
    return render(
        request,
        "platform_runtime/change_requests.html",
        {
            "change_requests": page_obj.object_list,
            "change_request_summary": summary,
            "page_obj": page_obj,
            "pagination_extra_query": q.urlencode(),
            **change_requests_frame_context(),
        },
    )


@require_control_plane_access
def change_request_detail(request, request_id: int):
    row = get_object_or_404(ConfigurationChangeRequest.objects.select_related("school", "requested_by", "approved_by"), pk=request_id)
    return render(request, "platform_runtime/change_request_detail.html", {"change_request": row})


@require_control_plane_access
def change_request_approve(request, request_id: int):
    row = get_object_or_404(ConfigurationChangeRequest, pk=request_id)
    if request.method == "POST":
        approve_change_request(row, actor=request.user, notes=request.POST.get("notes", ""))
    return redirect("configuration:change_request_detail", request_id=row.pk)


@require_control_plane_access
def change_request_reject(request, request_id: int):
    row = get_object_or_404(ConfigurationChangeRequest, pk=request_id)
    if request.method == "POST":
        reject_change_request(row, actor=request.user, notes=request.POST.get("notes", ""))
    return redirect("configuration:change_request_detail", request_id=row.pk)


@require_control_plane_access
def change_request_schedule(request, request_id: int):
    row = get_object_or_404(ConfigurationChangeRequest, pk=request_id)
    if request.method == "POST":
        scheduled_at = parse_datetime(request.POST.get("scheduled_at", "")) or timezone.now()
        schedule_change_request(row, actor=request.user, scheduled_at=scheduled_at, execution_window=request.POST.get("execution_window", ""))
    return redirect("configuration:change_request_detail", request_id=row.pk)


@require_control_plane_access
def change_request_cancel(request, request_id: int):
    row = get_object_or_404(ConfigurationChangeRequest, pk=request_id)
    if request.method == "POST":
        cancel_change_request(row, actor=request.user, reason=request.POST.get("reason", ""))
    return redirect("configuration:change_request_detail", request_id=row.pk)


@require_control_plane_access
def change_request_apply(request, request_id: int):
    row = get_object_or_404(ConfigurationChangeRequest, pk=request_id)
    if request.method == "POST":
        apply_approved_change_request(row, actor=request.user)
    return redirect("configuration:change_request_detail", request_id=row.pk)
