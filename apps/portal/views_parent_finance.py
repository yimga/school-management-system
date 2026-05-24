"""Parent finance, wallet, and feed views (moved from views.py)."""

import logging
from collections import Counter
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Sum
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

from apps.accounts.decorators import parent_portal_required, role_required
from apps.accounts.models import User
from apps.finance.models import Invoice, ReferralReward
from apps.finance.services import generate_payment_link
from apps.people.models import StudentGuardian
from apps.platform_runtime.helpers import get_effective_flags

from .services import guardian_student_links, guardian_students
from .tenant_pagination import paginate_for_request, pagination_extra_query


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_finance(request: HttpRequest):
    all_links = guardian_student_links(request.user)
    finance_links = guardian_student_links(request.user, finance_only=True)

    if not all_links.exists():
        messages.info(request, "Link a student first to view finance details.")
        return redirect("portal:link_child")

    flags = get_effective_flags(request)
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    finance_link_count = finance_links.count()
    guardian_link_count = all_links.count()
    finance_access_granted = finance_link_count > 0
    can_request_finance_access = (
        require_finance_opt_in and guardian_link_count > finance_link_count
    )
    finance_request_url = reverse("finance:finance_request_access")
    links = (
        finance_links
        if (finance_access_granted or not require_finance_opt_in)
        else all_links
    )

    status_param = ""
    order_param = "-issued_date"
    if require_finance_opt_in and not finance_access_granted:
        students = []
        invoices_qs = Invoice.objects.none()
        aggregates = {"total_due": Decimal("0.00"), "balance": Decimal("0.00")}
        overdue_count = 0
    else:
        students = guardian_students(request.user, finance_only=True)
        invoices_qs = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Invoice.objects.filter(student__in=students)
            .exclude(status=Invoice.Status.DRAFT)
            .select_related("student", "academic_year")
            .prefetch_related("payments")
        )
        aggregates = invoices_qs.aggregate(
            total_due=Sum("total_amount"),
            balance=Sum("balance_amount"),
        )
        overdue_count = invoices_qs.filter(status=Invoice.Status.OVERDUE).count()

        # Optional sort/filter for list (data-agnostic; hero stats stay on full set)
        status_param = (request.GET.get("status") or "").strip()
        if status_param and status_param in [c[0] for c in Invoice.Status.choices]:
            invoices_qs = invoices_qs.filter(status=status_param)
        _order_map = {
            "issued_date": "issued_date",
            "-issued_date": "-issued_date",
            "due_date": "due_date",
            "-due_date": "-due_date",
            "total_amount": "total_amount",
            "-total_amount": "-total_amount",
        }
        order_param = (request.GET.get("order") or "").strip()
        order_by = _order_map.get(order_param, "-issued_date")
        invoices_qs = invoices_qs.order_by(order_by)

    total_due = aggregates.get("total_due") or Decimal("0.00")
    balance = aggregates.get("balance") or Decimal("0.00")
    paid = total_due - balance
    int((paid / total_due) * 100) if total_due else 0
    bool(students)

    page_obj = paginate_for_request(request, invoices_qs, per_page=20)

    payment_method_counts = Counter()
    invoice_rows = []
    reminders = []
    for inv in page_obj.object_list:
        link = generate_payment_link(inv)
        payments = list(inv.payments.all())
        receipt = payments[0] if payments else None
        if payments:
            for payment in payments:
                payment_method_counts[payment.get_method_display()] += 1
        invoice_rows.append(
            {
                "invoice": inv,
                "payment_link": link,
                "receipt_url": reverse(
                    "finance:invoice_receipt", args=(inv.id, receipt.id)
                )
                if receipt
                else None,
                "preferred_method": inv.get_preferred_payment_method_display() or "Any",
                "attachment_url": inv.attachment.url if inv.attachment else None,
                "recent_payment": receipt,
            }
        )
        reminder = getattr(inv, "reminder", None)
        if reminder and reminder.is_active:
            reminders.append(
                {
                    "invoice": inv,
                    "reminder": reminder,
                    "payment_link": link,
                }
            )

    referral_qs = ReferralReward.objects.filter(guardian__guardian_user=request.user)
    referral_total = referral_qs.filter(
        status=ReferralReward.Status.APPROVED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    referral_pending = referral_qs.filter(status=ReferralReward.Status.PENDING).count()
    hero = {
        "title": "Finances",
        "subtitle": "Balances, invoices, and secure payment links",
        "stats": [
            {"label": "Total due", "value": total_due},
            {"label": "Paid", "value": paid},
            {"label": "Outstanding", "value": balance},
            {"label": "Overdue", "value": overdue_count},
            {"label": "Reminders", "value": len(reminders), "meta": "Queued notices"},
            {
                "label": "Referral credits",
                "value": f"{referral_total:.2f}",
                "meta": "Approved bonuses",
            },
        ],
    }

    attachment_count = invoices_qs.filter(attachment__isnull=False).count()
    payment_method_summary = [
        {"method": method, "count": count}
        for method, count in payment_method_counts.most_common()
    ]

    return render(
        request,
        "parent/finance.html",
        {
            "links": links,
            "hero": hero,
            "invoice_rows": invoice_rows,
            "total_due": total_due,
            "balance": balance,
            "paid": paid,
            "overdue_count": overdue_count,
            "reminders": reminders,
            "attachment_count": attachment_count,
            "payment_method_summary": payment_method_summary,
            "referral_total": referral_total,
            "referral_pending": referral_pending,
            "finance_access_required": require_finance_opt_in,
            "finance_access_granted": finance_access_granted,
            "guardian_link_count": guardian_link_count,
            "finance_guardian_count": finance_link_count,
            "can_request_finance_access": can_request_finance_access,
            "finance_request_url": finance_request_url,
            "invoice_statuses": Invoice.Status.choices,
            "selected_status": status_param,
            "order_options": [
                ("-issued_date", _("Date (newest first)")),
                ("issued_date", _("Date (oldest first)")),
                ("-due_date", _("Due date (latest first)")),
                ("due_date", _("Due date (earliest first)")),
                ("-total_amount", _("Amount (high to low)")),
                ("total_amount", _("Amount (low to high)")),
            ],
            "selected_order": order_param,
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query(request),
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_wallet(request: HttpRequest):
    """Plan V: Parent wallet rich UI — balance, history, top-up link."""
    from apps.finance.models import ParentWallet, WalletTransaction

    school = getattr(request, "school", None)
    if not school:
        messages.info(request, "Select a school to view your wallet.")
        return redirect("portal:parent_dashboard")
    wallet = ParentWallet.objects.filter(school=school, user=request.user).first()
    transactions = []
    if wallet:
        transactions = list(
            WalletTransaction.objects.filter(wallet=wallet).order_by("-created_at")[:50]
        )
    try:
        top_up_url = reverse("api_v1:finance-wallet-top-up")
    except (NoReverseMatch, ImproperlyConfigured) as e:
        logger.debug(
            "reverse(api_v1:finance-wallet-top-up) failed, using fallback: %s", e
        )
        top_up_url = "/api/v1/finance/wallet/top-up"
    return render(
        request,
        "parent/wallet.html",
        {
            "wallet": wallet,
            "transactions": transactions,
            "top_up_url": top_up_url,
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_feed(request: HttpRequest):
    """Plan VI: Social feed for parents — announcements, achievements, interventions for their children/school."""
    from apps.communication.models import FeedItem

    school = getattr(request, "school", None)
    if not school:
        messages.info(request, "Select a school to view the feed.")
        return redirect("portal:parent_dashboard")
    student_ids = set(
        StudentGuardian.objects.filter(guardian_user=request.user).values_list(
            "student_id", flat=True
        )
    )
    qs = (
        FeedItem.objects.filter(school=school)
        .select_related("student", "created_by")
        .order_by("-created_at")[:100]
    )
    items = [i for i in qs if i.student_id is None or i.student_id in student_ids]
    return render(request, "parent/feed.html", {"feed_items": items})
