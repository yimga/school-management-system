"""
Webhook security utilities for payment integrations.

Implements IP whitelisting, rate limiting, idempotency tokens,
and request logging for CSRF-exempt webhook endpoints.
"""
from __future__ import annotations

import logging
import hashlib
from typing import Optional
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseForbidden

try:
    from django.http import HttpResponseTooManyRequests
except ImportError:
    from django.http import HttpResponse

    class HttpResponseTooManyRequests(HttpResponse):
        status_code = 429

from apps.siteconfig.models import Integration

logger = logging.getLogger("finance.webhooks")


class WebhookSecurityException(Exception):
    """Base exception for webhook security violations."""
    pass


class IPWhitelistViolation(WebhookSecurityException):
    """Raised when request IP is not whitelisted."""
    pass


class RateLimitExceeded(WebhookSecurityException):
    """Raised when rate limit is exceeded."""
    pass


class IdempotencyViolation(WebhookSecurityException):
    """Raised when idempotency check fails."""
    pass


def get_client_ip(request: HttpRequest) -> str:
    """
    Extract client IP from request, handling proxies.
    
    Checks X-Forwarded-For, X-Real-IP, and REMOTE_ADDR in order.
    Returns the first non-private IP or the direct connection IP.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ips = [ip.strip() for ip in x_forwarded_for.split(",")]
        # Return first IP that looks like it came from outside
        for ip in ips:
            if ip and not _is_private_ip(ip):
                return ip
        # Fall back to last IP in chain if all are private (trust chain)
        return ips[-1] if ips else request.META.get("REMOTE_ADDR", "")
    
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip:
        return x_real_ip
    
    return request.META.get("REMOTE_ADDR", "")


def _is_private_ip(ip: str) -> bool:
    """Check if IP address is private/reserved."""
    parts = ip.split(".")
    if len(parts) != 4:
        return True  # Invalid format, treat as private
    try:
        octets = [int(p) for p in parts]
        # Private ranges: 10.x.x.x, 172.16-31.x.x, 192.168.x.x, 127.x.x.x
        return (
            octets[0] == 10
            or (octets[0] == 172 and 16 <= octets[1] <= 31)
            or (octets[0] == 192 and octets[1] == 168)
            or octets[0] == 127
            or octets[0] == 0
            or octets[0] >= 224
        )
    except (ValueError, IndexError):
        return True


def check_webhook_ip_whitelist(
    request: HttpRequest,
    integration: Integration,
    provider_slug: str,
) -> None:
    """
    Verify that request IP is in the whitelist for this integration.
    
    Args:
        request: HTTP request object
        integration: Integration model with config
        provider_slug: Payment provider identifier
        
    Raises:
        IPWhitelistViolation: If IP is not whitelisted or whitelist is empty
    """
    config = integration.config or {}
    whitelist = config.get("webhook_ip_whitelist", [])
    
    if not whitelist:
        logger.warning(
            f"Webhook IP whitelist not configured for {provider_slug}. "
            "Rejecting all webhook requests for security."
        )
        raise IPWhitelistViolation(
            f"IP whitelist not configured for {provider_slug}"
        )
    
    client_ip = get_client_ip(request)
    
    if client_ip not in whitelist:
        logger.warning(
            f"Webhook received from non-whitelisted IP {client_ip} "
            f"for provider {provider_slug}"
        )
        raise IPWhitelistViolation(
            f"IP {client_ip} is not authorized for {provider_slug} webhooks"
        )
    
    logger.info(
        f"Webhook IP whitelist check passed for {client_ip} ({provider_slug})"
    )


def check_webhook_rate_limit(
    integration: Integration,
    provider_slug: str,
    limit: int = 100,
    window_seconds: int = 60,
) -> None:
    """
    Check rate limit for webhook requests from a provider.
    
    Uses cache to track request count per provider within time window.
    
    Args:
        integration: Integration model
        provider_slug: Payment provider identifier
        limit: Maximum requests allowed in time window (default: 100)
        window_seconds: Time window in seconds (default: 60)
        
    Raises:
        RateLimitExceeded: If rate limit is exceeded
    """
    cache_key = f"webhook_rate_limit:{provider_slug}"
    current_count = cache.get(cache_key, 0)
    
    if current_count >= limit:
        logger.warning(
            f"Webhook rate limit exceeded for {provider_slug}. "
            f"Count: {current_count}, Limit: {limit}"
        )
        raise RateLimitExceeded(
            f"Rate limit exceeded for {provider_slug} webhooks"
        )
    
    cache.set(cache_key, current_count + 1, window_seconds)
    
    if current_count == 0:
        logger.info(
            f"Webhook rate limit tracking started for {provider_slug}"
        )


def compute_idempotency_key(
    invoice_id: int | str,
    amount: Decimal | str | float,
    provider_slug: str,
    external_ref: str | None = None,
) -> str:
    """
    Compute a deterministic idempotency key for a payment.
    
    Combines invoice, amount, provider, and external reference to create
    a unique identifier for deduplication.
    
    Args:
        invoice_id: Invoice ID
        amount: Payment amount
        provider_slug: Payment provider
        external_ref: Optional external payment reference
        
    Returns:
        SHA256 hex digest of the combined data
    """
    data = f"{invoice_id}:{amount}:{provider_slug}:{external_ref or ''}"
    return hashlib.sha256(data.encode()).hexdigest()


def check_webhook_idempotency(
    idempotency_key: str,
    max_age_hours: int = 24,
) -> bool:
    """
    Check if a webhook idempotency key has been processed recently.
    
    Returns True if this is a duplicate (already processed), False if new.
    Duplicate requests within max_age_hours are detected.
    
    Args:
        idempotency_key: Unique identifier for the request
        max_age_hours: Hours to retain idempotency record (default: 24)
        
    Returns:
        True if duplicate detected, False if new/expired
    """
    cache_key = f"webhook_idempotency:{idempotency_key}"
    
    if cache.get(cache_key) is not None:
        logger.warning(
            f"Duplicate webhook detected (idempotency key: {idempotency_key[:16]}...)"
        )
        return True  # Duplicate
    
    cache.set(cache_key, True, max_age_hours * 3600)
    return False  # New request


def log_webhook_request(
    request: HttpRequest,
    provider_slug: str,
    invoice_id: int | None,
    amount: Decimal | None,
    status: str = "received",
    error: str | None = None,
) -> None:
    """
    Log webhook request for audit trail and debugging.
    
    Args:
        request: HTTP request object
        provider_slug: Payment provider identifier
        invoice_id: Invoice ID from webhook (if available)
        amount: Payment amount from webhook (if available)
        status: Status of processing (received, processing, completed, failed)
        error: Error message if applicable
    """
    client_ip = get_client_ip(request)
    log_data = {
        "provider": provider_slug,
        "client_ip": client_ip,
        "status": status,
        "invoice_id": invoice_id,
        "amount": str(amount) if amount else None,
        "timestamp": timezone.now().isoformat(),
    }
    
    if error:
        log_data["error"] = error
        logger.error(
            f"Webhook error from {provider_slug}: {error}",
            extra=log_data,
        )
    else:
        logger.info(
            f"Webhook {status} from {provider_slug}",
            extra=log_data,
        )


def validate_webhook_request(
    request: HttpRequest,
    integration: Integration,
    provider_slug: str,
) -> dict[str, str]:
    """
    Perform all security checks on webhook request.
    
    Combines IP whitelist, rate limiting, and logging into single call.
    
    Args:
        request: HTTP request
        integration: Integration model
        provider_slug: Provider identifier
        
    Returns:
        Dict with 'passed' boolean and 'message' string
        
    Raises:
        IPWhitelistViolation: If IP not whitelisted
        RateLimitExceeded: If rate limit exceeded
    """
    try:
        check_webhook_ip_whitelist(request, integration, provider_slug)
        check_webhook_rate_limit(integration, provider_slug)
        return {"passed": True, "message": "All checks passed"}
    except (IPWhitelistViolation, RateLimitExceeded) as e:
        log_webhook_request(
            request,
            provider_slug,
            invoice_id=None,
            amount=None,
            status="rejected",
            error=str(e),
        )
        raise
