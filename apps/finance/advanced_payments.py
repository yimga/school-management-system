"""
Phase 9 Task 6: Advanced Payment Features
Recurring payments, split payments, dynamic pricing, installments

INTEGRATES WITH:
- apps.finance.models (Invoice, Payment, PaymentPlan, RecurringPaymentSubscription)
- apps.finance.payment_processors (Stripe, PayPal, Flutterwave, Paystack)
"""

import logging
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.utils import DatabaseError, IntegrityError
from datetime import timedelta
from decimal import Decimal
from typing import Dict, List

from .models import (
    ComplianceProfile,
    Invoice,
    Payment,
    PaymentPlan,
    RecurringPaymentSubscription,
)

User = get_user_model()


def _recurring_subscription_process_payment(self):
    """Process the next scheduled payment. Only runs Stripe when payment_processor is 'stripe'."""
    from apps.finance.payment_processors import StripeProcessor
    from apps.people.models import StudentProfile

    if self.status != "ACTIVE":
        return False
    student = None
    if getattr(self.user, "id", None):
        sp = StudentProfile.objects.filter(user_id=self.user.id).first()
        if sp:
            student = sp
    profile = ComplianceProfile.objects.first()
    if not profile:
        return False
    school = getattr(student, "school", None) if student else None
    invoice = Invoice.objects.create(
        profile=profile,
        school=school,
        student=student,
        total_amount=self.plan.amount,
        balance_amount=self.plan.amount,
        due_date=self.next_payment_date,
        notes=f"{self.plan.name} - Payment {self.payments_made + 1}",
        status=Invoice.Status.ISSUED,
    )
    processor_name = (self.payment_processor or "").strip().lower()
    if processor_name != "stripe":
        return False
    try:
        processor = StripeProcessor()
        result = processor.process_payment(
            {
                "amount": float(self.plan.amount),
                "currency": "USD",
                "customer_id": self.customer_payment_method_id,
            }
        )
        Payment.objects.create(
            invoice=invoice,
            amount=self.plan.amount,
            status="completed",
            gateway_transaction_id=result.get("transaction_id") or None,
        )
        self.payments_made += 1
        self.total_paid += self.plan.amount
        self.last_payment_date = timezone.now().date()
        self.next_payment_date = self._calculate_next_payment_date()
        if (
            self.plan.max_installments > 0
            and self.payments_made >= self.plan.max_installments
        ):
            self.status = "COMPLETED"
        self.save()
        return True
    except (
        DatabaseError,
        IntegrityError,
        ValidationError,
        ValueError,
        TypeError,
        AttributeError,
    ) as e:
        logging.getLogger(__name__).debug(
            "recurring subscription record_payment skip: %s", e
        )
        self.missed_payments += 1
        if self.missed_payments >= 3:
            self.status = "DEFAULTED"
        self.save()
        return False


def _calculate_next_payment_date(self):
    """Calculate next payment date based on frequency."""
    from datetime import timedelta

    current = self.next_payment_date
    if self.plan.frequency == "WEEKLY":
        return current + timedelta(days=7)
    if self.plan.frequency == "BIWEEKLY":
        return current + timedelta(days=14)
    if self.plan.frequency == "MONTHLY":
        return current + timedelta(days=30)
    if self.plan.frequency == "QUARTERLY":
        return current + timedelta(days=90)
    if self.plan.frequency == "ANNUALLY":
        return current + timedelta(days=365)
    return current + timedelta(days=30)


RecurringPaymentSubscription.process_payment = _recurring_subscription_process_payment
RecurringPaymentSubscription._calculate_next_payment_date = _calculate_next_payment_date


class SplitPayment(models.Model):
    """
    Split payments across multiple parties

    USE CASE: Parent pays for multiple children, scholarship splits
    """

    parent_invoice = models.ForeignKey(
        "finance.Invoice", on_delete=models.CASCADE, related_name="split_payments"
    )

    split_name = models.CharField(max_length=255)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Split: {self.split_name}"


class SplitPaymentPart(models.Model):
    """Individual part of a split payment"""

    split_payment = models.ForeignKey(
        SplitPayment, on_delete=models.CASCADE, related_name="parts"
    )

    payer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="payment_splits"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )

    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("split_payment", "payer")

    def __str__(self):
        return f"{self.payer.username} - {self.amount}"


