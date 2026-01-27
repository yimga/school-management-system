"""
Phase 8 Task 6: Advanced Finance - Payment Validators
Payment data validation, PCI compliance checks
"""

from decimal import Decimal
from datetime import datetime


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


class CardValidator:
    """Validate credit card information"""
    
    CARD_TYPES = {
        'visa': {'prefix': '4', 'lengths': [13, 16, 19]},
        'mastercard': {'prefix': '5[1-5]', 'lengths': [16]},
        'amex': {'prefix': '3[47]', 'lengths': [15]},
    }
    
    @staticmethod
    def validate_card_number(card_number):
        """Validate using Luhn algorithm"""
        card_number = card_number.replace(' ', '').replace('-', '')
        
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
        """Validate expiry date"""
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
        """Validate CVV/CVC"""
        if not cvv or not cvv.isdigit():
            return False
        
        return len(cvv) in [3, 4]
    
    @staticmethod
    def get_card_type(card_number):
        """Detect card type"""
        import re
        
        for card_type, rules in CardValidator.CARD_TYPES.items():
            if re.match(rules['prefix'], card_number[:2]):
                return card_type
        
        return 'unknown'


class AmountValidator(PaymentValidator):
    """Validate transaction amounts."""

    MIN_AMOUNT = Decimal('100')
    MAX_AMOUNT = Decimal('10000000')

    @staticmethod
    def validate_amount(amount, min_amount=None, max_amount=None):
        """Validate transaction amount."""
        try:
            amount_decimal = Decimal(str(amount))
        except Exception:
            return False

        if amount_decimal <= 0:
            return False

        if min_amount is not None and amount_decimal < Decimal(str(min_amount)):
            return False

        if max_amount is not None and amount_decimal > Decimal(str(max_amount)):
            return False

        return True
    
    @staticmethod
    def get_amount_category(amount):
        """Categorize amount"""
        amount = Decimal(str(amount))
        
        if amount < Decimal('5000'):
            return 'small'
        elif amount < Decimal('50000'):
            return 'medium'
        elif amount < Decimal('500000'):
            return 'large'
        else:
            return 'very_large'


class CurrencyValidator(PaymentValidator):
    """Validate currency codes."""

    VALID_CURRENCIES = {
        'USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'SEK', 'NZD',
        'MXN', 'SGD', 'HKD', 'NOK', 'KRW', 'TRY', 'RUB', 'INR', 'BRL', 'ZAR',
        'XAF', 'CFA', 'NGN', 'KES', 'GHS',
    }

    @staticmethod
    def validate_currency(currency_code):
        if not currency_code:
            return False
        if len(currency_code) != 3:
            return False
        if not currency_code.isalpha():
            return False
        return True


class PaymentMethodValidator(PaymentValidator):
    """Validate payment method configuration."""

    @staticmethod
    def validate_api_configuration(gateway, api_key, api_secret):
        if not gateway:
            return False
        if gateway == 'manual':
            return True
        if not api_key or not api_secret:
            return False
        if len(api_key) < 10 or len(api_secret) < 10:
            return False
        return True

    @staticmethod
    def validate_fees(fee_percent, fixed_fee):
        try:
            fee_decimal = Decimal(str(fee_percent))
            fixed_decimal = Decimal(str(fixed_fee))
        except Exception:
            return False

        if fee_decimal < 0 or fee_decimal > 100:
            return False
        if fixed_decimal < 0:
            return False
        return True


class RefundValidator(PaymentValidator):
    """Validate refund requests."""

    VALID_REASONS = {
        'duplicate', 'incorrect_amount', 'student_request',
        'overpayment', 'compliance', 'other',
    }

    @staticmethod
    def validate_refund_amount(payment_amount, refund_amount):
        try:
            payment_decimal = Decimal(str(payment_amount))
            refund_decimal = Decimal(str(refund_amount))
        except Exception:
            return False

        if refund_decimal <= 0:
            return False
        if refund_decimal > payment_decimal:
            return False
        return True

    @staticmethod
    def validate_refund_reason(reason):
        if not reason:
            return False
        return reason in RefundValidator.VALID_REASONS


class CompliancePaymentValidator(PaymentValidator):
    """Validate payments against compliance rules."""

    def validate_against_compliance(self, payment, compliance_rules):
        if not compliance_rules:
            return True
        for rule in compliance_rules:
            params = getattr(rule, "custom_parameters", None) or {}
            max_amount = params.get("max_payment_amount")
            if max_amount is not None and payment.amount > Decimal(str(max_amount)):
                self.add_error("Payment exceeds compliance limit")
        return self.is_valid()


