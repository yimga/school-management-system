"""Gateway registry: resolve gateway by school and method (Phase 3). Prefer policy from request.tenant_runtime when in request context.

STATUS — dormant/scaffolded rail (verified 2026-07-23): ``get_gateway`` and the
``BasePaymentGateway`` surface it returns (``initiate`` / ``check_status`` /
``parse_webhook``) currently have NO production callers. Some concrete gateways
here (e.g. ``razorpay``/``mercado_pago``) DO issue real HTTP in ``initiate`` — do
not mistake that for a live rail: nothing invokes it yet.

The LIVE inbound webhook path is ``apps.finance.webhooks.normalizer``
(``normalize_provider_payload``, wired in ``apps.finance.views_payments``), NOT
``parse_webhook`` here. Bringing an outbound rail live is gated on external PSP
credentials / partner certification tracked per adapter in
``apps.billing.psp_adapter_registry`` (``adapter_status``). Until a caller is
wired end-to-end, treat this module as scaffolding, not a settled payment path.
"""

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
    """Return zero under the current no-custody tenant-payment contract.

    RunMyCampus bills its SaaS subscription separately in ``apps.billing``.
    Tenant tuition/fee gateways settle to the tenant; policy configuration must
    not silently introduce an operator fee on those transactions.
    """
    return Decimal("0")
