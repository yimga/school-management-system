"""Phase 2.0 Payment Processing Tests"""
from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from apps.siteconfig.models import RegionConfig
from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.finance.payment_models import (
    PaymentMethod, Payment, Transaction, RefundRequest, 
    PaymentReconciliation, PaymentAuditLog
)
from apps.finance.payment_validators import (
    AmountValidator, CurrencyValidator, PaymentMethodValidator,
    RefundValidator, CompliancePaymentValidator
)
from apps.finance.payment_processors import PaymentProcessorFactory


class PaymentMethodTestCase(TestCase):
    """Test payment method models."""
    
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='Test', code='TST', default_language='en', timezone='UTC'
        )
        self.user = User.objects.create_user('admin', 'admin@test.com', 'pass')
    
    def test_payment_method_creation(self):
        """Test creating payment method."""
        method = PaymentMethod.objects.create(
            name='Card Payment', method_type='card', gateway='stripe',
            region=self.region, created_by=self.user,
            transaction_fee_percent=Decimal('2.5'), fixed_fee=Decimal('0.30')
        )
        self.assertEqual(method.name, 'Card Payment')
        self.assertTrue(method.is_active)
    
    def test_calculate_fee(self):
        """Test fee calculation."""
        method = PaymentMethod.objects.create(
            name='Card Payment', method_type='card', gateway='stripe',
            region=self.region, created_by=self.user,
            transaction_fee_percent=Decimal('2.5'), fixed_fee=Decimal('0.30')
        )
        amount = Decimal('100.00')
        fee = method.calculate_fee(amount)
        self.assertEqual(fee, Decimal('2.80'))


class PaymentTestCase(TestCase):
    """Test payment models."""
    
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='Test', code='TST', default_language='en', timezone='UTC'
        )
        self.user = User.objects.create_user('admin', 'admin@test.com', 'pass')
        self.method = PaymentMethod.objects.create(
            name='Card', method_type='card', gateway='stripe',
            region=self.region, created_by=self.user
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            admission_number="STU001",
        )
    
    def test_payment_creation(self):
        """Test creating payment."""
        payment = Payment.objects.create(
            reference_number='PAY001',
            student=self.student,
            region=self.region,
            payment_method=self.method,
            amount=Decimal('500.00'),
            currency_code='USD',
            purpose='tuition'
        )
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.amount, Decimal('500.00'))
    
    def test_mark_processing(self):
        """Test marking payment as processing."""
        payment = Payment.objects.create(
            reference_number='PAY001',
            student=self.student,
            region=self.region,
            payment_method=self.method,
            amount=Decimal('500.00'),
            currency_code='USD',
            purpose='tuition'
        )
        payment.mark_processing()
        self.assertEqual(payment.status, 'processing')
        self.assertIsNotNone(payment.initiated_at)
    
    def test_mark_completed(self):
        """Test marking payment as completed."""
        payment = Payment.objects.create(
            reference_number='PAY001',
            student=self.student,
            region=self.region,
            payment_method=self.method,
            amount=Decimal('500.00'),
            currency_code='USD',
            purpose='tuition'
        )
        payment.mark_completed(gateway_tx_id='tx_123')
        self.assertEqual(payment.status, 'completed')
        self.assertEqual(payment.gateway_transaction_id, 'tx_123')


