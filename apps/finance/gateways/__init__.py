"""
Payment gateways: MTN MoMo, Orange Money, Stripe, Paystack, Flutterwave.
Abstract interface; tenant routing by school_id; optional platform fee.
"""

from .base import BasePaymentGateway, GatewayResult
from .registry import get_gateway, get_platform_fee, register_gateway

# Register built-in gateways (import side-effect calls registry.register_gateway)
from . import mtn_momo  # noqa: F401
from . import mpesa_daraja  # noqa: F401
from . import orange_money  # noqa: F401
from . import stripe  # noqa: F401
from . import paystack  # noqa: F401
from . import flutterwave  # noqa: F401
from . import razorpay  # noqa: F401
from . import pesapal  # noqa: F401
from . import mercado_pago  # noqa: F401
from . import dlocal  # noqa: F401

__all__ = [
    "BasePaymentGateway",
    "GatewayResult",
    "get_gateway",
    "get_platform_fee",
    "register_gateway",
]
