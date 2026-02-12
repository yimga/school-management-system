"""
Security validators and utilities for payment webhook processing.

Includes:
- WebhookSecurityValidator: IP whitelist, rate limiting, signature verification
- PaymentValidator: Amount and invoice validation
"""

import hashlib
import hmac
import logging
from decimal import Decimal, InvalidOperation
from functools import wraps
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


class PaymentEncryption:
    """
    Lightweight masking/hashing helpers for payment metadata.
    """

    @staticmethod
    def encrypt_card_number(card_number: str) -> str:
        """
        Mask card number while preserving only last four digits.
        """
        if not card_number:
            return ""
        normalized = "".join(ch for ch in str(card_number) if ch.isdigit())
        if len(normalized) <= 4:
            return normalized
        masked = "*" * (len(normalized) - 4)
        return f"{masked}{normalized[-4:]}"

    @staticmethod
    def hash_payment_token(token: str) -> str:
        """
        One-way hash for transient payment tokens.
        """
        secret = getattr(settings, "SECRET_KEY", "")
        payload = f"{secret}:{token or ''}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class WebhookSecurityValidator:
    """
    Validates incoming payment webhooks for security.
    
    Checks:
    - IP whitelist (provider's known IPs)
    - Rate limiting (max requests per minute per IP)
    - HMAC-SHA256 signature verification (timing-safe)
    - Idempotency (prevents duplicate payment processing)
    """

    def __init__(self, provider_config: dict):
        """
        Args:
            provider_config: Dict with keys:
                - 'webhook_ips': list of allowed IPs
                - 'webhook_secret': API key for HMAC signing
                - 'rate_limit': requests per minute (default: 100)
        """
        self.webhook_ips = provider_config.get("webhook_ips", [])
        self.webhook_secret = provider_config.get("webhook_secret", "")
        self.rate_limit = provider_config.get("rate_limit", 100)

    @staticmethod
    def get_client_ip(request: HttpRequest) -> str:
        """Extract client IP from request, handling proxies."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "")
        return ip

    def validate_ip_whitelist(self, client_ip: str) -> bool:
        """Check if client IP is in whitelist.
        
        Args:
            client_ip: IP address from request
            
        Returns:
            True if IP is whitelisted or whitelist is empty (disabled)
        """
        if not self.webhook_ips:
            return True  # Whitelist disabled
        
        is_allowed = client_ip in self.webhook_ips
        if not is_allowed:
            logger.warning(f"Webhook IP not whitelisted: {client_ip}")
        return is_allowed

    def validate_rate_limit(self, client_ip: str) -> bool:
        """
        Check rate limit for client IP.
        Uses cache to track request count per minute.
        
        Args:
            client_ip: IP address from request
            
        Returns:
            True if request is within limit
        """
        cache_key = f"webhook_rate_limit:{client_ip}"
        current_count = cache.get(cache_key, 0)
        
        if current_count >= self.rate_limit:
            logger.warning(f"Webhook rate limit exceeded for {client_ip}: {current_count}/{self.rate_limit}")
            return False
        
        # Increment and set 60-second expiry
        cache.set(cache_key, current_count + 1, 60)
        return True

    def validate_signature(
        self,
        request_body: bytes,
        signature_header: str,
        signature_algorithm: str = "sha256"
    ) -> bool:
        """
        Verify HMAC signature using timing-safe comparison.
        
        Args:
            request_body: Raw request body bytes
            signature_header: Signature from request header
            signature_algorithm: Hash algorithm (default: sha256)
            
        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logger.warning("Webhook secret not configured, skipping signature check")
            return False
        
        if not signature_header:
            logger.warning("No signature provided in webhook request")
            return False
        
        # Compute expected signature
        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                request_body,
                getattr(hashlib, signature_algorithm)
            ).hexdigest()
        except (ValueError, AttributeError):
            logger.error(f"Invalid signature algorithm: {signature_algorithm}")
            return False
        
        # Timing-safe comparison (prevents timing attacks)
        is_valid = hmac.compare_digest(signature_header, expected_signature)
        
        if not is_valid:
            logger.warning(
                f"Webhook signature mismatch. Expected: {expected_signature[:8]}..., "
                f"Got: {signature_header[:8]}..."
            )
        
        return is_valid

    def validate_idempotency(self, provider: str, reference_id: str) -> bool:
        """
        Check if webhook has already been processed.
        Uses WebhookLog to prevent duplicate payments.
        
        Args:
            provider: Payment provider slug (mtm_momo, orange_money, etc.)
            reference_id: External payment reference
            
        Returns:
            True if this is a new webhook (not processed before)
        """
        from .models import WebhookLog
        
        # Check if this reference was already processed successfully
        duplicate = WebhookLog.objects.filter(
            provider=provider,
            reference_id=reference_id,
            status__in=["PROCESSED", "DUPLICATE"]
        ).exists()
        
        if duplicate:
            logger.info(f"Duplicate webhook detected: {provider} {reference_id}")
            return False
        
        return True


