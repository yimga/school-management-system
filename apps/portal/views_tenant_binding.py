"""v4.00.52 — Tenant-binding operator UI (Wedge 45 item).

Surfaces the v4.00.51 ``UserTenantBinding`` rows to staff:

  * ``GET /portal/super/sso/bindings/`` — index, filterable by
    ``?source=oidc|saml|manual``, ``?provider=<slug>``, ``?school=<id>``.
  * ``POST /portal/super/sso/bindings/reassign/`` — reassign a binding to a
    different school (audited via existing ``updated_at`` field; the bind
    row's ``source`` flips to ``manual`` to mark operator override).
"""
from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@staff_member_required
@require_http_methods(["GET"])
def tenant_bindings_index(request: HttpRequest):
    from apps.accounts.models_sso import UserTenantBinding

    qs = UserTenantBinding.objects.select_related("user", "school").order_by("-updated_at")  # tenant-isolation-allow: operator-console-platform-scope-staff-required
    source = (request.GET.get("source") or "").strip()
    provider = (request.GET.get("provider") or "").strip()
    school = (request.GET.get("school") or "").strip()
    if source:
        qs = qs.filter(source=source)
    if provider:
        qs = qs.filter(provider=provider)
    if school:
        qs = qs.filter(school_id=school)
    rows = list(qs[:500])

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "rows": [
                {
                    "user_id": r.user_id,
                    "username": r.user.get_username() if r.user else "",
                    "school_id": str(r.school_id),
                    "school_name": getattr(r.school, "name", ""),
                    "source": r.source,
                    "provider": r.provider,
                    "subject": r.subject,
                    "issuer": r.issuer,
                    "is_primary": r.is_primary,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                }
                for r in rows
            ],
            "filter": {"source": source, "provider": provider, "school": school},
        })
    return render(request, "super/sso/bindings_index.html", {
        "rows": rows,
        "filter_source": source,
        "filter_provider": provider,
        "filter_school": school,
    })


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def tenant_binding_reassign(request: HttpRequest):
    """Point a user's PRIMARY tenant binding at a school (multi-binding aware).

    Body: ``user`` (User.pk), ``school`` (target School.pk). Upserts the
    ``(user, school)`` binding, promotes it to primary (demoting any other
    primary in the same transaction), and flips ``source`` to ``manual`` to
    mark operator override; preserves ``provider`` + ``subject`` + ``issuer``
    on other bindings for audit. Other-school bindings are never deleted.
    """
    user_id = (request.POST.get("user") or "").strip()
    school_id = (request.POST.get("school") or "").strip()
    if not user_id or not school_id:
        return JsonResponse({"error": "missing_user_or_school"}, status=400)

    from apps.accounts.models_sso import UserTenantBinding
    from apps.schools.models import School
    from django.contrib.auth import get_user_model
    from django.db import transaction

    UserModel = get_user_model()
    user = UserModel.objects.filter(pk=user_id).first()  # tenant-isolation-allow: operator-binding-resolve-user-by-pk-staff-required
    if user is None:
        return JsonResponse({"error": "user_not_found"}, status=404)
    school = School.objects.filter(pk=school_id).first()  # tenant-isolation-allow: operator-binding-resolve-school-by-pk-staff-required
    if school is None:
        return JsonResponse({"error": "school_not_found"}, status=404)

    with transaction.atomic():
        # Demote first — the partial unique constraint (one primary per user)
        # would reject promoting the target while another primary exists.
        UserTenantBinding.objects.filter(  # tenant-isolation-allow: operator-binding-demote-old-primary-staff-required
            user_id=user.pk, is_primary=True
        ).exclude(school=school).update(is_primary=False)
        row, created = UserTenantBinding.objects.get_or_create(  # tenant-isolation-allow: operator-binding-upsert-keyed-by-user-and-school
            user_id=user.pk,
            school=school,
            defaults={"source": "manual", "is_primary": True},
        )
        if not created and (not row.is_primary or row.source != "manual"):
            row.is_primary = True
            row.source = "manual"
            row.save(update_fields=["is_primary", "source", "updated_at"])

    payload = {
        "success": True,
        "action": "created" if created else "reassigned",
        "user_id": user.pk,
        "school_id": str(school.pk),
        "source": row.source,
        "is_primary": row.is_primary,
    }
    if (request.GET.get("format") or "").lower() == "json" or (request.POST.get("format") or "").lower() == "json":
        return JsonResponse(payload)
    return HttpResponseRedirect(reverse("portal:tenant_bindings_index"))
