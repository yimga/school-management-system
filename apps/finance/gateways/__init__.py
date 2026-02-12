"""
Payment gateways for Mobile Money (Phase 3): MTN MoMo, Orange Money.
Abstract interface; tenant routing by school_id; optional platform fee.
"""
from .base import BasePaymentGateway, GatewayResult
from .registry import get_gateway, get_platform_fee, register_gateway

# Register built-in gateways
from . import mtn_momo  # noqa: F401
from . import orange_money  # noqa: F401

__all__ = ["BasePaymentGateway", "GatewayResult", "get_gateway", "get_platform_fee", "register_gateway"]
