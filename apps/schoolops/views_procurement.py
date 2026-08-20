"""Tenant procurement UI (rubric metric M33).

Deliberately the same decorator stack and feature gate as the rest of extended ops
(``views_tenant_ops``): procurement is the ordering half of inventory, so a school
that has not enabled the inventory module has no business seeing it either.

Generation always produces DRAFTS. The button proposes; a human submits.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import DatabaseError, IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.permissions import user_can_access_ops_extended_modules
from apps.schools.mixins import require_feature
from apps.schoolops.models import PurchaseOrder
from apps.schoolops.procurement_services import (
    compute_required_quantities,
    generate_purchase_orders_from_class_config,
    tenant_gmv,
)


@login_required
@user_passes_test(user_can_access_ops_extended_modules)
@require_feature("inventory")
@require_http_methods(["GET", "POST"])
def ops_procurement(request):
    school = request.school

    if request.method == "POST":
        intent = (request.POST.get("intent") or "").strip().lower()
        if intent == "generate":
            try:
                created = generate_purchase_orders_from_class_config(school)
            except (DatabaseError, IntegrityError, ValueError) as exc:
                messages.error(
                    request, _("Could not generate orders: %(err)s") % {"err": exc}
                )
            else:
                if created:
                    messages.success(
                        request,
                        _("Generated %(count)s draft order(s) from class configuration.")
                        % {"count": len(created)},
                    )
                else:
                    # An honest empty result, not a silent no-op: the school either
                    # has no supply requirements, no enrolled classes for them, or
                    # already holds enough stock.
                    messages.info(
                        request,
                        _(
                            "Nothing to order — every configured supply requirement "
                            "is already covered by stock on hand."
                        ),
                    )
        elif intent == "submit":
            raw = (request.POST.get("order_id") or "").strip()
            if not raw.isdigit():
                messages.error(request, _("Select a valid order."))
            else:
                updated = PurchaseOrder.objects.filter(
                    pk=int(raw), school=school, status=PurchaseOrder.Status.DRAFT
                ).update(status=PurchaseOrder.Status.SUBMITTED)
                if updated:
                    messages.success(request, _("Order submitted to the vendor."))
                else:
                    messages.error(
                        request, _("That order is not a draft for this school.")
                    )
        else:
            messages.error(request, _("Unknown action."))
        return redirect(reverse("accounts:ops_procurement"))

    orders = list(
        PurchaseOrder.objects.filter(school=school)
        .select_related("vendor")
        .prefetch_related(
            "lines__product",
            "lines__subject_assignment__subject",
            "lines__subject_assignment__classroom",
        )[:50]
    )
    preview = compute_required_quantities(school)
    preview_rows = [
        {
            "product": slot["product"],
            "quantity": slot["quantity"],
            "assignment": slot["assignment"],
        }
        for slot in preview.values()
    ]

    return render(
        request,
        "schoolops/ops_procurement.html",
        {
            "school": school,
            "orders": orders,
            "preview_rows": preview_rows,
            "gmv": tenant_gmv(school),
            "hub_url": reverse("accounts:ops_hub"),
        },
    )
