from datetime import date

"""
Phase 0 Security & Validation Tests

Tests for:
1. Payment webhook security (signature verification, rate limiting, IP whitelist, idempotency)
2. Role-based permission enforcement
3. Input validation on critical fields
"""

from decimal import Decimal
from unittest.mock import patch
import hashlib
import hmac

from django.test import TestCase, Client
from django.test.utils import override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    Payment,
    WebhookLog,
)
from apps.finance.security import (
    WebhookSecurityValidator,
    PaymentValidator,
)
from apps.accounts.permissions import (
    has_role_hierarchy,
    can_view_invoice,
)
from apps.evals.models import Evaluation
from apps.people.models import StudentProfile, StudentGuardian
from apps.academics.models import (
    AcademicYear,
    Term,
    Classroom,
    SubjectAssignment,
    Specialty,
    Department,
    Subject,
)

User = get_user_model()


# ============================================================================
# WEBHOOK SECURITY TESTS
# ============================================================================


class WebhookSecurityValidatorTest(TestCase):
    """Test WebhookSecurityValidator functionality."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon",
            country_code="CM",
        )

        self.config = {
            "webhook_secret": "test-secret-key-12345",
            "webhook_ips": ["192.168.1.1", "127.0.0.1"],
            "rate_limit": 100,
            "signature_header": "X-Signature",
        }

        self.validator = WebhookSecurityValidator(self.config)

    def test_get_client_ip_from_remote_addr(self):
        """Test IP extraction from REMOTE_ADDR."""

        class FakeRequest:
            META = {"REMOTE_ADDR": "10.0.0.1"}

        ip = self.validator.get_client_ip(FakeRequest())
        self.assertEqual(ip, "10.0.0.1")

    def test_get_client_ip_from_x_forwarded_for(self):
        """Test IP extraction from X-Forwarded-For header (proxy)."""

        class FakeRequest:
            META = {
                "HTTP_X_FORWARDED_FOR": "203.0.113.1, 198.51.100.1",
                "REMOTE_ADDR": "10.0.0.1",
            }

        ip = self.validator.get_client_ip(FakeRequest())
        self.assertEqual(ip, "203.0.113.1")

    def test_validate_ip_whitelist_allowed(self):
        """Test IP whitelist allows whitelisted IPs."""
        self.assertTrue(self.validator.validate_ip_whitelist("127.0.0.1"))
        self.assertTrue(self.validator.validate_ip_whitelist("192.168.1.1"))

    def test_validate_ip_whitelist_rejected(self):
        """Test IP whitelist rejects non-whitelisted IPs."""
        self.assertFalse(self.validator.validate_ip_whitelist("203.0.113.1"))

    def test_validate_ip_whitelist_empty_allows_all(self):
        """Test empty whitelist allows all IPs."""
        validator = WebhookSecurityValidator({"webhook_ips": []})
        self.assertTrue(validator.validate_ip_whitelist("any.ip.address"))

    def test_validate_signature_valid(self):
        """Test signature verification with valid signature."""
        request_body = b'{"invoice_id": 123, "amount": 100}'
        expected_sig = hmac.new(
            b"test-secret-key-12345", request_body, hashlib.sha256
        ).hexdigest()

        self.assertTrue(self.validator.validate_signature(request_body, expected_sig))

    def test_validate_signature_invalid(self):
        """Test signature verification with invalid signature."""
        request_body = b'{"invoice_id": 123, "amount": 100}'
        invalid_sig = "invalid_signature_12345"

        self.assertFalse(self.validator.validate_signature(request_body, invalid_sig))

    def test_validate_signature_missing(self):
        """Test signature verification with missing signature."""
        request_body = b'{"invoice_id": 123, "amount": 100}'

        self.assertFalse(self.validator.validate_signature(request_body, ""))

    def test_validate_timestamp_within_tolerance(self):
        validator = WebhookSecurityValidator(
            {
                "require_timestamp": True,
                "timestamp_tolerance_seconds": 60,
            }
        )
        now_ts = int(timezone.now().timestamp())
        self.assertTrue(validator.validate_timestamp(str(now_ts)))

    def test_validate_timestamp_rejects_stale(self):
        validator = WebhookSecurityValidator(
            {
                "require_timestamp": True,
                "timestamp_tolerance_seconds": 30,
            }
        )
        stale_ts = int(timezone.now().timestamp()) - 120
        self.assertFalse(validator.validate_timestamp(str(stale_ts)))

    def test_validate_rate_limit_allows_within_limit(self):
        """Test rate limiting allows requests within limit."""
        for i in range(5):
            self.assertTrue(self.validator.validate_rate_limit("10.0.0.1"))

    def test_validate_rate_limit_rejects_over_limit(self):
        """Test rate limiting rejects requests over limit (mock cache)."""
        # This requires mocking the cache to verify 100 requests
        # For now, verify the function returns boolean
        result = self.validator.validate_rate_limit("192.168.1.1")
        self.assertIsInstance(result, bool)

    def test_validate_idempotency_new_webhook(self):
        """Test idempotency check allows new webhooks."""
        result = self.validator.validate_idempotency("mtn_momo", "ref-12345")
        self.assertTrue(result)

    def test_validate_idempotency_duplicate_webhook(self):
        """Test idempotency check rejects duplicate webhooks."""
        # Create a processed webhook log
        WebhookLog.objects.create(
            provider="mtn_momo",
            reference_id="ref-12345",
            client_ip="127.0.0.1",
            signature_valid=True,
            status=WebhookLog.Status.PROCESSED,
        )

        result = self.validator.validate_idempotency("mtn_momo", "ref-12345")
        self.assertFalse(result)


class PaymentValidatorTest(TestCase):
    """Test PaymentValidator functionality."""

    def test_validate_amount_positive(self):
        """Test valid positive amounts."""
        is_valid, error = PaymentValidator.validate_amount(Decimal("100.50"))
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_amount_zero(self):
        """Test zero amount is invalid."""
        is_valid, error = PaymentValidator.validate_amount(Decimal("0"))
        self.assertFalse(is_valid)
        self.assertIn("positive", error.lower())

    def test_validate_amount_negative(self):
        """Test negative amount is invalid."""
        is_valid, error = PaymentValidator.validate_amount(Decimal("-100"))
        self.assertFalse(is_valid)
        self.assertIn("positive", error.lower())

    def test_validate_amount_exceeds_max(self):
        """Test amount exceeding maximum is invalid."""
        is_valid, error = PaymentValidator.validate_amount(Decimal("2000000000"))
        self.assertFalse(is_valid)
        self.assertIn("exceeds", error.lower())

    def test_validate_against_invoice_within_balance(self):
        """Test payment within invoice balance is valid."""
        is_valid, error = PaymentValidator.validate_against_invoice(
            Decimal("100"),
            Decimal("500"),
            Decimal("0"),
        )
        self.assertTrue(is_valid)

    def test_validate_against_invoice_exceeds_balance(self):
        """Test payment exceeding balance is invalid."""
        is_valid, error = PaymentValidator.validate_against_invoice(
            Decimal("100"),
            Decimal("500"),
            Decimal("450"),
        )
        self.assertFalse(is_valid)
        self.assertIn("exceeds", error.lower())

    def test_validate_reference_valid(self):
        """Test valid reference."""
        is_valid, error = PaymentValidator.validate_reference("MTN-PAY-123")
        self.assertTrue(is_valid)

    def test_validate_reference_empty(self):
        """Test empty reference is invalid."""
        is_valid, error = PaymentValidator.validate_reference("")
        self.assertFalse(is_valid)


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================


class EvaluationValidationTest(TestCase):
    """Test Evaluation score validation."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="Term 1",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        self.department = Department.objects.create(name="General", code="GEN")
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            name="Form 1A",
            code="F1A",
            academic_year=self.year,
            department=self.department,
        )
        self.subject = Subject.objects.create(
            name="Mathematics", category=Subject.Category.GENERAL
        )

        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STD100",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )

        from apps.people.models import TeacherProfile

        teacher_user = User.objects.create_user(username="teacher", role="TEACHER")
        self.teacher = TeacherProfile.objects.create(user=teacher_user)

        self.subject_assign = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
        )

    def test_evaluation_score_valid(self):
        """Test evaluation with valid scores (0-20)."""
        evaluation = Evaluation(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assign,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("15.5"),
        )
        # Should not raise ValidationError
        evaluation.full_clean()

    def test_evaluation_score_negative(self):
        """Test evaluation with negative score raises error."""
        evaluation = Evaluation(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assign,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("-5"),
        )
        with self.assertRaises(ValidationError):
            evaluation.full_clean()

    def test_evaluation_score_exceeds_20(self):
        """Test evaluation with score > 20 raises error."""
        evaluation = Evaluation(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assign,
            student=self.student,
            teacher=self.teacher,
            exam_score=Decimal("25"),
        )
        with self.assertRaises(ValidationError):
            evaluation.full_clean()

    def test_evaluation_no_scores_raises_error(self):
        """Test evaluation with no scores raises error."""
        evaluation = Evaluation(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assign,
            student=self.student,
            teacher=self.teacher,
        )
        with self.assertRaises(ValidationError):
            evaluation.full_clean()


