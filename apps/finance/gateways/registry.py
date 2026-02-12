"""Gateway registry: resolve gateway by school and method (Phase 3)."""
from decimal import Decimal
from typing import Optional

from apps.schools.models import School

from .base import BasePaymentGateway, GatewayResult

_REGISTRY: dict[str, type[BasePaymentGateway]] = {}


def register_gateway(code: str, gateway_class: type[BasePaymentGateway]) -> None:
    _REGISTRY[code.lower()] = gateway_class


def get_gateway(school: School, method_code: str) -> Optional[BasePaymentGateway]:
    """Return gateway instance for school and method (e.g. MTN_MOMO, ORANGE_MONEY). Config from School.settings."""
    code = (method_code or "").strip().upper().replace(" ", "_")
    if not code:
        return None
    key = code.lower()
    if key not in _REGISTRY:
        return None
    settings = getattr(school, "settings", None) or {}
    gateways_config = settings.get("payment_gateways") or {}
    config = gateways_config.get(key) or gateways_config.get(code) or {}
    return _REGISTRY[key](school, config)


def get_platform_fee(school: School, method_code: str, amount: Decimal) -> Decimal:
    """Optional platform fee (e.g. 100 XAF) from school or global config."""
    settings = getattr(school, "settings", None) or {}
    gateways_config = settings.get("payment_gateways") or {}
    code = (method_code or "").strip().upper()
    cfg = gateways_config.get(code.lower()) or gateways_config.get(code) or {}
    fee = cfg.get("platform_fee")
    if fee is not None:
        return Decimal(str(fee))
    return Decimal("0")
