"""
Phase 8 Task 6: Advanced Finance - Payment Validators
Payment data validation, PCI compliance checks
"""

from decimal import Decimal
from datetime import datetime
from django.utils.translation import gettext_lazy as _


class PaymentValidator:
    """Base payment validator with error tracking."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def add_error(self, message):
        self.errors.append(message)

    def add_warning(self, message):
        self.warnings.append(message)

    def is_valid(self):
        return len(self.errors) == 0

    def get_issues_count(self):
        return len(self.errors) + len(self.warnings)


class AmountValidator(PaymentValidator):
    """Validates payment amounts."""

    def validate_amount(self, amount, min_amount=None, max_amount=None):
        try:
            amount_decimal = Decimal(str(amount))
        except Exception:
            self.add_error(_("Invalid amount format"))
            return False

        if amount_decimal <= 0:
            self.add_error(_("Amount must be positive"))
            return False

        if amount_decimal < Decimal("0.01"):
            self.add_error(_("Amount must be at least 0.01"))
            return False

        if min_amount is not None and amount_decimal < Decimal(str(min_amount)):
            self.add_error(_(f"Amount below minimum: {min_amount}"))
            return False

        if max_amount is not None and amount_decimal > Decimal(str(max_amount)):
            self.add_error(_(f"Amount exceeds maximum: {max_amount}"))
            return False

        if amount_decimal.as_tuple().exponent < -2:
            self.add_warning(_("Amount has excessive decimal places"))

        return True


class CurrencyValidator(PaymentValidator):
    """Validates currency codes."""

    VALID_CURRENCIES = [
        "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SEK", "NZD",
        "MXN", "SGD", "HKD", "NOK", "KRW", "TRY", "RUB", "INR", "BRL", "ZAR",
        "XAF", "CFA", "NGN", "KES", "GHS", "GBP",
    ]

    def validate_currency(self, currency_code):
        if not currency_code:
            self.add_error(_("Currency code is required"))
            return False

        if len(currency_code) != 3:
            self.add_error(_("Currency code must be 3 characters"))
            return False

        currency_code = currency_code.upper()

        if currency_code not in self.VALID_CURRENCIES:
            self.add_warning(_(f"Unusual currency code: {currency_code}"))

        return True


class PaymentMethodValidator(PaymentValidator):
    """Validates payment method configuration."""

    def validate_api_configuration(self, gateway, api_key, api_secret):
        if not gateway:
            self.add_error(_("Gateway is required"))
            return False

        if gateway == "manual":
            return True

        if not api_key or not api_secret:
            self.add_error(_(f"{gateway} requires API key and secret"))
            return False

        if len(api_key) < 10:
            self.add_error(_("API key appears invalid (too short)"))
            return False

        if len(api_secret) < 10:
            self.add_error(_("API secret appears invalid (too short)"))
            return False

        return True

    def validate_fees(self, fee_percent, fixed_fee):
        try:
            fee_decimal = Decimal(str(fee_percent))
            fixed_decimal = Decimal(str(fixed_fee))
        except Exception:
            self.add_error(_("Invalid fee format"))
            return False

        if fee_decimal < 0 or fee_decimal > 100:
            self.add_error(_("Fee percentage must be between 0 and 100"))
            return False

        if fixed_decimal < 0:
            self.add_error(_("Fixed fee cannot be negative"))
            return False

        if fee_decimal == 0 and fixed_decimal == 0:
            self.add_warning(_("No transaction fees configured"))

        return True


class RefundValidator(PaymentValidator):
    """Validates refund requests."""

    def validate_refund_amount(self, payment_amount, refund_amount):
        try:
            payment_decimal = Decimal(str(payment_amount))
            refund_decimal = Decimal(str(refund_amount))
        except Exception:
            self.add_error(_("Invalid amount format"))
            return False

        if refund_decimal <= 0:
            self.add_error(_("Refund amount must be positive"))
            return False

        if refund_decimal > payment_decimal:
            self.add_error(_(f"Refund cannot exceed payment amount: {payment_amount}"))
            return False

        return True

    def validate_refund_reason(self, reason):
        valid_reasons = ["duplicate", "incorrect_amount", "student_request", "overpayment", "compliance", "other"]

        if not reason:
            self.add_error(_("Refund reason is required"))
            return False

        if reason not in valid_reasons:
            self.add_error(_(f"Invalid refund reason: {reason}"))
            return False

        return True


class CompliancePaymentValidator(PaymentValidator):
    """Validates payments against compliance rules."""

    def validate_against_compliance(self, payment, compliance_rules):
        if not compliance_rules:
            return True

        for rule in compliance_rules:
            if rule.rule_type == "data_retention":
                if not self._validate_data_retention(payment):
                    continue

            if hasattr(rule, "custom_parameters"):
                params = rule.custom_parameters or {}
                if "max_payment_amount" in params:
                    max_amount = Decimal(str(params["max_payment_amount"]))
                    if payment.amount > max_amount:
                        self.add_error(_(f"Payment exceeds compliance limit: {max_amount}"))

        return self.is_valid()

    def _validate_data_retention(self, payment):
        if payment.gateway_response and "card" in str(payment.gateway_response):
            self.add_warning(_("Payment data contains sensitive information"))
            return False
        return True

    def generate_compliance_score(self, payment, compliance_rules):
        if not compliance_rules:
            return 100.0

        total_checks = len(compliance_rules)
        passed_checks = 0

        for rule in compliance_rules:
            if rule.rule_type == "data_retention":
                if self._validate_data_retention(payment):
                    passed_checks += 1
            else:
                passed_checks += 1

        return (passed_checks / total_checks * 100) if total_checks > 0 else 100.0


class TransactionReconciliationValidator(PaymentValidator):
    """Validates transaction reconciliation."""

    def validate_reconciliation(self, payments, transactions):
        payment_ids = set(p.id for p in payments)
        transaction_payment_ids = set(t.payment_id for t in transactions)

        missing_transactions = payment_ids - transaction_payment_ids
        if missing_transactions:
            self.add_error(_(f"Missing transactions for {len(missing_transactions)} payments"))

        orphaned_transactions = transaction_payment_ids - payment_ids
        if orphaned_transactions:
            self.add_error(_(f"Found {len(orphaned_transactions)} orphaned transactions"))

        return self.is_valid()

    def validate_amount_reconciliation(self, total_payments, total_transactions):
        try:
            payments_decimal = Decimal(str(total_payments))
            transactions_decimal = Decimal(str(total_transactions))
        except Exception:
            self.add_error(_("Invalid amount format"))
            return False

        if payments_decimal != transactions_decimal:
            difference = abs(payments_decimal - transactions_decimal)
            self.add_error(_(f"Amount mismatch: {difference}"))
            return False

        return True


class CardValidator:
    """Validate credit card information"""

    CARD_TYPES = {
        "visa": {"prefix": "4", "lengths": [13, 16, 19]},
        "mastercard": {"prefix": "5[1-5]", "lengths": [16]},
        "amex": {"prefix": "3[47]", "lengths": [15]},
    }

    @staticmethod
    def validate_card_number(card_number):
        card_number = card_number.replace(" ", "").replace("-", "")

        if not card_number.isdigit():
            return False

        if len(card_number) < 13 or len(card_number) > 19:
            return False

        digits = [int(d) for d in card_number]
        checksum = 0

        for i, digit in enumerate(reversed(digits)):
            if i % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit

        return checksum % 10 == 0

    @staticmethod
    def validate_expiry_date(month, year):
        try:
            month = int(month)
            year = int(year)

            if month < 1 or month > 12:
                return False

            expiry = datetime(year, month, 1)
            return expiry > datetime.now()
        except (ValueError, TypeError):
            return False

    @staticmethod
    def validate_cvv(cvv):
        if not cvv or not cvv.isdigit():
            return False

        return len(cvv) in [3, 4]

    @staticmethod
    def get_card_type(card_number):
        import re

        for card_type, rules in CardValidator.CARD_TYPES.items():
            if re.match(rules["prefix"], card_number[:2]):
                return card_type

        return "unknown"


class BankValidator:
    """Validate bank account information"""

    BANK_CODES = {
        "GTB": "Guaranty Trust Bank",
        "UBA": "United Bank for Africa",
        "FCMB": "First City Monument Bank",
        "ACCESS": "Access Bank",
        "ZENITH": "Zenith Bank",
    }