class BankValidator:
    """Validate bank account information"""
    
    BANK_CODES = {
        'GTB': 'Guaranty Trust Bank',
        'UBA': 'United Bank for Africa',
        'FCMB': 'First City Monument Bank',
        'ACCESS': 'Access Bank',
        'ZENITH': 'Zenith Bank',
    }
    
    @staticmethod
    def validate_account_number(account_number):
        """Validate account number format"""
        if not account_number or not account_number.isdigit():
            return False
        
        return len(account_number) in [10, 11]
    
    @staticmethod
    def validate_bank_code(bank_code):
        """Validate bank code"""
        return bank_code in BankValidator.BANK_CODES
    
    @staticmethod
    def validate_account_name(account_name):
        """Validate account holder name"""
        if not account_name or len(account_name) < 3:
            return False
        
        return len(account_name) <= 100


class MobileMoneyValidator:
    """Validate mobile money transactions"""
    
    PROVIDERS = {
        # Expect international format without leading '+' (e.g., '2347031234567')
        'mtn': {'prefix': '234703|234706|234701', 'length': 13},
        'airtel': {'prefix': '234701|234708', 'length': 13},
        'glo': {'prefix': '234705|234704', 'length': 13},
        '9mobile': {'prefix': '234809|234808', 'length': 13},
    }
    
    @staticmethod
    def validate_phone_number(phone_number):
        """Validate phone number"""
        import re
        
        phone_number = phone_number.replace('+', '').replace(' ', '')
        
        for provider, rules in MobileMoneyValidator.PROVIDERS.items():
            if re.match(rules['prefix'], phone_number) and len(phone_number) == rules['length']:
                return True
        
        return False
    
    @staticmethod
    def get_provider(phone_number):
        """Get provider for phone number"""
        import re
        
        phone_number = phone_number.replace('+', '').replace(' ', '')
        
        for provider, rules in MobileMoneyValidator.PROVIDERS.items():
            if re.match(rules['prefix'], phone_number):
                return provider
        
        return None


class PaymentDataValidator:
    """Comprehensive payment data validation"""
    
    @staticmethod
    def validate_card_payment(payment_data):
        """Validate card payment data"""
        errors = []
        
        # Validate card number
        if not CardValidator.validate_card_number(payment_data.get('card_number', '')):
            errors.append('Invalid card number')
        
        # Validate expiry
        if not CardValidator.validate_expiry_date(
            payment_data.get('expiry_month'),
            payment_data.get('expiry_year')
        ):
            errors.append('Invalid expiry date')
        
        # Validate CVV
        if not CardValidator.validate_cvv(payment_data.get('cvv', '')):
            errors.append('Invalid CVV')
        
        # Validate amount
        if not AmountValidator.validate_amount(payment_data.get('amount')):
            errors.append('Invalid amount')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
        }
    
    @staticmethod
    def validate_bank_payment(payment_data):
        """Validate bank transfer data"""
        errors = []
        
        # Validate account
        if not BankValidator.validate_account_number(payment_data.get('account_number', '')):
            errors.append('Invalid account number')
        
        # Validate bank
        if not BankValidator.validate_bank_code(payment_data.get('bank_code', '')):
            errors.append('Invalid bank code')
        
        # Validate account name
        if not BankValidator.validate_account_name(payment_data.get('account_name', '')):
            errors.append('Invalid account name')
        
        # Validate amount
        if not AmountValidator.validate_amount(payment_data.get('amount')):
            errors.append('Invalid amount')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
        }
    
    @staticmethod
    def validate_mobile_money(payment_data):
        """Validate mobile money payment"""
        errors = []
        
        # Validate phone
        if not MobileMoneyValidator.validate_phone_number(payment_data.get('phone_number', '')):
            errors.append('Invalid phone number')
        
        # Validate amount
        if not AmountValidator.validate_amount(payment_data.get('amount')):
            errors.append('Invalid amount')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
        }


class PaymentRuleValidator:
    """Validate against business rules"""
    
    @staticmethod
    def check_daily_limit(user_id, amount, daily_limit=1000000):
        """Check daily spending limit"""
        # In production, query actual user transactions
        return True
    
    @staticmethod
    def check_transaction_frequency(user_id, hours=1, max_transactions=10):
        """Check transaction frequency"""
        # In production, query actual user transactions
        return True
    
    @staticmethod
    def check_blacklist(user_id, phone_number=None, card_number=None):
        """Check if user/payment method on blacklist"""
        # In production, query actual blacklist
        return False
    
    @staticmethod
    def validate_business_rules(user_id, payment_data):
        """Validate all business rules"""
        violations = []
        
        if not PaymentRuleValidator.check_daily_limit(user_id, payment_data.get('amount')):
            violations.append('Daily limit exceeded')
        
        if not PaymentRuleValidator.check_transaction_frequency(user_id):
            violations.append('Too many transactions')
        
        if PaymentRuleValidator.check_blacklist(user_id):
            violations.append('User on blacklist')
        
        return {
            'compliant': len(violations) == 0,
            'violations': violations,
        }
