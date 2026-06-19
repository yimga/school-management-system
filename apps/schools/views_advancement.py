"""
Tenant advancement (wedge 5): donor and gift CRUD for staff on school subdomain.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import DatabaseError, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.platform_runtime.structured_logging import log_view_exception
from apps.schools.mixins import require_school
from services.post_delete_navigation import (
    mutation_return_url,
    redirect_after_detail_mutation,
)

from .models import AdvancementDonor, AdvancementGift


def _staff_only(u):
    return bool(u and u.is_authenticated and u.is_staff)


@login_required
@user_passes_test(_staff_only)
@require_school
@require_http_methods(["GET", "POST"])
def advancement_donor_list(request):
    school = request.school
    q = (request.GET.get("q") or "").strip()
    qs = AdvancementDonor.objects.filter(school=school).order_by("-updated_at")
    if q:
        qs = qs.filter(display_name__icontains=q) | qs.filter(email__icontains=q)
    paginator = Paginator(qs, 25)
    page = request.GET.get("page")
    try:
        donors = paginator.page(page)
    except PageNotAnInteger:
        donors = paginator.page(1)
    except EmptyPage:
        donors = paginator.page(paginator.num_pages)
    return render(
        request,
        "schools/advancement_donor_list.html",
        {
            "donors": donors,
            "search": q,
            "dashboard_url": reverse("accounts:backend_dashboard"),
            "create_url": reverse("accounts:advancement_donor_create"),
        },
    )


@login_required
@user_passes_test(_staff_only)
@require_school
@require_http_methods(["GET", "POST"])
def advancement_donor_create(request):
    school = request.school
    if request.method == "POST":
        name = (request.POST.get("display_name") or "").strip()
        if not name:
            messages.error(request, "Display name is required.")
        else:
            try:
                AdvancementDonor.objects.create(
                    school=school,
                    display_name=name[:200],
                    email=(request.POST.get("email") or "").strip()[:254],
                    external_ref=(request.POST.get("external_ref") or "").strip()[:120],
                    notes=(request.POST.get("notes") or "").strip()[:4000],
                )
                messages.success(request, "Donor created.")
                return redirect("accounts:advancement_donor_list")
            except (IntegrityError, DatabaseError, ValueError, TypeError):
                log_view_exception(
                    request,
                    "advancement_donor_create failed",
                    extra={"view": "advancement_donor_create", "school_id": str(school.pk)},
                )
                messages.error(request, "Could not save donor.")
    return render(
        request,
        "schools/advancement_donor_form.html",
        {
            "title": "Add donor",
            "submit_label": "Create",
            "dashboard_url": reverse("accounts:backend_dashboard"),
            "list_url": reverse("accounts:advancement_donor_list"),
            "donor": None,
        },
    )


@login_required
@user_passes_test(_staff_only)
@require_school
@require_http_methods(["GET", "POST"])
def advancement_donor_edit(request, donor_id):
    school = request.school
    donor = get_object_or_404(AdvancementDonor, pk=donor_id, school=school)
    if request.method == "POST":
        name = (request.POST.get("display_name") or "").strip()
        if not name:
            messages.error(request, "Display name is required.")
        else:
            try:
                donor.display_name = name[:200]
                donor.email = (request.POST.get("email") or "").strip()[:254]
                donor.external_ref = (request.POST.get("external_ref") or "").strip()[:120]
                donor.notes = (request.POST.get("notes") or "").strip()[:4000]
                donor.save()
                messages.success(request, "Donor updated.")
                return redirect("accounts:advancement_donor_detail", donor_id=donor.pk)
            except (IntegrityError, DatabaseError, ValueError, TypeError) as e:
                log_view_exception(
                    request,
                    e,
                    extra={
                        "view": "advancement_donor_edit",
                        "donor_id": str(donor.pk),
                        "school_id": str(school.pk),
                    },
                )
                messages.error(request, "Could not save donor.")
    return render(
        request,
        "schools/advancement_donor_form.html",
        {
            "title": "Edit donor",
            "submit_label": "Save",
            "dashboard_url": reverse("accounts:backend_dashboard"),
            "list_url": reverse("accounts:advancement_donor_list"),
            "donor": donor,
        },
    )


@login_required
@user_passes_test(_staff_only)
@require_school
@require_http_methods(["GET", "POST"])
def advancement_donor_detail(request, donor_id):
    school = request.school
    donor = get_object_or_404(
        AdvancementDonor.objects.prefetch_related("gifts"), pk=donor_id, school=school
    )
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "add_gift":
            amt = (request.POST.get("amount") or "").strip()
            try:
                d = Decimal(amt)
            except (InvalidOperation, TypeError, ValueError):
                d = None
            if d is None or d <= 0:
                messages.error(request, "Enter a positive amount.")
            else:
                try:
                    gift = AdvancementGift.objects.create(
                        donor=donor,
                        amount=d,
                        currency=(request.POST.get("currency") or "USD").strip()[:3]
                        or "USD",
                        received_at=timezone.now().date(),
                        campaign_name=(request.POST.get("campaign_name") or "").strip()[
                            :120
                        ],
                        notes=(request.POST.get("gift_notes") or "").strip()[:500],
                    )
                    award_source_id = (
                        request.POST.get("award_source_id") or ""
                    ).strip()
                    if award_source_id:
                        from .advancement_services import designate_and_credit_gift

                        res = designate_and_credit_gift(
                            gift, award_source_id, user_id=request.user.pk
                        )
                        if res and not res.get("ok"):
                            messages.warning(
                                request,
                                f"Gift recorded, but not credited to fund: {res.get('error')}",
                            )
                        elif res and res.get("ok"):
                            messages.success(
                                request, "Gift recorded and credited to fund."
                            )
                        else:
                            messages.success(request, "Gift recorded.")
                    else:
                        messages.success(request, "Gift recorded.")
                    return redirect(
                        "accounts:advancement_donor_detail", donor_id=donor.pk
                    )
                except (IntegrityError, DatabaseError, ValueError, TypeError):
                    log_view_exception(
                        request,
                        "advancement add_gift failed",
                        extra={
                            "view": "advancement_donor_detail",
                            "donor_id": str(donor.pk),
                        },
                    )
                    messages.error(request, "Could not record gift.")
    gifts = list(donor.gifts.select_related("award_source").all()[:100])
    award_sources = []
    try:
        from apps.finance.models import AwardSource

        award_sources = list(
            AwardSource.objects.filter(school=school, is_active=True).order_by("name")
        )
    except (ImportError, DatabaseError) as e:
        logging.getLogger(__name__).debug(
            "advancement_donor_detail award_sources skip: %s", e
        )
    list_url = reverse("accounts:advancement_donor_list")
    detail_url = reverse("accounts:advancement_donor_detail", args=[donor.pk])
    return_url = mutation_return_url(request, detail_url, list_url=list_url)
    return render(
        request,
        "schools/advancement_donor_detail.html",
        {
            "donor": donor,
            "gifts": gifts,
            "award_sources": award_sources,
            "dashboard_url": reverse("accounts:backend_dashboard"),
            "edit_url": reverse("accounts:advancement_donor_edit", args=[donor.pk]),
            "list_url": list_url,
            "return_url": return_url,
        },
    )


@login_required
@user_passes_test(_staff_only)
@require_school
@require_POST
def advancement_gift_delete(request, gift_id):
    school = request.school
    gift = get_object_or_404(
        AdvancementGift.objects.select_related("donor"),
        pk=gift_id,
        donor__school=school,
    )
    donor_id = gift.donor_id
    gift.delete()
    messages.success(request, "Gift removed.")
    detail_url = reverse("accounts:advancement_donor_detail", args=[donor_id])
    return redirect_after_detail_mutation(request, detail_url)