class DynamicPricingRule(models.Model):
    """
    Dynamic pricing rules for fees

    USE CASES: Early bird discounts, bulk discounts, need-based adjustments
    """

    RULE_TYPES = [
        ("PERCENTAGE_DISCOUNT", "Percentage Discount"),
        ("FIXED_DISCOUNT", "Fixed Amount Discount"),
        ("PERCENTAGE_INCREASE", "Percentage Increase"),
        ("TIERED", "Tiered Pricing"),
    ]

    CONDITION_TYPES = [
        ("DATE_RANGE", "Date Range"),
        ("SIBLING_COUNT", "Number of Siblings"),
        ("ENROLLMENT_DATE", "Enrollment Date"),
        ("SCHOLARSHIP", "Scholarship"),
        ("PAYMENT_HISTORY", "Payment History"),
    ]

    name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=30, choices=RULE_TYPES)
    condition_type = models.CharField(max_length=30, choices=CONDITION_TYPES)

    # Rule parameters (JSON)
    parameters = models.JSONField(default=dict)

    # Adjustment
    adjustment_value = models.DecimalField(max_digits=10, decimal_places=2)

    # Validity
    valid_from = models.DateField()
    valid_to = models.DateField()
    is_active = models.BooleanField(default=True)

    priority = models.IntegerField(
        default=0, help_text="Higher priority rules apply first"
    )

    class Meta:
        ordering = ["-priority", "name"]

    def __str__(self):
        return self.name

    def applies_to(self, user, invoice) -> bool:
        """Check if rule applies to user/invoice"""
        current_date = timezone.now().date()

        if not (self.valid_from <= current_date <= self.valid_to):
            return False

        if self.condition_type == "DATE_RANGE":
            # Early bird discount
            payment_date = invoice.due_date
            early_date = self.parameters.get("early_date")
            return payment_date <= early_date if early_date else False

        elif self.condition_type == "SIBLING_COUNT":
            # Sibling discount
            from apps.people.models import Student

            sibling_count = Student.objects.filter(
                parent=user.parent if hasattr(user, "parent") else None
            ).count()
            min_siblings = self.parameters.get("min_siblings", 2)
            return sibling_count >= min_siblings

        elif self.condition_type == "SCHOLARSHIP":
            # Scholarship recipient
            return hasattr(user, "scholarship") and user.scholarship.is_active

        return False

    def calculate_adjusted_amount(self, original_amount: Decimal) -> Decimal:
        """Calculate adjusted amount based on rule"""
        if self.rule_type == "PERCENTAGE_DISCOUNT":
            return original_amount * (1 - self.adjustment_value / 100)

        elif self.rule_type == "FIXED_DISCOUNT":
            return max(Decimal("0.00"), original_amount - self.adjustment_value)

        elif self.rule_type == "PERCENTAGE_INCREASE":
            return original_amount * (1 + self.adjustment_value / 100)

        return original_amount


class InstallmentPlan(models.Model):
    """
    Installment payment plans for invoices

    INTEGRATES WITH: apps.finance.models.Invoice
    """

    invoice = models.OneToOneField(
        "finance.Invoice", on_delete=models.CASCADE, related_name="installment_plan"
    )

    num_installments = models.IntegerField()
    installment_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Schedule
    first_payment_date = models.DateField()
    payment_frequency_days = models.IntegerField(default=30)

    # Fees
    setup_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Annual interest rate %",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Installment Plan: {self.invoice.id} ({self.num_installments} payments)"

    def generate_schedule(self) -> List[Dict]:
        """Generate payment schedule"""
        schedule = []
        current_date = self.first_payment_date

        for i in range(self.num_installments):
            schedule.append(
                {
                    "installment_number": i + 1,
                    "due_date": current_date,
                    "amount": float(self.installment_amount),
                    "is_paid": False,
                }
            )
            current_date = current_date + timedelta(days=self.payment_frequency_days)

        return schedule