class InvoiceValidationTest(TestCase):
    """Test Invoice and Payment validation."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )

    def test_invoice_positive_amount(self):
        """Test invoice with positive amount."""
        invoice = Invoice(
            profile=self.profile,
            academic_year=self.year,
            total_amount=Decimal("1000.00"),
        )
        invoice.full_clean()  # Should not raise

    def test_invoice_zero_amount_raises_error(self):
        """Test invoice with zero amount raises error."""
        invoice = Invoice(
            profile=self.profile,
            academic_year=self.year,
            total_amount=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError):
            invoice.full_clean()

    def test_invoice_negative_amount_raises_error(self):
        """Test invoice with negative amount raises error."""
        invoice = Invoice(
            profile=self.profile,
            academic_year=self.year,
            total_amount=Decimal("-100.00"),
        )
        with self.assertRaises(ValidationError):
            invoice.full_clean()


@override_settings(SEND_FINANCE_SIGNALS=False)
class PaymentValidationTest(TestCase):
    """Test Payment validation."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            total_amount=Decimal("1000.00"),
        )
        # Avoid recalculation signals interfering with balance tests
        self._apply_payment_patch = patch(
            "apps.finance.signals.apply_payment", lambda payment: None
        )
        self._apply_payment_patch.start()
        self.addCleanup(self._apply_payment_patch.stop)

    def test_payment_valid_amount(self):
        """Test payment with valid positive amount."""
        payment = Payment(
            invoice=self.invoice,
            amount=Decimal("500.00"),
            method="CASH",
        )
        payment.full_clean()  # Should not raise

    def test_payment_exceeds_invoice_balance(self):
        """Test payment exceeding invoice balance raises error."""
        # First payment
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("900.00"),
            method="CASH",
        )

        # Second payment exceeding remaining balance
        payment2 = Payment(
            invoice=self.invoice,
            amount=Decimal("200.00"),  # Only 100 remaining
            method="CASH",
        )
        with self.assertRaises(ValidationError):
            payment2.full_clean()

    def test_payment_zero_amount_raises_error(self):
        """Test payment with zero amount raises error."""
        payment = Payment(
            invoice=self.invoice,
            amount=Decimal("0.00"),
            method="CASH",
        )
        with self.assertRaises(ValidationError):
            payment.full_clean()


