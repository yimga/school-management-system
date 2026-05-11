"""Cloudflare DNS provider — POSTs to https://api.cloudflare.com/client/v4."""

import logging

from django.conf import settings

from apps.schools.dns_providers.base import BaseDNSProvider, DNSProviderResult

logger = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"

# Cloudflare returns code 81057 when a record with the same name+type+content
# already exists. We treat that as idempotent success.
CLOUDFLARE_RECORD_ALREADY_EXISTS = 81057


class CloudflareDNSProvider(BaseDNSProvider):
    name = "cloudflare"

    def __init__(self) -> None:
        self.token = (getattr(settings, "CLOUDFLARE_API_TOKEN", "") or "").strip()
        self.zone_id = (getattr(settings, "CLOUDFLARE_ZONE_ID", "") or "").strip()
        self.proxied = bool(getattr(settings, "CLOUDFLARE_PROXIED", False))

    def create_record(
        self,
        *,
        subdomain: str,
        target: str,
        record_type: str = "CNAME",
        ttl: int = 60,
    ) -> DNSProviderResult:
        if not subdomain or not target:
            return DNSProviderResult(
                ok=False,
                provider=self.name,
                error="subdomain and target are required.",
            )
        if not self.token or not self.zone_id:
            return DNSProviderResult(
                ok=False,
                provider=self.name,
                error="CLOUDFLARE_API_TOKEN / CLOUDFLARE_ZONE_ID not set.",
            )

        try:
            import requests
        except ImportError:
            return DNSProviderResult(
                ok=False, provider=self.name, error="requests library not installed."
            )

        url = f"{API_BASE}/zones/{self.zone_id}/dns_records"
        payload = {
            "type": record_type,
            "name": subdomain,
            "content": target,
            "ttl": ttl,
            "proxied": self.proxied,
        }
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("Cloudflare network error creating %s: %s", subdomain, exc)
            return DNSProviderResult(ok=False, provider=self.name, error=str(exc))

        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}

        if response.ok and data.get("success"):
            record_id = (data.get("result") or {}).get("id")
            return DNSProviderResult(
                ok=True, provider=self.name, record_id=record_id, raw=data
            )

        errors = data.get("errors") or [{"message": (response.text or "")[:200]}]
        for err in errors:
            try:
                if int(err.get("code", 0)) == CLOUDFLARE_RECORD_ALREADY_EXISTS:
                    return DNSProviderResult(
                        ok=True,
                        provider=self.name,
                        record_id=None,
                        error="record already exists (treated as success)",
                        raw=data,
                    )
            except (TypeError, ValueError):
                continue
        msg = "; ".join(str(e.get("message", "")) for e in errors)
        return DNSProviderResult(
            ok=False, provider=self.name, error=msg or "unknown error", raw=data
        )
