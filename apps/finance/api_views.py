"""
Finance API Views
Invoice, Payment, and Financial Analytics endpoints
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.core.cache import cache
from django.db.models import Sum, Count
from django.db.models.functions import ExtractMonth
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.finance.models import Invoice, Payment, Notification, ComplianceProfile
from apps.api.serializers import InvoiceSerializer, PaymentSerializer
from apps.api.permissions import IsAdminUser
from apps.schools.models import School


FINANCE_WRITE_ROLES = {"ADMIN", "BURSAR", "ACCOUNTANT", "FINANCE_STAFF", "LEADERSHIP", "PRINCIPAL"}


def _can_write_finance(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
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
    raw = request.headers.get("X-Client-Updated-At") or request.META.get("HTTP_X_CLIENT_UPDATED_AT")
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
    filterset_fields = ['status', 'student', 'issued_date', 'due_date']
    ordering_fields = ['issued_date', 'due_date', 'total_amount', 'created_at']
    ordering = ['-issued_date', '-id']
    
    def get_queryset(self):
        user = self.request.user
        base = Invoice.objects.all().select_related('student__user')
        school = _request_school(self.request)
        if school is None:
            return base.none()
        base = base.filter(school=school)

        if user.is_staff or user.role in ['ADMIN', 'BURSAR', 'LEADERSHIP', 'HOD']:
            return base

        from apps.people.models import StudentProfile

        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return base.filter(student=student_profile)

        from apps.accounts.permissions import guardian_finance_student_ids
        guardian_children = guardian_finance_student_ids(user)

        return base.filter(student_id__in=guardian_children)
    
    def list(self, request, *args, **kwargs):
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
        
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        if from_date and to_date:
            queryset = queryset.filter(
                issued_date__gte=from_date,
                issued_date__lte=to_date
            )
        
        student_id = request.query_params.get('student_id')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        """Create new invoice"""
        if not _can_write_finance(request.user):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        school = _request_school(request)
        if school is None:
            return Response(
                {'error': 'School context required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.validated_data.get("student")
        if student and student.school_id != school.id:
            return Response(
                {'error': 'Cross-tenant student reference is not allowed'},
                status=status.HTTP_403_FORBIDDEN
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

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Mark invoice as fully paid"""
        if not _can_write_finance(request.user):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        invoice = self.get_object()
        invoice.status = Invoice.Status.PAID
        invoice.balance_amount = 0
        invoice.save(update_fields=["status", "balance_amount", "updated_at"])
        
        Notification.objects.create(
            title="Invoice Marked Paid",
            message=f"Invoice {invoice.id} has been marked as paid",
            recipient=request.user,
            created_by=request.user
        )
        
        return Response({
            'status': 'success',
            'invoice_id': invoice.id,
            'marked_at': timezone.now().isoformat()
        })
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get invoice summary statistics"""
        queryset = self.get_queryset()
        
        total_amount = queryset.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        paid_amount = queryset.filter(
            status=Invoice.Status.PAID
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        pending_amount = queryset.filter(
            status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL]
        ).aggregate(Sum('balance_amount'))['balance_amount__sum'] or 0
        overdue_amount = queryset.filter(
            status=Invoice.Status.OVERDUE
        ).aggregate(Sum('balance_amount'))['balance_amount__sum'] or 0
        
        count_by_status = queryset.values('status').annotate(
            count=Count('id')
        )
        
        return Response({
            'total_amount': float(total_amount),
            'paid_amount': float(paid_amount),
            'pending_amount': float(pending_amount),
            'overdue_amount': float(overdue_amount),
            'payment_rate': round((paid_amount / total_amount * 100), 1) if total_amount > 0 else 0,
            'by_status': list(count_by_status)
        })


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Payment recording and tracking API
    
    Create and retrieve payment records
    Filter by invoice, payment method, date
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    ordering_fields = ['created_at', 'amount', 'paid_at']
    ordering = ['-paid_at']
    
    def get_queryset(self):
        user = self.request.user
        base = Payment.objects.all().select_related('invoice__student__user')
        school = _request_school(self.request)
        if school is None:
            return base.none()
        base = base.filter(school=school)

        if _can_write_finance(user):
            return base

        from apps.people.models import StudentProfile

        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return base.filter(invoice__student=student_profile)

        from apps.accounts.permissions import guardian_finance_student_ids
        guardian_children = guardian_finance_student_ids(user)

        return base.filter(invoice__student_id__in=guardian_children)
    
    def create(self, request, *args, **kwargs):
        """
        Record a new payment.
        Supports X-Idempotency-Key: same key within 24h returns the same response (offline replay dedup).
        Request Body: { "invoice": 1, "amount": 25000.00, "method": "MTN_MOMO", "reference": "REF123456", "paid_at": "..." }
        """
        if not _can_write_finance(request.user):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        school = _request_school(request)
        if school is None:
            return Response(
                {'error': 'School context required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        idem_key = (request.headers.get("X-Idempotency-Key") or request.META.get("HTTP_X_IDEMPOTENCY_KEY") or "").strip()[:64]
        if idem_key:
            cache_key = f"offline_payment_idempotency:{request.user.pk}:{idem_key}"
            cached = cache.get(cache_key)
            if cached is not None:
                return Response(cached.get("data"), status=cached.get("status", status.HTTP_200_OK))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.validated_data.get("invoice")
        student = serializer.validated_data.get("student")
        if invoice:
            invoice_school_id = getattr(invoice, "school_id", None)
            if invoice_school_id and invoice_school_id != school.id:
                return Response(
                    {'error': 'Cross-tenant invoice reference is not allowed'},
                    status=status.HTTP_403_FORBIDDEN
                )
            if invoice.student_id and getattr(invoice.student, "school_id", None) != school.id:
                return Response(
                    {'error': 'Cross-tenant invoice student reference is not allowed'},
                    status=status.HTTP_403_FORBIDDEN
                )
        if student and student.school_id != school.id:
            return Response(
                {'error': 'Cross-tenant student reference is not allowed'},
                status=status.HTTP_403_FORBIDDEN
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
            created_by=request.user
        )

        if idem_key:
            cache_key = f"offline_payment_idempotency:{request.user.pk}:{idem_key}"
            cache.set(cache_key, {"data": serializer.data, "status": status.HTTP_201_CREATED}, timeout=86400)

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
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

    @action(detail=False, methods=['get'])
    def by_method(self, request):
        """Get payment breakdown by method"""
        queryset = self.get_queryset()
        
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        if from_date and to_date:
            queryset = queryset.filter(
                paid_at__date__gte=from_date,
                paid_at__date__lte=to_date
            )
        
        breakdown = queryset.values('method').annotate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        return Response({
            'breakdown': list(breakdown),
            'total': float(queryset.aggregate(Sum('amount'))['amount__sum'] or 0)
        })
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent payments"""
        limit = int(request.query_params.get('limit', 10))
        queryset = self.get_queryset()[:limit]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class FinancialAnalyticsAPI(APIView):
    """
    Financial analytics and reporting
    Revenue, collection rates, forecasting
    """
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        """Get comprehensive financial analytics"""
        school = _request_school(request)
        if school is None:
            return Response(
                {'error': 'School context required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        queryset_invoices = Invoice.objects.filter(school=school)
        queryset_payments = Payment.objects.filter(school=school)
        
        if from_date and to_date:
            queryset_invoices = queryset_invoices.filter(
                issued_date__gte=from_date,
                issued_date__lte=to_date
            )
            queryset_payments = queryset_payments.filter(
                paid_at__date__gte=from_date,
                paid_at__date__lte=to_date
            )
        
        total_invoiced = queryset_invoices.aggregate(
            Sum('total_amount')
        )['total_amount__sum'] or 0
        
        total_collected = queryset_payments.aggregate(
            Sum('amount')
        )['amount__sum'] or 0
        
        collection_rate = (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0
        
        pending_invoices = queryset_invoices.filter(
            status__in=[Invoice.Status.ISSUED, Invoice.Status.PARTIAL]
        ).aggregate(Sum('balance_amount'))['balance_amount__sum'] or 0
        
        overdue_invoices = queryset_invoices.filter(
            status=Invoice.Status.OVERDUE
        ).aggregate(Sum('balance_amount'))['balance_amount__sum'] or 0
        
        outstanding_fees = pending_invoices + overdue_invoices
        
        payment_methods = queryset_payments.values('method').annotate(
            total=Sum('amount')
        )
        
        # DB-agnostic: works on SQLite and PostgreSQL
        monthly_revenue = queryset_payments.annotate(
            month=ExtractMonth('paid_at')
        ).values('month').annotate(
            total=Sum('amount')
        ).order_by('month')
        
        return Response({
            'total_invoiced': float(total_invoiced),
            'total_collected': float(total_collected),
            'collection_rate': round(collection_rate, 1),
            'pending_amount': float(pending_invoices),
            'overdue_amount': float(overdue_invoices),
            'outstanding_fees': float(outstanding_fees),
            'payment_methods': list(payment_methods),
            'monthly_revenue': list(monthly_revenue),
            'currency': ComplianceProfile.objects.filter(is_active=True).values_list('currency_code', flat=True).first() or 'XAF'
        })
