"""
DNS verification for custom domains: query TXT records for runyourcampus-verify=<dns_token>
and mark SchoolDomain as verified. Legacy runmycampus token prefixes remain accepted.
"""
import logging
from django.utils import timezone

from apps.schools.domain_sync import sync_verified_schooldomain

logger = logging.getLogger(__name__)

TXT_PREFIXES = ("runyourcampus-verify=", "runmycampus-verify=")


def verify_domain_txt(domain: str, expected_token: str) -> bool:
    """
    Query TXT records for the given domain and return True if any TXT record
    contains runyourcampus-verify=<expected_token> (legacy runmycampus prefix also accepted).
    """
    if not domain or not expected_token:
        return False
    domain = domain.strip().lower()
    expected = str(expected_token).strip().lower()
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "TXT")
        for rdata in answers:
            for s in rdata.strings:
                txt = s.decode("utf-8") if isinstance(s, bytes) else str(s)
                lowered = txt.lower()
                for prefix in TXT_PREFIXES:
                    if lowered.startswith(prefix.lower()):
                        token_part = txt[len(prefix) :].strip()
                        if token_part.lower() == expected:
                            return True
        return False
    except Exception as e:
        logger.warning("DNS TXT verification failed for %s: %s", domain, e)
        return False


def verify_and_activate_schooldomain(school_domain) -> bool:
    """
    Check TXT for the given SchoolDomain instance; if runyourcampus-verify=<dns_token>
    is present, set is_verified=True, set verified_at, and log SchoolProvisioningEvent.
    Returns True if verification succeeded.
    """
    from .models import SchoolDomain, SchoolProvisioningEvent

    if not isinstance(school_domain, SchoolDomain):
        return False
    if school_domain.is_verified:
        return True
    domain = (school_domain.domain or "").strip().lower()
    token_str = str(school_domain.dns_token or "").strip().lower()
    if not domain or not token_str:
        return False
    if not verify_domain_txt(domain, token_str):
        return False
    school_domain.is_verified = True
    school_domain.verified_at = timezone.now()
    school_domain.save(update_fields=["is_verified", "verified_at"])
    try:
        sync_verified_schooldomain(school_domain)
    except Exception as exc:
        logger.warning("Domain verified but runtime sync failed for %s: %s", domain, exc)
    SchoolProvisioningEvent.log_event(
        school=school_domain.school,
        event_type=SchoolProvisioningEvent.EventType.DOMAIN_VERIFIED,
        status=SchoolProvisioningEvent.Status.SUCCESS,
        message="Custom domain verified: %s" % domain,
        payload={"domain": domain, "school_domain_id": str(school_domain.pk)},
    )
    return True
