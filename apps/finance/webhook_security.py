"""
Webhook security compatibility shim.

Use apps.finance.security for webhook validation and helpers.
"""

from .security import (
    PaymentValidator,
    WebhookSecurityValidator,
)

# NOTE: `webhook_security_required` was retired 2026-06-15 (dead, applied to no
# view, referenced a `PaymentIntegration` model that was never built). Webhook
# security lives in the routed `views_payments.py::payment_provider_webhook`
# using `WebhookSecurityValidator`.
__all__ = [
    "PaymentValidator",
    "WebhookSecurityValidator",
]
