"""
DNS provider abstraction for tenant subdomain auto-provisioning.

Default-off. Opt-in via the DNS_PROVIDER setting:

    DNS_PROVIDER = "cloudflare"   # requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE_ID
    DNS_PROVIDER = "route53"      # requires AWS_ROUTE53_HOSTED_ZONE_ID + AWS creds

When unset (the default), get_dns_provider() returns NullDNSProvider, which is a
safe no-op for self-hosted deployments that manage DNS out of band.
"""

from apps.schools.dns_providers.base import (
    BaseDNSProvider,
    DNSProviderResult,
    NullDNSProvider,
)

__all__ = [
    "BaseDNSProvider",
    "DNSProviderResult",
    "NullDNSProvider",
    "get_dns_provider",
]


def get_dns_provider() -> BaseDNSProvider:
    """Return the DNS provider configured via settings.DNS_PROVIDER."""
    from django.conf import settings

    name = (getattr(settings, "DNS_PROVIDER", "") or "").strip().lower()
    if name == "cloudflare":
        from apps.schools.dns_providers.cloudflare import CloudflareDNSProvider

        return CloudflareDNSProvider()
    if name == "route53":
        from apps.schools.dns_providers.route53 import Route53DNSProvider

        return Route53DNSProvider()
    return NullDNSProvider()
