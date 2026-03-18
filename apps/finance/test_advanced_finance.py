"""
Phase 8 Task 6: Advanced Finance Tests
Payment security, validation, processing tests
"""

from django.test import TestCase
from decimal import Decimal


class PaymentEncryptionTestCase(TestCase):
    """Test payment encryption"""

    def test_encrypt_card_number(self):
        """Test card number encryption"""
        from apps.finance.security import PaymentEncryption

        encrypted = PaymentEncryption.encrypt_card_number("4532123456789010")

        # Should mask all but last 4 digits
        self.assertTrue(encrypted.endswith("9010"))
        self.assertNotIn("4532", encrypted)

    def test_hash_payment_token(self):
        """Test token hashing"""
        from apps.finance.security import PaymentEncryption

        token = "test_token_12345"
        hashed = PaymentEncryption.hash_payment_token(token)

        self.assertEqual(len(hashed), 64)  # SHA256 hex
        self.assertNotEqual(hashed, token)


class FraudDetectorTestCase(TestCase):
    """Test fraud detection"""

    def test_check_amount_risk_high(self):
        """Test high amount fraud detection"""
        from apps.finance.security import FraudDetector

        high_amount = 150000

        is_risky = FraudDetector.check_amount_risk(high_amount)

        self.assertTrue(is_risky)

    def test_check_amount_risk_normal(self):
        """Test normal amount not flagged"""
        from apps.finance.security import FraudDetector

        normal_amount = 50000

        is_risky = FraudDetector.check_amount_risk(normal_amount)

        self.assertFalse(is_risky)

    def test_calculate_fraud_score(self):
        """Test fraud score calculation"""
        from apps.finance.security import FraudDetector

        payment_data = {
            "amount": 150000,
            "high_velocity": True,
            "geographic_anomaly": True,
            "new_card": True,
        }

        score = FraudDetector.calculate_fraud_score(payment_data)

        self.assertGreater(score, 50)
        self.assertLessEqual(score, 100)


class CardValidatorTestCase(TestCase):
    """Test card validation"""

    def test_validate_card_number_valid(self):
        """Test valid card number"""
        from apps.finance.payment_validators import CardValidator

        # Valid Visa test number
        valid_card = "4532015112830366"

        is_valid = CardValidator.validate_card_number(valid_card)

        self.assertTrue(is_valid)

    def test_validate_card_number_invalid(self):
        """Test invalid card number"""
        from apps.finance.payment_validators import CardValidator

        invalid_card = "4532015112830367"  # Invalid checksum

        is_valid = CardValidator.validate_card_number(invalid_card)

        self.assertFalse(is_valid)

    def test_validate_expiry_date_valid(self):
        """Test valid expiry date"""
        from apps.finance.payment_validators import CardValidator
        from datetime import datetime

        year = datetime.now().year + 2
        month = 12

        is_valid = CardValidator.validate_expiry_date(month, year)

        self.assertTrue(is_valid)

    def test_validate_cvv(self):
        """Test CVV validation"""
        from apps.finance.payment_validators import CardValidator

        # Valid 3-digit CVV
        self.assertTrue(CardValidator.validate_cvv("123"))

        # Valid 4-digit CVV
        self.assertTrue(CardValidator.validate_cvv("1234"))

        # Invalid
        self.assertFalse(CardValidator.validate_cvv("12"))
        self.assertFalse(CardValidator.validate_cvv("abc"))


class AmountValidatorTestCase(TestCase):
    """Test amount validation"""

    def test_validate_amount_valid(self):
        """Test valid amount"""
        from apps.finance.payment_validators import AmountValidator

        amount = Decimal("5000")

        is_valid = AmountValidator.validate_amount(amount)

        self.assertTrue(is_valid)

    def test_validate_amount_too_small(self):
        """Test amount too small"""
        from apps.finance.payment_validators import AmountValidator

        amount = Decimal("50")

        is_valid = AmountValidator.validate_amount(amount)

        self.assertFalse(is_valid)

    def test_get_amount_category(self):
        """Test amount categorization"""
        from apps.finance.payment_validators import AmountValidator

        self.assertEqual(AmountValidator.get_amount_category("2000"), "small")
        self.assertEqual(AmountValidator.get_amount_category("20000"), "medium")
        self.assertEqual(AmountValidator.get_amount_category("200000"), "large")
        self.assertEqual(AmountValidator.get_amount_category("1000000"), "very_large")


