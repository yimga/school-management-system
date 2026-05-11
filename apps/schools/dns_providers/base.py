"""Base classes + result envelope for DNS provider implementations."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DNSProviderResult:
    ok: bool
    provider: str
    record_id: Optional[str] = None
    error: Optional[str] = None
    raw: dict = field(default_factory=dict)


class BaseDNSProvider:
    """
    Uniform interface for DNS record automation.

    Implementations should be idempotent: calling create_record twice for the
    same (subdomain, target) tuple must not error and must return ok=True.
    Network/auth/validation errors return ok=False with a human-readable error.
    """

    name: str = "base"

    def create_record(
        self,
        *,
        subdomain: str,
        target: str,
        record_type: str = "CNAME",
        ttl: int = 60,
    ) -> DNSProviderResult:
        raise NotImplementedError


class NullDNSProvider(BaseDNSProvider):
    """No-op provider returned when DNS_PROVIDER is unset."""

    name = "null"

    def create_record(self, **kwargs) -> DNSProviderResult:
        return DNSProviderResult(
            ok=False,
            provider=self.name,
            error="No DNS provider configured (set DNS_PROVIDER=cloudflare|route53).",
        )