class PaymentAuditLoggingTestCase(TestCase):
    """Ensure status changes emit audit entries."""

    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='Audit', code='AUD', default_language='en', timezone='UTC'
        )
        self.user = User.objects.create_user('auditor', 'audit@test.com', 'pass')
        self.method = PaymentMethod.objects.create(
            name='Audit Card', method_type='card', gateway='stripe',
            region=self.region, created_by=self.user
        )
        self.student = StudentProfile.objects.create(
            user=self.user, admission_number='AUD001'
        )
        self.payment = Payment.objects.create(
            reference_number='AUDPAY',
            student=self.student,
            region=self.region,
            payment_method=self.method,
            amount=Decimal('250.00'),
            currency_code='USD',
            purpose='tuition'
        )

    def test_mark_processing_logs_audit(self):
        self.payment.mark_processing()
        log = PaymentAuditLog.objects.filter(
            payment=self.payment,
            action_type='payment_initiated'
        ).last()
        self.assertIsNotNone(log)
        self.assertEqual(log.severity, 'medium')
        self.assertEqual(log.region, self.region)
        self.assertEqual(log.details.get('status'), 'processing')

    def test_mark_completed_logs_audit(self):
        self.payment.mark_completed(gateway_tx_id='tx_audit')
        log = PaymentAuditLog.objects.filter(
            payment=self.payment,
            action_type='payment_completed'
        ).last()
        self.assertIsNotNone(log)
        self.assertEqual(log.details.get('gateway_transaction_id'), 'tx_audit')
        self.assertEqual(log.severity, 'low')

    def test_mark_failed_logs_audit(self):
        self.payment.mark_failed(reason='test failure')
        log = PaymentAuditLog.objects.filter(
            payment=self.payment,
            action_type='payment_failed'
        ).last()
        self.assertIsNotNone(log)
        self.assertEqual(log.severity, 'high')
        self.assertIn('reason', log.details)
        self.assertEqual(log.details.get('reason'), 'test failure')


class TransactionTestCase(TestCase):
    """Test transaction models."""
    
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='Test', code='TST', default_language='en', timezone='UTC'
        )
        self.user = User.objects.create_user('admin', 'admin@test.com', 'pass')
        self.method = PaymentMethod.objects.create(
            name='Card', method_type='card', gateway='stripe',
            region=self.region, created_by=self.user
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            admission_number="STU001",
        )
        self.payment = Payment.objects.create(
            reference_number='PAY001',
            student=self.student,
            region=self.region,
            payment_method=self.method,
            amount=Decimal('500.00'),
            currency_code='USD',
            purpose='tuition'
        )
    
    def test_transaction_creation(self):
        """Test creating transaction."""
        trans = Transaction.objects.create(
            payment=self.payment,
            transaction_type='payment',
            amount=Decimal('500.00'),
            currency='USD',
            status='success'
        )
        self.assertEqual(trans.status, 'success')


class AmountValidatorTestCase(TestCase):
    """Test amount validation."""
    
    def test_valid_amount(self):
        """Test valid amount."""
        validator = AmountValidator()
        self.assertTrue(validator.validate_amount(Decimal('100.00')))
    
    def test_zero_amount(self):
        """Test zero amount fails."""
        validator = AmountValidator()
        self.assertFalse(validator.validate_amount(Decimal('0.00')))
    
    def test_negative_amount(self):
        """Test negative amount fails."""
        validator = AmountValidator()
        self.assertFalse(validator.validate_amount(Decimal('-100.00')))
    
    def test_amount_below_minimum(self):
        """Test amount below minimum."""
        validator = AmountValidator()
        self.assertFalse(validator.validate_amount(Decimal('0.001'), min_amount=Decimal('0.01')))
    
    def test_amount_above_maximum(self):
        """Test amount above maximum."""
        validator = AmountValidator()
        self.assertFalse(validator.validate_amount(Decimal('1000.00'), max_amount=Decimal('500.00')))


class CurrencyValidatorTestCase(TestCase):
    """Test currency validation."""
    
    def test_valid_currency(self):
        """Test valid currency."""
        validator = CurrencyValidator()
        self.assertTrue(validator.validate_currency('USD'))
    
    def test_invalid_length(self):
        """Test invalid length."""
        validator = CurrencyValidator()
        self.assertFalse(validator.validate_currency('US'))
    
    def test_empty_currency(self):
        """Test empty currency."""
        validator = CurrencyValidator()
        self.assertFalse(validator.validate_currency(''))


