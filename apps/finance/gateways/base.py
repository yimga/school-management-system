"""Abstract payment gateway interface (Phase 3)."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from apps.schools.models import School


@dataclass
class GatewayResult:
    """Result of initiate or webhook callback."""
    success: bool
    transaction_id: Optional[str] = None
    message: Optional[str] = None
    raw_response: Optional[dict] = None


class BasePaymentGateway:
    """Abstract interface for collect payment (e.g. MoMo, Orange Money)."""

    code: str = "base"

    def __init__(self, school: School, config: Optional[dict] = None):
        self.school = school
        self.config = config or {}

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
        """Start payment collection. Returns GatewayResult with transaction_id on success."""
        raise NotImplementedError

    def check_status(self, transaction_id: str) -> GatewayResult:
        """Poll payment status."""
        raise NotImplementedError

    def parse_webhook(self, payload: dict, headers: Optional[dict] = None) -> Optional[GatewayResult]:
        """Parse webhook payload from provider; return GatewayResult or None if not for us."""
        raise NotImplementedError
