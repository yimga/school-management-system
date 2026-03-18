"""Gateway registry: resolve gateway by school and method (Phase 3). Prefer policy from request.tenant_runtime when in request context."""

from decimal import Decimal
from typing import Any, Dict, Optional

from apps.policies.policy_registry import get_effective_policy
from apps.schools.models import School

from .base import BasePaymentGateway

_REGISTRY: dict[str, type[BasePaymentGateway]] = {}


def register_gateway(code: str, gateway_class: type[BasePaymentGateway]) -> None:
    _REGISTRY[code.lower()] = gateway_class


def _policy_for_gateway(
    school: Optional[School], policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Resolve policy: use provided policy (e.g. request.tenant_runtime.policy) or get_effective_policy(school)."""
    if policy is not None:
        return policy
    return get_effective_policy(school) if school else {}


def get_gateway(
    school: School,
    method_code: str,
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> Optional[BasePaymentGateway]:
    """Return gateway instance for school and method (e.g. MTN_MOMO, ORANGE_MONEY). Config from policy.
    In request context, pass policy=request.tenant_runtime.policy to use the unified runtime (no direct get_effective_policy)."""
    code = (method_code or "").strip().upper().replace(" ", "_")
    if not code:
        return None
    key = code.lower()
    if key not in _REGISTRY:
        return None
    resolved = _policy_for_gateway(school, policy)
    gateways_config = resolved.get("payment_gateways") or {}
    config = gateways_config.get(key) or gateways_config.get(code) or {}
    return _REGISTRY[key](school, config)


def get_platform_fee(
    school: Optional[School],
    method_code: str,
    amount: Decimal,
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> Decimal:
    """Optional platform fee (e.g. 100 XAF) from policy. Prefer policy=request.tenant_runtime.policy in request context."""
    resolved = _policy_for_gateway(school, policy)
    gateways_config = resolved.get("payment_gateways") or {}
    code = (method_code or "").strip().upper()
    cfg = gateways_config.get(code.lower()) or gateways_config.get(code) or {}
    fee = cfg.get("platform_fee")
    if fee is not None:
        return Decimal(str(fee))
    return Decimal("0")