class PaymentMethodValidatorTestCase(TestCase):
    """Test payment method validation."""
    
    def test_validate_api_configuration_valid(self):
        """Test valid API configuration."""
        validator = PaymentMethodValidator()
        self.assertTrue(validator.validate_api_configuration(
            'stripe', 'sk_test_123456789', 'secret_123456789'
        ))
    
    def test_validate_api_configuration_manual(self):
        """Test manual gateway doesn't need API."""
        validator = PaymentMethodValidator()
        self.assertTrue(validator.validate_api_configuration('manual', '', ''))
    
    def test_validate_fees_valid(self):
        """Test valid fees."""
        validator = PaymentMethodValidator()
        self.assertTrue(validator.validate_fees(Decimal('2.5'), Decimal('0.30')))
    
    def test_validate_fees_invalid_percent(self):
        """Test invalid fee percent."""
        validator = PaymentMethodValidator()
        self.assertFalse(validator.validate_fees(Decimal('150'), Decimal('0.30')))


class RefundValidatorTestCase(TestCase):
    """Test refund validation."""
    
    def test_valid_refund_amount(self):
        """Test valid refund amount."""
        validator = RefundValidator()
        self.assertTrue(validator.validate_refund_amount(Decimal('500.00'), Decimal('250.00')))
    
    def test_refund_exceeds_payment(self):
        """Test refund exceeding payment."""
        validator = RefundValidator()
        self.assertFalse(validator.validate_refund_amount(Decimal('500.00'), Decimal('600.00')))
    
    def test_valid_refund_reason(self):
        """Test valid refund reason."""
        validator = RefundValidator()
        self.assertTrue(validator.validate_refund_reason('duplicate'))
    
    def test_invalid_refund_reason(self):
        """Test invalid refund reason."""
        validator = RefundValidator()
        self.assertFalse(validator.validate_refund_reason('invalid'))


class PaymentProcessorFactoryTestCase(TestCase):
    """Test payment processor factory."""
    
    def test_stripe_processor(self):
        """Test Stripe processor creation."""
        processor = PaymentProcessorFactory.get_processor('stripe', 'key', 'secret')
        result = processor.charge(Decimal('100.00'), 'USD', 'ref123', {})
        self.assertEqual(result['status'], 'success')
    
    def test_paypal_processor(self):
        """Test PayPal processor creation."""
        processor = PaymentProcessorFactory.get_processor('paypal', 'key', 'secret')
        result = processor.charge(Decimal('100.00'), 'USD', 'ref123', {})
        self.assertEqual(result['status'], 'success')
    
    def test_unknown_processor(self):
        """Test unknown processor raises error."""
        with self.assertRaises(ValueError):
            PaymentProcessorFactory.get_processor('unknown', 'key', 'secret')


class RefundRequestTestCase(TestCase):
    """Test refund request models."""
    
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='Test', code='TST', default_language='en', timezone='UTC'
        )
        self.user = User.objects.create_user('admin', 'admin@test.com', 'pass')
        self.method = PaymentMethod.objects.create(
            name='Card', method_type='card', gateway='stripe',
            region=self.region, created_by=self.user
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            admission_number="STU001",
        )
        self.payment = Payment.objects.create(
            reference_number='PAY001',
            student=self.student,
            region=self.region,
            payment_method=self.method,
            amount=Decimal('500.00'),
            currency_code='USD',
            purpose='tuition'
        )
    
    def test_refund_request_creation(self):
        """Test creating refund request."""
        refund = RefundRequest.objects.create(
            payment=self.payment,
            region=self.region,
            amount=Decimal('250.00'),
            reason='duplicate',
            description='Accidental duplicate',
            requested_by=self.user
        )
        self.assertEqual(refund.status, 'pending')
        self.assertEqual(refund.amount, Decimal('250.00'))


class PaymentAuditLogTestCase(TestCase):
    """Test payment audit logs."""
    
    def setUp(self):
        self.region = RegionConfig.objects.create(
            name='Test', code='TST', default_language='en', timezone='UTC'
        )
        self.user = User.objects.create_user('admin', 'admin@test.com', 'pass')
    
    def test_audit_log_creation(self):
        """Test creating audit log."""
        log = PaymentAuditLog.objects.create(
            action_type='payment_created',
            region=self.region,
            description='Payment created',
            user=self.user,
            severity='low'
        )
        self.assertEqual(log.action_type, 'payment_created')
        self.assertEqual(log.severity, 'low')