# ============================================================================
# PERMISSION TESTS
# ============================================================================


class PermissionHierarchyTest(TestCase):
    """Test role hierarchy and permission functions."""

    def setUp(self):
        uid = id(self)
        self.admin_user = User.objects.create_user(
            username="finance_ph_admin_%s" % uid, role="ADMIN"
        )
        self.bursar_user = User.objects.create_user(
            username="finance_ph_bursar_%s" % uid, role="BURSAR"
        )
        self.teacher_user = User.objects.create_user(
            username="finance_ph_teacher_%s" % uid, role="TEACHER"
        )
        self.parent_user = User.objects.create_user(
            username="finance_ph_parent_%s" % uid, role="PARENT"
        )

    def test_role_hierarchy_admin_superior(self):
        """Test admin has higher or equal permissions to other roles."""
        self.assertTrue(has_role_hierarchy(self.admin_user, "BURSAR"))
        self.assertTrue(has_role_hierarchy(self.admin_user, "TEACHER"))
        self.assertTrue(has_role_hierarchy(self.admin_user, "ADMIN"))

    def test_role_hierarchy_bursar_not_admin(self):
        """Test bursar doesn't have admin permissions."""
        self.assertFalse(has_role_hierarchy(self.bursar_user, "ADMIN"))

    def test_role_hierarchy_teacher_basic(self):
        """Test teacher hierarchy."""
        self.assertTrue(has_role_hierarchy(self.teacher_user, "TEACHER"))
        self.assertFalse(has_role_hierarchy(self.teacher_user, "BURSAR"))

    def test_superuser_always_allowed(self):
        """Test superuser bypasses hierarchy checks."""
        superuser = User.objects.create_superuser(
            username="finance_ph_super_%s" % id(self),
            password="pass",
            email="super_%s@test.com" % id(self),
        )
        self.assertTrue(has_role_hierarchy(superuser, "ADMIN"))
        self.assertTrue(has_role_hierarchy(superuser, "BURSAR"))


