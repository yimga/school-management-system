"""AWS Route53 DNS provider — uses boto3 ChangeResourceRecordSets UPSERT."""

import logging

from django.conf import settings

from apps.schools.dns_providers.base import BaseDNSProvider, DNSProviderResult

logger = logging.getLogger(__name__)


class Route53DNSProvider(BaseDNSProvider):
    name = "route53"

    def __init__(self) -> None:
        self.hosted_zone_id = (
            getattr(settings, "AWS_ROUTE53_HOSTED_ZONE_ID", "") or ""
        ).strip()
        self.region = (
            getattr(settings, "AWS_ROUTE53_REGION", "")
            or getattr(settings, "AWS_REGION", "")
            or ""
        ).strip()

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
        if not self.hosted_zone_id:
            return DNSProviderResult(
                ok=False,
                provider=self.name,
                error="AWS_ROUTE53_HOSTED_ZONE_ID not set.",
            )

        try:
            import boto3
        except ImportError:
            return DNSProviderResult(
                ok=False,
                provider=self.name,
                error="boto3 not installed (add to requirements.txt).",
            )

        try:
            kwargs = {"region_name": self.region} if self.region else {}
            client = boto3.client("route53", **kwargs)
            response = client.change_resource_record_sets(
                HostedZoneId=self.hosted_zone_id,
                ChangeBatch={
                    "Comment": "RunMyCampus tenant provisioning",
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": subdomain,
                                "Type": record_type,
                                "TTL": ttl,
                                "ResourceRecords": [{"Value": target}],
                            },
                        }
                    ],
                },
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("Route53 network error creating %s: %s", subdomain, exc)
            return DNSProviderResult(ok=False, provider=self.name, error=str(exc))
        except Exception as exc:  # boto3 raises ClientError/BotoCoreError
            logger.warning("Route53 create_record failed for %s: %s", subdomain, exc)
            return DNSProviderResult(ok=False, provider=self.name, error=str(exc))

        change_id = (response.get("ChangeInfo") or {}).get("Id")
        return DNSProviderResult(
            ok=True, provider=self.name, record_id=change_id, raw=response
        )
