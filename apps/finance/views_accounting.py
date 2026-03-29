"""
Finance accounting and reconciliation views (§6.15 app-by-app split — subdomain: accounting).
Trial balance, bursar entries, expense vs budget, suspense queue.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from apps.accounts.utils import get_dashboard_context

from .models import LedgerAccount, Payment, SuspensePayment
from .bank_statement_import import BankStatementImportService
from .views_common import _active_profile, _can_access_accounting, FINANCE_SOFT_FAILURES


@staff_member_required(login_url=settings.LOGIN_URL)
def trial_balance(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    start = request.GET.get("start")
    end = request.GET.get("end")

    line_filter = models.Q(
        lines__entry__profile=profile, lines__entry__posted_at__isnull=False
    )
    if start:
        line_filter &= models.Q(lines__entry__entry_date__gte=start)
    if end:
        line_filter &= models.Q(lines__entry__entry_date__lte=end)

    accounts = (
        LedgerAccount.objects.filter(profile=profile, is_active=True)
        .annotate(
            debit_total=Coalesce(
                Sum("lines__debit", filter=line_filter), Decimal("0.00")
            ),
            credit_total=Coalesce(
                Sum("lines__credit", filter=line_filter), Decimal("0.00")
            ),
        )
        .order_by("code")
    )

    accounts = list(accounts)
    total_debit = sum((acc.debit_total for acc in accounts), Decimal("0.00"))
    total_credit = sum((acc.credit_total for acc in accounts), Decimal("0.00"))

    return render(
        request,
        "finance/trial_balance.html",
        {
            "profile": profile,
            "accounts": accounts,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "start": start or "",
            "end": end or "",
            "page_title": "Trial Balance",
            "page_subtitle": f"Compliance: {profile.name} ({profile.country_code})",
            "action_url": reverse("finance:dashboard"),
        },
    )


@login_required
def bursar_entries_report(request: HttpRequest):
    """Read-only report of fee/payment transactions for Accountant. RBAC: accounting.view or ACCOUNTANT."""
    if not _can_access_accounting(request.user):
        return HttpResponseForbidden(
            "You do not have permission to view Bursar entries."
        )
    payments = (
        Payment.objects.select_related("invoice__student", "invoice")
        .filter(status="completed")
        .order_by("-created_at")[:100]
    )
    dashboard_context = get_dashboard_context(request.user, "finance")
    return render(
        request,
        "finance/bursar_entries_report.html",
        {
            "payments": payments,
            "dashboard_context": dashboard_context,
        },
    )


@login_required
def expense_vs_budget(request: HttpRequest):
    """Placeholder: Expense vs approved budget for Accountant. RBAC: accounting.view or ACCOUNTANT."""
    if not _can_access_accounting(request.user):
        return HttpResponseForbidden(
            "You do not have permission to view expense vs budget."
        )
    from .models import Budget

    budgets = Budget.objects.select_related("academic_year").order_by(
        "-academic_year__start_date"
    )[:5]
    dashboard_context = get_dashboard_context(request.user, "finance")
    return render(
        request,
        "finance/expense_vs_budget.html",
        {
            "budgets": budgets,
            "dashboard_context": dashboard_context,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def suspense_queue(request: HttpRequest):
    """Queue of unidentified deposits awaiting allocation."""
    queue = (
        SuspensePayment.objects.select_related(
            "bank_statement_entry",
            "bank_statement_entry__bank_account",
            "suggested_invoice",
            "suggested_student",
            "claimed_student",
        )
        .prefetch_related("allocations__invoice", "allocations__payment")
        .filter(
            status__in=[SuspensePayment.Status.OPEN, SuspensePayment.Status.PARTIAL]
        )
        .order_by("-created_at")
    )
    return render(
        request,
        "finance/suspense_queue.html",
        {
            "queue": queue,
            "page_title": "Suspense Queue",
            "page_subtitle": "Unmatched bank/MoMo deposits that require manual claim and split allocation.",
            "action_url": reverse("finance:payments"),
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
@require_POST
def claim_suspense_payment(request: HttpRequest, suspense_id: int):
    """
    Claim and allocate an unidentified payment.
    Expects JSON in `allocations`, e.g.:
      [{"invoice_id": 12, "amount": "10000"}, {"invoice_id": 13, "amount": "5000"}]
    """
    suspense = get_object_or_404(SuspensePayment, pk=suspense_id)
    raw_allocations = request.POST.get("allocations", "").strip()
    notes = request.POST.get("notes", "").strip()
    if not raw_allocations:
        messages.error(request, "Provide allocation JSON before submitting.")
        return redirect("finance:suspense_queue")

    try:
        allocations = json.loads(raw_allocations)
    except json.JSONDecodeError:
        messages.error(request, "Allocation payload must be valid JSON.")
        return redirect("finance:suspense_queue")

    try:
        result = BankStatementImportService().claim_suspense_payment(
            suspense_payment=suspense,
            allocations=allocations,
            claimed_by=request.user,
            notes=notes,
        )
    except FINANCE_SOFT_FAILURES as exc:
        messages.error(request, f"Failed to allocate suspense payment: {exc}")
        return redirect("finance:suspense_queue")

    messages.success(
        request,
        f"Suspense #{suspense.id} updated to {result['status']}. Remaining: {result['remaining']}.",
    )
    return redirect("finance:suspense_queue")
