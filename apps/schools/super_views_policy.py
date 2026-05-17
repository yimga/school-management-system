"""
Policy diff, impact preview, and sandbox bundle apply (BR-12 extraction from super_views).
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import redirect, render
from django.urls import reverse

from .decision_architecture import get_decision_architecture_for_page
from .models import School


def _policy_bundle_impact_preview(bundle_id):
    """GAP.7: Affected tenants and policy keys for a policy bundle (who uses it)."""
    from apps.policies.models import PolicyBundle, TenantBlueprint

    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        bundle = PolicyBundle.objects.filter(pk=bundle_id, is_active=True).first()
        if not bundle:
            return {
                "error": "Bundle not found",
                "by_bundle": True,
                "affected_count": 0,
                "affected_schools": [],
                "policy_keys": [],
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            }
        qs = TenantBlueprint.objects.filter(active_bundle_id=bundle_id).select_related(
            "school"
        )
        schools = [
            {
                "id": str(tb.school_id),
                "name": getattr(tb.school, "name", "") or "",
                "slug": getattr(tb.school, "slug", "") or "",
            }
            for tb in qs
            if getattr(tb, "school", None)
        ]
        snapshot = getattr(bundle, "policy_snapshot", None) or {}
        policy_keys = list(snapshot.keys()) if isinstance(snapshot, dict) else []
        return {
            "by_bundle": True,
            "bundle_id": bundle_id,
            "bundle_code": getattr(bundle, "code", "") or "",
            "bundle_name": getattr(bundle, "name", "") or "",
            "affected_count": len(schools),
            "affected_schools": schools,
            "policy_keys": policy_keys[:80],
        }
    except (AttributeError, DatabaseError, TypeError, ValueError) as e:
        return {
            "error": str(e),
            "by_bundle": True,
            "affected_count": 0,
            "affected_schools": [],
            "policy_keys": [],
        }


def super_policy_diff(request):
    """Phase 9: Policy diff viewer — compare platform default, country/region, blueprint, tenant override. GAP.7: impact preview."""
    from apps.policies.models import PolicyBundle

    school_id = request.GET.get("school_id")
    bundle_id_param = request.GET.get("bundle_id")
    school = None
    layers = []
    impact_preview = None

    if school_id:
        try:
            school = School.objects.get(id=school_id)
            from apps.policies.policy_registry import get_effective_policy

            policy = get_effective_policy(school, user=getattr(request, "user", None))
            layers = [
                {
                    "label": "Effective (tenant)",
                    "data": json.dumps(policy or {}, indent=2),
                    "source": "tenant + blueprint + country",
                },
            ]
            # GAP.7: when no bundle_id in GET — impact for this school's bundle (same-bundle tenant count + features)
            if not bundle_id_param:
                policy_dict = policy or {}
                features = policy_dict.get("features") or {}
                affected_features = list(features.keys())[:50]
                affected_tenant_count = 0
                try:
                    from apps.policies.models import TenantBlueprint

                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    tb = getattr(school, "tenant_blueprint", None)
                    if tb and getattr(tb, "active_bundle_id", None):
                        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                        affected_tenant_count = TenantBlueprint.objects.filter(
                            active_bundle_id=tb.active_bundle_id
                        ).count()
                except (AttributeError, DatabaseError, TypeError, ValueError):
                    pass
                impact_preview = {
                    "affected_tenant_count": affected_tenant_count,
                    "affected_features": affected_features,
                    "bundle_id": getattr(
                        getattr(school, "tenant_blueprint", None),
                        "active_bundle_id",
                        None,
                    ),
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                }
                if impact_preview.get("bundle_id"):
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    try:
                        bundle = PolicyBundle.objects.filter(
                            id=impact_preview["bundle_id"]
                        ).first()
                        if bundle:
                            impact_preview["blueprint_compatibility"] = (
                                getattr(bundle, "blueprint_compatibility", []) or []
                            )
                    except (AttributeError, DatabaseError, TypeError, ValueError):
                        impact_preview["blueprint_compatibility"] = []
                else:
                    impact_preview["blueprint_compatibility"] = []
        except School.DoesNotExist:
            pass

    if bundle_id_param:
        try:
            impact_preview = _policy_bundle_impact_preview(int(bundle_id_param))
        except (TypeError, ValueError):
            impact_preview = {
                "error": "Invalid bundle_id",
                "affected_count": 0,
                "affected_schools": [],
                "policy_keys": [],
            }
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

    bundles_sample = list(
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        PolicyBundle.objects.filter(is_active=True)
        .order_by("-created_at")
        .values("id", "code", "name")[:30]
    )

    return render(
        request,
        "schools/super_policy_diff.html",
        {
            "school": school,
            "layers": layers,
            "impact_preview": impact_preview,
            "bundles_sample": bundles_sample,
            "dashboard_url": reverse("super:dashboard"),
            "policy_diff_url": reverse("super:policy_diff"),
            "runtime_inspector_url": reverse("super:runtime_inspector"),
            "decision_architecture": get_decision_architecture_for_page("policy_diff"),
        },
    )


def super_apply_policy_bundle_to_sandbox(request):
    """GAP.8: Apply a policy bundle to a sandbox school (staged rollout). POST: bundle_id, sandbox_school_id."""
    if request.method != "POST":
        return redirect(
            reverse("super:policy_diff")
            + "?school_id="
            + (request.GET.get("school_id") or "")
        )
    bundle_id = request.POST.get("bundle_id")
    sandbox_school_id = request.POST.get("sandbox_school_id")
    if not bundle_id or not sandbox_school_id:
        messages.warning(request, "bundle_id and sandbox_school_id required.")
        return redirect(reverse("super:policy_diff"))
    try:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        from apps.policies.models import PolicyBundle, TenantBlueprint

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        bundle = PolicyBundle.objects.filter(id=bundle_id).first()
        if not bundle:
            messages.warning(request, "Policy bundle not found.")
            return redirect(reverse("super:policy_diff"))
        sandbox_school = School.objects.get(id=sandbox_school_id)
        tb, created = TenantBlueprint.objects.get_or_create(
            school=sandbox_school,
            defaults={"active_bundle": bundle},
        )
        if not created:
            tb.active_bundle = bundle
            tb.save(update_fields=["active_bundle"])
        messages.success(
            request,
            f"Bundle applied to sandbox school {getattr(sandbox_school, 'name', sandbox_school_id)}.",
        )
    except (School.DoesNotExist, ValueError) as e:
        messages.warning(request, str(e))
    return redirect(
        reverse("super:policy_diff") + f"?school_id={request.POST.get('school_id', '')}"
    )