class PaymentValidator:
    """Validates payment data before recording in database."""

    @staticmethod
    def validate_amount(amount: Decimal) -> tuple[bool, Optional[str]]:
        """
        Validate payment amount.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            amount_decimal = Decimal(str(amount))
        except Exception:
            return False, "Amount must be a valid decimal number"
        
        if amount_decimal <= 0:
            return False, f"Amount must be positive, got {amount_decimal}"
        
        # Practical limit: 1 billion XAF (~1.6M USD)
        if amount_decimal > Decimal("1000000000"):
            return False, f"Amount exceeds maximum limit: {amount_decimal}"
        
        return True, None

    @staticmethod
    def validate_against_invoice(
        amount: Decimal,
        invoice_total: Decimal,
        invoice_paid: Decimal,
    ) -> tuple[bool, Optional[str]]:
        return FraudDetector.validate_against_invoice(amount, invoice_total, invoice_paid)

    @staticmethod
    def validate_reference(reference: str, max_length: int = 128) -> tuple[bool, Optional[str]]:
        return FraudDetector.validate_reference(reference, max_length)



class FraudDetector:
    """
    Lightweight fraud detection that scores payments based on known risk patterns.

    Patterns include amount, velocity, geographic anomalies, and new cards.
    Scores are capped at 100 to keep thresholds easy to reason about.
    """

    AMOUNT_THRESHOLD = Decimal("100000")
    MAX_SCORE = 100
    SCORE_WEIGHTS = {
        "amount": 40,
        "high_velocity": 20,
        "geographic_anomaly": 20,
        "new_card": 20,
    }

    @classmethod
    def check_amount_risk(cls, amount) -> bool:
        """Flag payments whose amount exceeds the configured threshold."""
        if amount is None:
            return False

        try:
            amount_decimal = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            return False

        return amount_decimal >= cls.AMOUNT_THRESHOLD

    @classmethod
    def calculate_fraud_score(cls, payment_data: dict) -> int:
        """
        Score a payment request based on individual risk drivers.
        Each flagged pattern adds a chunk of the total score until we hit MAX_SCORE.
        """
        score = 0

        if cls.check_amount_risk(payment_data.get("amount")):
            score += cls.SCORE_WEIGHTS["amount"]

        for flag in ("high_velocity", "geographic_anomaly", "new_card"):
            if payment_data.get(flag):
                score += cls.SCORE_WEIGHTS[flag]

        return min(score, cls.MAX_SCORE)

    @staticmethod
    def validate_against_invoice(
        amount: Decimal,
        invoice_total: Decimal,
        invoice_paid: Decimal
    ) -> tuple[bool, Optional[str]]:
        """
        Validate payment doesn't exceed invoice balance.
        
        Args:
            amount: Payment amount
            invoice_total: Invoice total
            invoice_paid: Amount already paid
            
        Returns:
            (is_valid, error_message)
        """
        remaining_balance = invoice_total - invoice_paid
        
        if amount > remaining_balance:
            return (
                False,
                f"Payment {amount} exceeds remaining balance {remaining_balance}"
            )
        
        return True, None

    @staticmethod
    def validate_reference(reference: str, max_length: int = 128) -> tuple[bool, Optional[str]]:
        """
        Validate payment reference string.
        
        Returns:
            (is_valid, error_message)
        """
        if not reference or len(reference) == 0:
            return False, "Reference is required"
        
        if len(reference) > max_length:
            return False, f"Reference exceeds {max_length} characters"
        
        return True, None


def webhook_security_required(view_func):
    """
    Decorator for webhook views that enforces security checks.
    
    Checks: HTTP method, IP whitelist, rate limit, signature.
    
    Usage:
        @webhook_security_required
        def payment_provider_webhook(request, provider_slug):
            ...
    """
    @require_http_methods(["POST"])
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        from .models import PaymentIntegration, WebhookLog
        
        provider_slug = kwargs.get("provider_slug")
        if not provider_slug:
            provider_slug = args[1] if len(args) > 1 else None
        
        if not provider_slug:
            logger.error("No provider_slug in webhook request")
            return HttpResponseForbidden("Invalid request")
        
        # Get provider config
        try:
            integration = PaymentIntegration.objects.get(code=provider_slug, is_active=True)
        except PaymentIntegration.DoesNotExist:
            logger.warning(f"Unknown payment provider: {provider_slug}")
            return HttpResponseForbidden("Unknown provider")
        
        # Create validator
        validator = WebhookSecurityValidator(integration.config)
        client_ip = validator.get_client_ip(request)
        
        # Step 1: IP whitelist check
        if not validator.validate_ip_whitelist(client_ip):
            return HttpResponseForbidden("IP not whitelisted")
        
        # Step 2: Rate limiting check
        if not validator.validate_rate_limit(client_ip):
            return HttpResponse("Rate limit exceeded", status=429)
        
        # Step 3: Signature verification
        signature_header = integration.config.get("signature_header", "X-Signature")
        signature = (
            request.headers.get(signature_header)
            or request.META.get(f"HTTP_{signature_header.upper().replace('-', '_')}")
        )
        
        if not validator.validate_signature(request.body, signature or ""):
            logger.warning(f"Invalid webhook signature from {provider_slug} ({client_ip})")
            return HttpResponseForbidden("Invalid signature")
        
        # Log webhook receipt
        try:
            import json
            data = json.loads(request.body.decode() or "{}")
            reference_id = data.get("reference") or data.get("payment_reference") or "unknown"
            
            WebhookLog.objects.create(
                provider=provider_slug,
                reference_id=reference_id,
                client_ip=client_ip,
                signature_valid=True,
                status="RECEIVED",
                request_body=request.body.decode(),
            )
        except Exception as e:
            logger.error(f"Failed to log webhook: {e}")
        
        # Call the actual view
        return view_func(request, *args, **kwargs)
    
    return _wrapped
