"""
Celery tasks for accounts (e.g. delegation auto-revoke).
"""
from __future__ import annotations

import logging
from django.utils import timezone
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="accounts.expire_past_delegations")
def expire_past_delegations():
    """
    Set is_active=False on delegations whose effective_end_date has passed.
    Respects SiteSettings.delegation_auto_revoke; when True, deactivates automatically.
    """
    from apps.accounts.models import Delegation
    from apps.siteconfig.models import SiteSettings

    try:
        site = SiteSettings.get_solo()
        if not getattr(site, "delegation_auto_revoke", True):
            return {"expired": 0, "skipped": "auto_revoke disabled"}
    except Exception as e:
        logger.warning("expire_past_delegations: could not load SiteSettings: %s", e)
        return {"expired": 0, "error": str(e)}

    now = timezone.now()
    # Delegations that are still active but past their effective end
    qs = Delegation.objects.filter(is_active=True)
    to_expire = []
    for d in qs:
        end = d.extended_end_date or d.end_date
        if end and end < now:
            to_expire.append(d.pk)

    if to_expire:
        for pk in to_expire:
            try:
                from apps.people.badge_services import revoke_acting_badges_for_delegation
                d = Delegation.objects.get(pk=pk)
                revoke_acting_badges_for_delegation(d)
                if getattr(site, "delegation_summary_report_on_return", True):
                    try:
                        from apps.accounts.models import DelegationActionLog
                        count = DelegationActionLog.objects.filter(delegation=d).count()
                        if count > 0 and d.delegator.email:
                            from django.core.mail import send_mail
                            from django.conf import settings as django_settings
                            send_mail(
                                subject="While you were away: %d action(s) on your behalf" % count,
                                message="Your delegation has ended. %d action(s) were taken on your behalf. Review them in the portal: Delegation catch-up." % count,
                                from_email=getattr(django_settings, "DEFAULT_FROM_EMAIL", "noreply@school.local"),
                                recipient_list=[d.delegator.email],
                                fail_silently=True,
                            )
                    except Exception as e:
                        logger.warning("expire_past_delegations: summary email for %s: %s", pk, e)
            except Exception as e:
                logger.warning("expire_past_delegations: revoke badge for delegation %s: %s", pk, e)
        Delegation.objects.filter(pk__in=to_expire).update(is_active=False)
        logger.info("expire_past_delegations: deactivated %d delegation(s)", len(to_expire))

    return {"expired": len(to_expire)}
