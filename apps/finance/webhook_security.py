"""
Webhook security compatibility shim.

Use apps.finance.security for webhook validation and helpers.
"""

from .security import (
    PaymentValidator,
    WebhookSecurityValidator,
    webhook_security_required,
)

__all__ = [
    "PaymentValidator",
    "WebhookSecurityValidator",
    "webhook_security_required",
]
