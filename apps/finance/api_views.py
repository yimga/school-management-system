"""
Finance API Views
Invoice, Payment, and Financial Analytics endpoints
"""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.core.cache import cache
from django.db.models import Sum, Count
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.finance.json_decimal import amount_str
from apps.finance.models import Invoice, Payment, Notification
from apps.finance.services import pay_invoice_with_wallet
from apps.observability.tracing import trace_view
from apps.api.serializers import InvoiceSerializer, PaymentSerializer
from apps.api.permissions import IsAdminUser
from apps.accounts.drf_rebac import RebacPermission
from apps.accounts.rebac import enforce_permission_token
from apps.schools.models import School


def _money_aggregate_rows(rows):
    """Serialize ORM annotate totals as precision-preserving strings."""
    out = []
    for row in rows:
        item = dict(row)
        if "total" in item:
            item["total"] = amount_str(item["total"])
        out.append(item)
    return out


FINANCE_WRITE_ROLES = {
    "ADMIN",
    "BURSAR",
    "ACCOUNTANT",
    "FINANCE_STAFF",
    "LEADERSHIP",
    "PRINCIPAL",
}


class FinanceCursorPagination(CursorPagination):
    ordering = "-created_at"


def _can_write_finance(user, school=None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    if school is not None:
        return enforce_permission_token(user, "finance.manage", school=school)
    return (getattr(user, "role", "") or "").upper() in FINANCE_WRITE_ROLES


def _can_read_finance(user, school=None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    if school is not None:
        return enforce_permission_token(user, "finance.view", school=school)
    return (getattr(user, "role", "") or "").upper() in FINANCE_WRITE_ROLES


def _request_school(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    school_id = getattr(request, "session", {}).get("school_id")
    if not school_id:
        return None
    return School.objects.filter(pk=school_id, is_active=True).first()


def _parse_client_updated_at(value):
    """Parse X-Client-Updated-At header to timezone-aware datetime for comparison."""
    if not value or not value.strip():
        return None
    dt = parse_datetime(value.strip())
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _check_offline_conflict(instance, request, method_name="update"):
    """
    If request has X-Client-Updated-At, compare with instance.updated_at (UTC).
    Return Response(409) if client timestamp is older than server; else return None.
    """
    raw = request.headers.get("X-Client-Updated-At") or request.META.get(
        "HTTP_X_CLIENT_UPDATED_AT"
    )
    if not raw:
        return None
    client_dt = _parse_client_updated_at(raw)
    if client_dt is None:
        return None
    server_dt = getattr(instance, "updated_at", None)
    if server_dt is None:
        return None
    if timezone.is_naive(server_dt):
        server_dt = timezone.make_aware(server_dt)
    if client_dt < server_dt:
        return Response(
            {"error": "conflict", "server_updated_at": server_dt.isoformat()},
            status=status.HTTP_409_CONFLICT,
        )
    return None


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    Invoice management API

    List, create, retrieve, update invoices
    Filter by status, date range, student
    """

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = FinanceCursorPagination

    def get_permissions(self):
        if self.action in ("list", "retrieve", "summary"):
            return [IsAuthenticated(), RebacPermission("finance.view")]
        return [IsAuthenticated(), RebacPermission("finance.manage")]
    filterset_fields = ["status", "student", "issued_date", "due_date"]
    ordering_fields = ["issued_date", "due_date", "total_amount", "created_at"]
    ordering = ["-issued_date", "-id"]

    def get_queryset(self):
        user = self.request.user
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        base = Invoice.objects.all().select_related("student__user")
        school = _request_school(self.request)
        if school is None:
            return base.none()
        from apps.tenancy.queryset_boundary import verify_explicit_school_filter

        verify_explicit_school_filter(base, school=school)
        base = base.filter(school=school)

        if user.is_staff or user.role in ["ADMIN", "BURSAR", "LEADERSHIP", "HOD"]:
            return base

        from apps.people.models import StudentProfile
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return base.filter(student=student_profile)

        from apps.accounts.permissions import guardian_finance_student_ids

        guardian_children = guardian_finance_student_ids(user)

        return base.filter(student_id__in=guardian_children)

    def list(self, request, *args, **kwargs):
        school = _request_school(request)
        if school and not _can_read_finance(request.user, school):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        """
        List invoices with advanced filtering

        Query Parameters:
        - status: DRAFT, ISSUED, PARTIAL, PAID, OVERDUE, VOID
        - from_date: YYYY-MM-DD
        - to_date: YYYY-MM-DD
        - student_id: specific student
        - limit: results per page
        """
        queryset = self.get_queryset()

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        if from_date and to_date:
            queryset = queryset.filter(
                issued_date__gte=from_date, issued_date__lte=to_date
            )

        student_id = request.query_params.get("student_id")
        if student_id:
            queryset = queryset.filter(student_id=student_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @trace_view("finance.invoice.create")
    def create(self, request, *args, **kwargs):
        """Create new invoice"""
        from apps.lifecycle.wind_down_guards import wind_down_drf_block

        blocked = wind_down_drf_block(request)
        if blocked is not None:
            return blocked
        school = _request_school(request)
        if not _can_write_finance(request.user, school):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        if school is None:
            return Response(
                {"error": "School context required"}, status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.validated_data.get("student")
        if student and student.school_id != school.id:
            return Response(
                {"error": "Cross-tenant student reference is not allowed"},
                status=status.HTTP_403_FORBIDDEN,
            )
        invoice = serializer.save(
            school=school,
            created_by=request.user,
            updated_by=request.user,
        )
        output = self.get_serializer(invoice)
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        conflict = _check_offline_conflict(instance, request)
        if conflict is not None:
            return conflict
        return super().update(request, *args, partial=partial, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        """Mark invoice as fully paid"""
        from apps.lifecycle.wind_down_guards import wind_down_drf_block

        blocked = wind_down_drf_block(request)
        if blocked is not None:
            return blocked
        school = _request_school(request)
        if not _can_write_finance(request.user, school):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        invoice = self.get_object()
        invoice.status = Invoice.Status.PAID
        invoice.balance_amount = 0
        invoice.save(update_fields=["status", "balance_amount", "updated_at"])

        Notification.objects.create(
            title="Invoice Marked Paid",
            message=f"Invoice {invoice.id} has been marked as paid",
            recipient=request.user,
            created_by=request.user,
        )

        return Response(
            {
                "status": "success",
                "invoice_id": invoice.id,
                "marked_at": timezone.now().isoformat(),
            }
        )

    @action(detail=True, methods=["post"])
    def pay_with_wallet(self, request, pk=None):
        """
        Pay (part of) this invoice using the current user's parent wallet.
        Body: optional {"amount": "100.00"} (default: full outstanding balance).
        """
        school = _request_school(request)
        if school is None:
            return Response(
                {"error": "School context required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice = self.get_object()
        if getattr(invoice, "school_id", None) and invoice.school_id != school.id:
            return Response(
                {"error": "Invoice does not belong to this school"},
                status=status.HTTP_403_FORBIDDEN,
            )
        amount_raw = request.data.get("amount")
        amount = None
        if amount_raw is not None:
            try:
                amount = str(amount_raw).strip()
            except (TypeError, AttributeError):
                amount = None
        try:
            payment, wallet = pay_invoice_with_wallet(
                school=school,
                user=request.user,
                invoice=invoice,
                amount=amount,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.refresh_from_db()
        from apps.api.serializers import PaymentSerializer as PaySer

        return Response(
            {
                "payment": PaySer(payment).data,
                "wallet_balance_after": str(wallet.balance),
                "invoice_balance_after": str(invoice.computed_balance),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get invoice summary statistics"""
        queryset = self.get_queryset()

        total_amount = queryset.aggregate(Sum("total_amount"))["total_amount__sum"] or 0
        paid_amount = (
            queryset.filter(status=Invoice.Status.PAID).aggregate(Sum("total_amount"))[
                "total_amount__sum"
            ]
            or 0
        )
        pending_amount = (
            queryset.filter(
                status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL]
            ).aggregate(Sum("balance_amount"))["balance_amount__sum"]
            or 0
        )
        overdue_amount = (
            queryset.filter(status=Invoice.Status.OVERDUE).aggregate(
                Sum("balance_amount")
            )["balance_amount__sum"]
            or 0
        )

        count_by_status = queryset.values("status").annotate(count=Count("id"))

        from apps.finance.json_decimal import amount_str
        from decimal import Decimal

        total_dec = Decimal(str(total_amount))
        paid_dec = Decimal(str(paid_amount))
        return Response(
            {
                "total_amount": amount_str(total_dec),
                "paid_amount": amount_str(paid_dec),
                "pending_amount": amount_str(pending_amount),
                "overdue_amount": amount_str(overdue_amount),
                "amount_wire_format": "decimal_string",
                "payment_rate": round((paid_dec / total_dec * 100), 1)
                if total_dec > 0
                else 0,
                "by_status": list(count_by_status),
            }
        )


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Payment recording and tracking API

    Create and retrieve payment records
    Filter by invoice, payment method, date
    """

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = FinanceCursorPagination

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), RebacPermission("finance.view")]
        return [IsAuthenticated(), RebacPermission("finance.manage")]
    ordering_fields = ["created_at", "amount", "paid_at"]
    ordering = ["-paid_at"]

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    def get_queryset(self):
        user = self.request.user
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        base = Payment.objects.all().select_related("invoice__student__user")
        school = _request_school(self.request)
        if school is None:
            return base.none()
        from apps.tenancy.queryset_boundary import verify_explicit_school_filter

        verify_explicit_school_filter(base, school=school)
        base = base.filter(school=school)

        if _can_write_finance(user, school):
            return base
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

        from apps.people.models import StudentProfile
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return base.filter(invoice__student=student_profile)

        from apps.accounts.permissions import guardian_finance_student_ids

        guardian_children = guardian_finance_student_ids(user)

        return base.filter(invoice__student_id__in=guardian_children)

    @trace_view("finance.payment.record")
    def create(self, request, *args, **kwargs):
        """
        Record a new payment.
        Supports X-Idempotency-Key: same key within 24h returns the same response (offline replay dedup).
        Request Body: { "invoice": 1, "amount": 25000.00, "method": "MTN_MOMO", "reference": "REF123456", "paid_at": "..." }
        """
        from apps.lifecycle.wind_down_guards import wind_down_drf_block

        blocked = wind_down_drf_block(request)
        if blocked is not None:
            return blocked
        school = _request_school(request)
        if not _can_write_finance(request.user, school):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        if school is None:
            return Response(
                {"error": "School context required"}, status=status.HTTP_400_BAD_REQUEST
            )
        idem_key = (
            request.headers.get("X-Idempotency-Key")
            or request.META.get("HTTP_X_IDEMPOTENCY_KEY")
            or ""
        ).strip()[:64]
        if idem_key:
            from apps.siteconfig.cache_utils import tenant_cache_key

            cache_key = tenant_cache_key(
                f"offline_payment_idempotency:{request.user.pk}:{idem_key}", request
            )
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(
                    cached.get("data"), status=cached.get("status", status.HTTP_200_OK)
                )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.validated_data.get("invoice")
        student = serializer.validated_data.get("student")
        if invoice:
            invoice_school_id = getattr(invoice, "school_id", None)
            if invoice_school_id and invoice_school_id != school.id:
                return Response(
                    {"error": "Cross-tenant invoice reference is not allowed"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if (
                invoice.student_id
                and getattr(invoice.student, "school_id", None) != school.id
            ):
                return Response(
                    {"error": "Cross-tenant invoice student reference is not allowed"},
                    status=status.HTTP_403_FORBIDDEN,
                )
        if student and student.school_id != school.id:
            return Response(
                {"error": "Cross-tenant student reference is not allowed"},
                status=status.HTTP_403_FORBIDDEN,
            )

        payment = serializer.save(school=school, created_by=request.user)

        invoice = payment.invoice
        if invoice:
            invoice.reconcile_balance()
            current_balance = invoice.computed_balance
            if current_balance <= 0:
                invoice.status = Invoice.Status.PAID
            elif current_balance < invoice.total_amount:
                invoice.status = Invoice.Status.PARTIAL
            else:
                invoice.status = Invoice.Status.ISSUED
            invoice.balance_amount = current_balance
            invoice.save(update_fields=["status", "balance_amount", "updated_at"])

        student_label = "N/A"
        if invoice and invoice.student:
            student_label = f"{invoice.student.first_name} {invoice.student.last_name}"
        Notification.objects.create(
            title="Payment Recorded",
            message=f"Payment of {payment.amount} recorded for {student_label}",
            recipient=request.user,
            created_by=request.user,
        )

        if idem_key:
            from apps.siteconfig.cache_utils import tenant_cache_key

            cache_key = tenant_cache_key(
                f"offline_payment_idempotency:{request.user.pk}:{idem_key}", request
            )
            cache.set(
                cache_key,
                {"data": serializer.data, "status": status.HTTP_201_CREATED},
                timeout=86400,
            )

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        conflict = _check_offline_conflict(instance, request)
        if conflict is not None:
            return conflict
        return super().update(request, *args, partial=partial, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def by_method(self, request):
        """Get payment breakdown by method"""
        queryset = self.get_queryset()

        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if from_date and to_date:
            queryset = queryset.filter(
                paid_at__date__gte=from_date, paid_at__date__lte=to_date
            )

        breakdown = queryset.values("method").annotate(
            total=Sum("amount"), count=Count("id")
        )

        return Response(
            {
                "breakdown": _money_aggregate_rows(breakdown),
                "total": amount_str(
                    queryset.aggregate(Sum("amount"))["amount__sum"] or 0
                ),
            }
        )

    @action(detail=False, methods=["get"])
    def recent(self, request):
        """Get recent payments"""
        limit = int(request.query_params.get("limit", 10))
        queryset = self.get_queryset()[:limit]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class FinancialAnalyticsAPI(APIView):
    """
    Financial analytics and reporting
    Revenue, collection rates, forecasting
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["Finance"],
        parameters=[
            OpenApiParameter(name="from_date", type=OpenApiTypes.DATE, required=False),
            OpenApiParameter(name="to_date", type=OpenApiTypes.DATE, required=False),
        ],
        responses={
            200: inline_serializer(
                name="FinancialAnalyticsResponse",
                fields={
                    "total_invoiced": serializers.CharField(),
                    "total_collected": serializers.CharField(),
                    "collection_rate": serializers.FloatField(),
                    "pending_amount": serializers.CharField(),
                    "overdue_amount": serializers.CharField(),
                    "outstanding_fees": serializers.CharField(),
                    "payment_methods": serializers.ListField(child=serializers.DictField()),
                    "monthly_revenue": serializers.ListField(child=serializers.DictField()),
                    "currency": serializers.CharField(),
                },
            ),
            400: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request):
        """Get comprehensive financial analytics"""
        school = _request_school(request)
        if school is None:
            return Response(
                {"error": "School context required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if not _can_read_finance(request.user, school):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        queryset_invoices = Invoice.objects.filter(school=school)
        queryset_payments = Payment.objects.filter(school=school)

        if from_date and to_date:
            queryset_invoices = queryset_invoices.filter(
                issued_date__gte=from_date, issued_date__lte=to_date
            )
            queryset_payments = queryset_payments.filter(
                paid_at__date__gte=from_date, paid_at__date__lte=to_date
            )

        total_invoiced = (
            queryset_invoices.aggregate(Sum("total_amount"))["total_amount__sum"] or 0
        )

        total_collected = queryset_payments.aggregate(Sum("amount"))["amount__sum"] or 0

        collection_rate = (
            (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0
        )

        pending_invoices = (
            queryset_invoices.filter(
                status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL]
            ).aggregate(Sum("balance_amount"))["balance_amount__sum"]
            or 0
        )

        overdue_invoices = (
            queryset_invoices.filter(status=Invoice.Status.OVERDUE).aggregate(
                Sum("balance_amount")
            )["balance_amount__sum"]
            or 0
        )

        outstanding_fees = pending_invoices + overdue_invoices

        payment_methods = queryset_payments.values("method").annotate(
            total=Sum("amount")
        )

        # DB-agnostic: works on SQLite and PostgreSQL
        monthly_revenue = (
            queryset_payments.annotate(month=ExtractMonth("paid_at"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )

        return Response(
            {
                "total_invoiced": amount_str(total_invoiced),
                "total_collected": amount_str(total_collected),
                "collection_rate": round(collection_rate, 1),
                "pending_amount": amount_str(pending_invoices),
                "overdue_amount": amount_str(overdue_invoices),
                "outstanding_fees": amount_str(outstanding_fees),
                "payment_methods": _money_aggregate_rows(payment_methods),
                "monthly_revenue": _money_aggregate_rows(monthly_revenue),
                # Local-first: the analytics summary belongs to THIS tenant, so its
                # currency is the requesting school's (resolve_currency cascades to
                # the platform default and never returns blank) — not an arbitrary
                # first-active ComplianceProfile, which could be another tenant's.
                "currency": school.resolve_currency(),
            }
        )