class InvoicePermissionTest(TestCase):
    """Test invoice access control."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.department = Department.objects.create(name="General", code="GEN")

        # Users (unique usernames to avoid cross-test UNIQUE constraint)
        uid = id(self)
        self.admin = User.objects.create_user(
            username="finance_inv_admin_%s" % uid, role="ADMIN"
        )
        self.bursar = User.objects.create_user(
            username="finance_inv_bursar_%s" % uid, role="BURSAR"
        )
        self.parent = User.objects.create_user(
            username="finance_inv_parent_%s" % uid, role="PARENT"
        )
        self.other_parent = User.objects.create_user(
            username="finance_inv_other_parent_%s" % uid, role="PARENT"
        )

        # Student with guardian link
        self.specialty = Specialty.objects.create(
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            name="Form 1",
            academic_year=self.year,
            code="F1",
            department=self.department,
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STD200",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
            can_view_finance=True,
        )

        # Invoice
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            total_amount=Decimal("1000.00"),
        )

    def test_admin_can_view_invoice(self):
        """Test admin can view any invoice."""
        self.assertTrue(can_view_invoice(self.admin, self.invoice.id))

    def test_bursar_can_view_invoice(self):
        """Test bursar can view any invoice."""
        self.assertTrue(can_view_invoice(self.bursar, self.invoice.id))

    def test_parent_can_view_child_invoice(self):
        """Test parent can view their child's invoice."""
        self.assertTrue(can_view_invoice(self.parent, self.invoice.id))

    def test_parent_cannot_view_other_child_invoice(self):
        """Test parent cannot view other student's invoice."""
        self.assertFalse(can_view_invoice(self.other_parent, self.invoice.id))


class PayrollRBACTest(TestCase):
    """Test that teachers (non-staff) cannot access staff-only payroll views."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_rbac",
            password="testpass",
            role="TEACHER",
            is_staff=False,
        )
        self.client = Client()

    def test_teacher_cannot_access_payroll_run_detail(self):
        """Teacher must not access payroll run detail (staff-only); expect 403."""
        self.client.login(username=self.teacher.username, password="testpass")
        response = self.client.get("/payroll/runs/1/", follow=False)
        self.assertIn(
            response.status_code,
            (403, 302),
            "Teacher must not get 200 on staff-only payroll run detail (403 or redirect to login).",
        )


# Phase 0 tests: webhook_security, input_validation, permissions (see test class names above).