class PaymentAdvancedService:
    """
    Service for advanced payment features

    INTEGRATES WITH:
    - apps.finance.payment_processors (Stripe, PayPal, etc.)
    - apps.finance.models (Invoice, Payment)
    """

    @staticmethod
    def create_recurring_subscription(
        user, plan: PaymentPlan, payment_method_id: str, start_date=None
    ):
        """Create a recurring payment subscription"""
        if start_date is None:
            start_date = timezone.now().date()

        subscription = RecurringPaymentSubscription.objects.create(
            user=user,
            plan=plan,
            start_date=start_date,
            next_payment_date=start_date,
            customer_payment_method_id=payment_method_id,
            status="ACTIVE",
        )

        return subscription

    @staticmethod
    def process_due_recurring_payments():
        """Process all due recurring payments (cron job)"""
        today = timezone.now().date()

        due_subscriptions = RecurringPaymentSubscription.objects.filter(
            status="ACTIVE", next_payment_date__lte=today
        )

        results = {"success": 0, "failed": 0, "total": due_subscriptions.count()}

        for subscription in due_subscriptions:
            if subscription.process_payment():
                results["success"] += 1
            else:
                results["failed"] += 1

        return results

    @staticmethod
    def create_split_payment(invoice, splits: List[Dict]):
        """
        Create split payment for invoice

        Args:
            invoice: Invoice to split
            splits: List of {'user': User, 'amount': Decimal, 'percentage': Decimal}
        """
        # Validate total equals invoice amount
        total = sum(s["amount"] for s in splits)
        if abs(total - invoice.amount) > Decimal("0.01"):
            raise ValidationError("Split amounts must equal invoice total")

        split_payment = SplitPayment.objects.create(
            parent_invoice=invoice,
            split_name=f"Split payment for {invoice.description}",
            total_amount=invoice.amount,
        )

        for split in splits:
            SplitPaymentPart.objects.create(
                split_payment=split_payment,
                payer=split["user"],
                amount=split["amount"],
                percentage=split.get("percentage", Decimal("0.00")),
            )

        return split_payment

    @staticmethod
    def apply_dynamic_pricing(user, invoice):
        """Apply dynamic pricing rules to invoice"""
        rules = DynamicPricingRule.objects.filter(is_active=True).order_by("-priority")

        original_amount = invoice.amount
        adjusted_amount = original_amount
        applied_rules = []

        for rule in rules:
            if rule.applies_to(user, invoice):
                adjusted_amount = rule.calculate_adjusted_amount(adjusted_amount)
                applied_rules.append(rule.name)

        # Update invoice
        if adjusted_amount != original_amount:
            invoice.amount = adjusted_amount
            invoice.notes = f"Applied pricing rules: {', '.join(applied_rules)}"
            invoice.save()

        return {
            "original_amount": float(original_amount),
            "adjusted_amount": float(adjusted_amount),
            "discount": float(original_amount - adjusted_amount),
            "rules_applied": applied_rules,
        }

    @staticmethod
    def create_installment_plan(invoice, num_installments: int, start_date=None):
        """Create installment plan for invoice"""
        if start_date is None:
            start_date = timezone.now().date()

        installment_amount = invoice.amount / num_installments

        plan = InstallmentPlan.objects.create(
            invoice=invoice,
            num_installments=num_installments,
            installment_amount=installment_amount,
            first_payment_date=start_date,
        )

        return plan

    @staticmethod
    def get_payment_analytics(user) -> Dict:
        """Get payment analytics for user"""
        from apps.finance.models import Invoice, Payment

        invoices = Invoice.objects.filter(student=user)
        payments = Payment.objects.filter(invoice__student=user)

        total_invoiced = invoices.aggregate(total=models.Sum("amount"))[
            "total"
        ] or Decimal("0.00")

        total_paid = payments.filter(status="COMPLETED").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0.00")

        # Recurring subscriptions
        active_subscriptions = RecurringPaymentSubscription.objects.filter(
            user=user, status="ACTIVE"
        ).count()

        return {
            "total_invoiced": float(total_invoiced),
            "total_paid": float(total_paid),
            "outstanding": float(total_invoiced - total_paid),
            "active_subscriptions": active_subscriptions,
            "payment_completion_rate": (float(total_paid) / float(total_invoiced) * 100)
            if total_invoiced > 0
            else 0,
        }