class BankValidatorTestCase(TestCase):
    """Test bank validation"""

    def test_validate_account_number(self):
        """Test account number validation"""
        from apps.finance.payment_validators import BankValidator

        # Valid 10-digit
        self.assertTrue(BankValidator.validate_account_number("1234567890"))

        # Valid 11-digit
        self.assertTrue(BankValidator.validate_account_number("12345678901"))

        # Invalid
        self.assertFalse(BankValidator.validate_account_number("123456789"))

    def test_validate_bank_code(self):
        """Test bank code validation"""
        from apps.finance.payment_validators import BankValidator

        self.assertTrue(BankValidator.validate_bank_code("GTB"))
        self.assertTrue(BankValidator.validate_bank_code("UBA"))
        self.assertFalse(BankValidator.validate_bank_code("XYZ"))

    def test_validate_account_name(self):
        """Test account name validation"""
        from apps.finance.payment_validators import BankValidator

        self.assertTrue(BankValidator.validate_account_name("John Doe"))
        self.assertFalse(BankValidator.validate_account_name("Jo"))


class MobileMoneyValidatorTestCase(TestCase):
    """Test mobile money validation"""

    def test_validate_phone_number(self):
        """Test phone number validation"""
        from apps.finance.payment_validators import MobileMoneyValidator

        # Valid Nigerian numbers
        valid_numbers = [
            "2347031234567",  # MTN
            "2347081234567",  # Airtel
            "2347051234567",  # Glo
        ]

        for number in valid_numbers:
            self.assertTrue(
                MobileMoneyValidator.validate_phone_number(number),
                f"Should validate {number}",
            )


class StripeProcessorTestCase(TestCase):
    """Test Stripe processor"""

    def test_charge_card(self):
        """Test charging card"""
        from apps.finance.payment_processors import StripeProcessor

        processor = StripeProcessor("test_key")
        result = processor.charge_card("tok_123", 5000, "NGN")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["amount"], 5000)

    def test_create_customer(self):
        """Test creating customer"""
        from apps.finance.payment_processors import StripeProcessor

        processor = StripeProcessor("test_key")
        result = processor.create_customer("test@example.com")

        self.assertIn("customer_id", result)
        self.assertEqual(result["email"], "test@example.com")


class PaystackProcessorTestCase(TestCase):
    """Test Paystack processor"""

    def test_initialize_transaction(self):
        """Test transaction initialization"""
        from apps.finance.payment_processors import PaystackProcessor

        processor = PaystackProcessor("sk_test", "pk_test")
        result = processor.initialize_transaction("test@example.com", 5000)

        self.assertIn("authorization_url", result)
        self.assertIn("reference", result)

    def test_verify_transaction(self):
        """Test transaction verification"""
        from apps.finance.payment_processors import PaystackProcessor

        processor = PaystackProcessor("sk_test", "pk_test")
        result = processor.verify_transaction("ref_12345")

        self.assertEqual(result["status"], "success")


class ProcessorFactoryTestCase(TestCase):
    """Test processor factory"""

    def test_get_processor(self):
        """Test getting processor"""
        from apps.finance.payment_processors import ProcessorFactory

        processor = ProcessorFactory.get_processor("stripe", "test_key")

        self.assertIsNotNone(processor)

    def test_get_available_processors(self):
        """Test getting available processors"""
        from apps.finance.payment_processors import ProcessorFactory

        available = ProcessorFactory.get_available_processors()

        self.assertIn("stripe", available)
        self.assertIn("paypal", available)
        self.assertIn("flutterwave", available)
        self.assertIn("paystack", available)


class PaymentDataValidatorTestCase(TestCase):
    """Test comprehensive payment data validation"""

    def test_validate_card_payment(self):
        """Test card payment validation"""
        from apps.finance.payment_validators import PaymentDataValidator

        from django.utils import timezone

        now = timezone.now()
        payment_data = {
            "card_number": "4532015112830366",
            "expiry_month": now.month,
            "expiry_year": now.year + 1,
            "cvv": "123",
            "amount": 5000,
        }

        result = PaymentDataValidator.validate_card_payment(payment_data)

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_bank_payment(self):
        """Test bank payment validation"""
        from apps.finance.payment_validators import PaymentDataValidator

        payment_data = {
            "account_number": "1234567890",
            "bank_code": "GTB",
            "account_name": "John Doe",
            "amount": 50000,
        }

        result = PaymentDataValidator.validate_bank_payment(payment_data)

        self.assertTrue(result["valid"])
