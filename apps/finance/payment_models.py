"""Phase 2.0 Payment Processing Models"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import uuid


class PaymentMethod(models.Model):
    """Payment method definitions and gateway configuration."""
    METHOD_TYPES = [
        ('card', 'Credit/Debit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('wallet', 'Digital Wallet'),
        ('mobile_money', 'Mobile Money'),
        ('check', 'Check'),
    ]
    
    GATEWAYS = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
        ('flutterwave', 'Flutterwave'),
        ('paystack', 'Paystack'),
        ('manual', 'Manual Processing'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES)
    gateway = models.CharField(max_length=20, choices=GATEWAYS, null=True, blank=True)
    region = models.ForeignKey('siteconfig.RegionConfig', on_delete=models.CASCADE, related_name='payment_methods')
    is_active = models.BooleanField(default=True)
    
    # Gateway configuration
    api_key = models.CharField(max_length=500, blank=True, help_text="Encrypted API key")
    api_secret = models.CharField(max_length=500, blank=True, help_text="Encrypted secret")
    webhook_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=500, blank=True)
    
    # Fees and limits
    transaction_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    fixed_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_payment_methods')
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Payment Method'
        verbose_name_plural = 'Payment Methods'
    
    def __str__(self):
        return f"{self.name} ({self.get_method_type_display()})"
    
    def calculate_fee(self, amount):
        """Calculate transaction fee based on configuration."""
        percent_fee = amount * (Decimal(self.transaction_fee_percent) / 100)
        return percent_fee + Decimal(self.fixed_fee)


class Payment(models.Model):
    """Records all payments processed through the system."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    PURPOSE_CHOICES = [
        ('tuition', 'Tuition'),
        ('exam_fee', 'Exam Fee'),
        ('activity_fee', 'Activity Fee'),
        ('accommodation', 'Accommodation'),
        ('other', 'Other'),
    ]

    METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK', 'Bank Transfer'),
        ('MTN_MOMO', 'MTN MoMo'),
        ('ORANGE_MOMO', 'Orange Money'),
        ('CHECK', 'Check'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(max_length=50, default=uuid.uuid4)
    reference = models.CharField(max_length=80, blank=True)
    invoice = models.ForeignKey('finance.Invoice', on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    student = models.ForeignKey('people.StudentProfile', on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    region = models.ForeignKey('siteconfig.RegionConfig', on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='payments', null=True, blank=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, blank=True)

    # Payment details
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    currency_code = models.CharField(max_length=3, default='USD')
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='tuition')
    description = models.TextField(blank=True)

    # Legacy receipt fields
    paid_at = models.DateTimeField(default=timezone.now)
    receipt_number = models.CharField(max_length=64, blank=True)
    external_reference = models.CharField(max_length=128, blank=True)
    receipt_file = models.FileField(
        upload_to="finance/receipts/",
        blank=True,
        null=True,
        help_text="Optional uploaded receipt or slip (PDF/image, max 2MB).",
    )

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_reason = models.TextField(blank=True)

    # Gateway information
    gateway_transaction_id = models.CharField(max_length=100, blank=True, unique=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    # Compliance
    compliance_checked = models.BooleanField(default=False)
    compliance_issues = models.JSONField(default=list, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    initiated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_payments')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments_created',
        help_text="User who recorded this payment"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft delete timestamp - set instead of deleting"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['region', 'created_at']),
        ]

    def __str__(self):
        target = self.invoice or self.reference_number
        return f"{target} - {self.amount} {self.currency_code}"

    def clean(self):
        """Validate payment data before saving."""
        if self.amount < Decimal("0.01"):
            raise ValidationError({"amount": "Payment amount must be at least 0.01"})

        if self.invoice:
            paid_amount = sum(
                p.amount for p in self.invoice.payments.exclude(pk=self.pk)
            ) or Decimal("0")
            remaining_balance = self.invoice.total_amount - paid_amount

            if self.amount > remaining_balance:
                raise ValidationError({
                    "amount": f"Payment {self.amount} exceeds remaining balance {remaining_balance}"
                })

            if self.method and self.invoice.profile:
                profile = self.invoice.profile
                if isinstance(profile.available_payment_methods, list) and profile.available_payment_methods:
                    if self.method not in profile.available_payment_methods:
                        raise ValidationError({
                            "method": (
                                f"Method '{self.method}' is not allowed for profile {profile.name}. "
                                f"Allowed: {', '.join(profile.available_payment_methods)}"
                            )
                        })

    def save(self, *args, **kwargs):
        """Call full_clean() before saving to validate."""
        self.full_clean()
        super().save(*args, **kwargs)

    def mark_processing(self):
        """Mark payment as processing."""
        self.status = 'processing'
        self.initiated_at = timezone.now()
        self.save()
        self._log_status_change(
            action_type='payment_initiated',
            severity='medium',
            details={'initiated_at': str(self.initiated_at)},
            user=self.processed_by,
        )

    def mark_completed(self, gateway_tx_id=None, response=None):
        """Mark payment as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if gateway_tx_id:
            self.gateway_transaction_id = gateway_tx_id
        if response:
            self.gateway_response = response
        self.save()
        self._log_status_change(
            action_type='payment_completed',
            severity='low',
            details={'gateway_transaction_id': gateway_tx_id or ''},
            user=self.processed_by,
        )

    def mark_failed(self, reason='', response=None):
        """Mark payment as failed."""
        self.status = 'failed'
        self.failed_at = timezone.now()
        self.status_reason = reason
        if response:
            self.gateway_response = response
        self.save()
        self._log_status_change(
            action_type='payment_failed',
            severity='high',
            details={'reason': reason or 'manual failure'},
            user=self.processed_by,
        )

    def _resolve_audit_region(self):
        if self.region:
            return self.region
        if self.invoice and getattr(self.invoice, "profile", None):
            return getattr(self.invoice.profile, "region", None)
        return None

    def _log_status_change(self, *, action_type: str, severity: str = "low", details=None, user=None):
        region = self._resolve_audit_region()
        if not region:
            return
        description = f"{self.reference_number} {action_type}".strip()
        if not description:
            description = action_type
        payload = {"status": self.status}
        if isinstance(details, dict):
            payload.update(details)
        elif details:
            payload["note"] = str(details)

        PaymentAuditLog.objects.create(
            action_type=action_type,
            payment=self,
            region=region,
            description=description,
            details=payload,
            severity=severity,
            user=user or self.processed_by or self.created_by,
        )


class Transaction(models.Model):
    """Individual transaction records for audit trail."""
    TRANSACTION_TYPE = [
        ('payment', 'Payment'),
        ('refund', 'Refund'),
        ('chargeback', 'Chargeback'),
        ('reversal', 'Reversal'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE, default='payment')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    gateway_reference = models.CharField(max_length=100, blank=True)
    
    # Details
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} {self.currency} ({self.status})"


class RefundRequest(models.Model):
    """Refund request tracking."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('processed', 'Processed'),
    ]
    
    REASON_CHOICES = [
        ('duplicate', 'Duplicate Payment'),
        ('incorrect_amount', 'Incorrect Amount'),
        ('student_request', 'Student Request'),
        ('overpayment', 'Overpayment'),
        ('compliance', 'Compliance Issue'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refund_requests')
    region = models.ForeignKey('siteconfig.RegionConfig', on_delete=models.CASCADE, related_name='refund_requests')
    
    # Refund details
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField()
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_notes = models.TextField(blank=True)
    
    # Processing
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='requested_refunds')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_refunds')
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Refund Request'
        verbose_name_plural = 'Refund Requests'
    
    def __str__(self):
        return f"Refund: {self.payment.reference_number} - {self.amount}"


class PaymentReconciliation(models.Model):
    """Reconciliation records for accounting."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reconciled', 'Reconciled'),
        ('discrepancy', 'Discrepancy Found'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    region = models.ForeignKey('siteconfig.RegionConfig', on_delete=models.CASCADE, related_name='payment_reconciliations')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name='reconciliations')
    
    # Period
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Totals
    total_payments = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_refunds = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_fees = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Reconciliation
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    discrepancy_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discrepancy_notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciled_payments')
    
    class Meta:
        ordering = ['-period_end']
        verbose_name = 'Payment Reconciliation'
        verbose_name_plural = 'Payment Reconciliations'
        unique_together = [['region', 'payment_method', 'period_start', 'period_end']]
    
    def __str__(self):
        return f"{self.region.code} - {self.payment_method.name} ({self.period_start} to {self.period_end})"


class PaymentAuditLog(models.Model):
    """Audit trail for payment operations."""
    ACTION_TYPES = [
        ('payment_created', 'Payment Created'),
        ('payment_initiated', 'Payment Initiated'),
        ('payment_completed', 'Payment Completed'),
        ('payment_failed', 'Payment Failed'),
        ('refund_requested', 'Refund Requested'),
        ('refund_approved', 'Refund Approved'),
        ('transaction_recorded', 'Transaction Recorded'),
        ('reconciliation_completed', 'Reconciliation Completed'),
    ]
    
    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, null=True, blank=True, related_name='audit_logs')
    region = models.ForeignKey('siteconfig.RegionConfig', on_delete=models.CASCADE, related_name='payment_audit_logs')
    
    # Details
    description = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_LEVELS, default='low')
    
    # Metadata
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_audit_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Payment Audit Log'
        verbose_name_plural = 'Payment Audit Logs'
        indexes = [
            models.Index(fields=['action_type', 'timestamp']),
            models.Index(fields=['region', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.get_action_type_display()} - {self.region.code}"
