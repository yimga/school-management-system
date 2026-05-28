"""Parent finance, wallet, and feed views (moved from views.py)."""

import logging
from collections import Counter
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Sum
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

from apps.accounts.decorators import parent_portal_required, role_required
from apps.accounts.models import User
from apps.finance.family_billing_aggregator import (
    aggregate_family_balance,
    propose_payment_split,
)
from apps.finance.models import Invoice, ParentWallet, ReferralReward
from apps.finance.payment_notification_intent import dispatch_payment_received_intent
from apps.finance.regional_payment_profiles import get_normalized_regional_profile
from apps.finance.services import generate_payment_link, pay_invoice_with_wallet
from apps.people.models import StudentGuardian
from apps.platform_runtime.helpers import get_effective_flags

from .services import guardian_student_links, guardian_students
from .tenant_pagination import paginate_for_request, pagination_extra_query


def _parent_finance_access_context(request: HttpRequest):
    """Shared finance gate for parent_finance and pay-all."""
    all_links = guardian_student_links(request.user)
    finance_links = guardian_student_links(request.user, finance_only=True)
    flags = get_effective_flags(request)
    require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))
    finance_link_count = finance_links.count()
    guardian_link_count = all_links.count()
    finance_access_granted = finance_link_count > 0
    can_request_finance_access = (
        require_finance_opt_in and guardian_link_count > finance_link_count
    )
    links = (
        finance_links
        if (finance_access_granted or not require_finance_opt_in)
        else all_links
    )
    blocked = require_finance_opt_in and not finance_access_granted
    return {
        "all_links": all_links,
        "finance_links": finance_links,
        "links": links,
        "require_finance_opt_in": require_finance_opt_in,
        "finance_access_granted": finance_access_granted,
        "can_request_finance_access": can_request_finance_access,
        "guardian_link_count": guardian_link_count,
        "finance_link_count": finance_link_count,
        "finance_blocked": blocked,
        "finance_request_url": reverse("finance:finance_request_access"),
    }


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_finance(request: HttpRequest):
    access = _parent_finance_access_context(request)
    if not access["all_links"].exists():
        messages.info(request, "Link a student first to view finance details.")
        return redirect("portal:link_child")

    require_finance_opt_in = access["require_finance_opt_in"]
    finance_access_granted = access["finance_access_granted"]
    can_request_finance_access = access["can_request_finance_access"]
    finance_request_url = access["finance_request_url"]
    links = access["links"]
    guardian_link_count = access["guardian_link_count"]
    finance_link_count = access["finance_link_count"]

    status_param = ""
    order_param = "-issued_date"
    if access["finance_blocked"]:
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

    family_summary = None
    wallet = None
    pay_all_url = None
    if not access["finance_blocked"] and balance > Decimal("0.00"):
        family_summary = aggregate_family_balance(guardian_user_id=request.user.pk)
        school = getattr(request, "school", None)
        if school:
            wallet = ParentWallet.objects.filter(school=school, user=request.user).first()
        try:
            pay_all_url = reverse("portal:parent_finance_pay_all")
        except NoReverseMatch:
            pay_all_url = None

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
            "family_summary": family_summary,
            "parent_wallet": wallet,
            "pay_all_url": pay_all_url,
        },
    )


@parent_portal_required
@role_required(User.Role.PARENT)
@require_http_methods(["GET", "POST"])
def parent_finance_pay_all(request: HttpRequest):
    """Pay all open family balances (wallet first, else PSP on highest-priority invoice)."""
    access = _parent_finance_access_context(request)
    if not access["all_links"].exists():
        messages.info(request, "Link a student first to view finance details.")
        return redirect("portal:link_child")
    if access["finance_blocked"]:
        messages.warning(request, _("Finance access is required before you can pay."))
        return redirect("portal:parent_finance")

    school = getattr(request, "school", None)
    if not school:
        messages.info(request, _("Select a school to continue."))
        return redirect("portal:parent_dashboard")

    family_summary = aggregate_family_balance(guardian_user_id=request.user.pk)
    if not family_summary.has_open_balance:
        messages.info(request, _("No open balances to pay."))
        return redirect("portal:parent_finance")
    if family_summary.currency_mismatch:
        messages.error(
            request,
            _("Invoices use different currencies. Pay each invoice individually."),
        )
        return redirect("portal:parent_finance")

    amount_due = family_summary.family_total_open_balance
    split = propose_payment_split(
        guardian_user_id=request.user.pk,
        payment_amount=amount_due,
    )
    if split.blocked_reasons:
        messages.error(request, _("Unable to allocate payment: %(reason)s") % {"reason": split.blocked_reasons[0]})
        return redirect("portal:parent_finance")

    wallet = ParentWallet.objects.filter(school=school, user=request.user).first()
    wallet_balance = wallet.balance if wallet else Decimal("0.00")

    if request.method == "POST":
        method = (request.POST.get("payment_method") or "psp").strip().lower()
        if method == "wallet":
            if not wallet or wallet_balance < amount_due:
                messages.error(request, _("Wallet balance is insufficient for pay-all."))
                return redirect("portal:parent_finance_pay_all")
            paid_count = 0
            with transaction.atomic():
                for line in split.lines:
                    invoice = get_object_or_404(
                        Invoice,
                        pk=line.invoice_id,
                        student__school=school,
                    )
                    payment, _wallet = pay_invoice_with_wallet(
                        school,
                        request.user,
                        invoice,
                        amount=line.allocated_amount,
                    )
                    dispatch_payment_received_intent(school=school, payment=payment)
                    paid_count += 1
            messages.success(
                request,
                _("Paid %(count)s invoice(s) from your wallet.") % {"count": paid_count},
            )
            return redirect("portal:parent_finance")

        first_line = split.lines[0] if split.lines else None
        if not first_line:
            messages.error(request, _("No invoices to pay."))
            return redirect("portal:parent_finance")
        invoice = get_object_or_404(
            Invoice,
            pk=first_line.invoice_id,
            student__school=school,
        )
        link = generate_payment_link(invoice)
        if not link or not link.get("url"):
            messages.error(
                request,
                _("Online payment is not configured. Contact the school office."),
            )
            return redirect("portal:parent_finance")
        remaining = max(len(split.lines) - 1, 0)
        if remaining:
            messages.info(
                request,
                _("After this payment, %(n)s more open invoice(s) remain on your account.")
                % {"n": remaining},
            )
        return redirect(link["url"])

    country_code = (
        getattr(school, "country_code", None)
        or getattr(getattr(school, "compliance_profile", None), "country_code", None)
        or ""
    )
    regional_payment_profile = get_normalized_regional_profile(country_code)

    return render(
        request,
        "parent/finance_pay_all_confirm.html",
        {
            "family_summary": family_summary,
            "split": split,
            "amount_due": amount_due,
            "wallet": wallet,
            "wallet_balance": wallet_balance,
            "can_pay_with_wallet": wallet is not None and wallet_balance >= amount_due,
            "regional_payment_profile": regional_payment_profile,
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
