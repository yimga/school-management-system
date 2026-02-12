"""MTN Mobile Money gateway (Phase 3). Placeholder until real API integration."""
from decimal import Decimal
from typing import Optional

from apps.schools.models import School

from .base import BasePaymentGateway, GatewayResult

# Register on import
from . import registry  # noqa: F401


class MTNMoMoGateway(BasePaymentGateway):
    code = "mtn_momo"

    def initiate(
        self,
        amount: Decimal,
        currency: str,
        reference: str,
        payer_phone: Optional[str] = None,
        description: Optional[str] = None,
        platform_fee: Optional[Decimal] = None,
        **kwargs,
    ) -> GatewayResult:
        # Placeholder: in production call MTN MoMo API (subscription_key, api_user, etc. from self.config)
        return GatewayResult(
            success=False,
            message="MTN MoMo integration not configured. Set payment_gateways.mtn_momo in School.settings.",
            raw_response={"placeholder": True},
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        return GatewayResult(success=False, message="Not implemented", transaction_id=transaction_id)

    def parse_webhook(self, payload: dict, headers: Optional[dict] = None) -> Optional[GatewayResult]:
        return None


registry.register_gateway("mtn_momo", MTNMoMoGateway)
