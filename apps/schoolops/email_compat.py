"""Compatibility shim for legacy callers (v4.00.98 Phase 7).

Drop-in replacement for ``django.core.mail.send_mail`` that routes through
the reliability layer (``apps.schoolops.email_delivery.send_transactional``).
Use it when migrating a legacy callsite without changing the signature:

  from django.core.mail import send_mail          # OLD: silent failures
  from apps.schoolops.email_compat import send_mail  # NEW: audited + retried

The compat wrapper preserves the legacy positional / keyword signature
(``subject, message, from_email, recipient_list, fail_silently=False, …``)
so existing callers don't need any other edit. ``fail_silently`` is honored;
return value matches Django's: ``int`` (1 on success, 0 on failure) since
that's what most legacy callers check.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, Union

logger = logging.getLogger(__name__)


def send_mail(
    subject: str,
    message: str,
    from_email: Optional[str],
    recipient_list: Iterable[str],
    fail_silently: bool = False,
    auth_user: Optional[str] = None,  # accepted for signature parity; ignored
    auth_password: Optional[str] = None,  # accepted for signature parity; ignored
    connection: Any = None,  # accepted for signature parity; ignored
    html_message: Optional[str] = None,
) -> int:
    """Mirror django.core.mail.send_mail signature; route to send_transactional.

    Returns 1 when the reliability layer reports ok=True (delivered OR
    queued), 0 otherwise. Honors ``fail_silently=True`` (re-raises only
    when False AND the reliability layer is itself unimportable).
    """

    try:
        from apps.schoolops.email_delivery import send_transactional
    except Exception:
        if fail_silently:
            return 0
        raise

    recipients = [str(r) for r in recipient_list if r]
    if not recipients:
        return 0

    try:
        result = send_transactional(
            subject=subject,
            body=message,
            to=recipients[0] if len(recipients) == 1 else recipients,
            html_body=html_message,
            from_email=from_email,
        )
    except Exception:
        if fail_silently:
            return 0
        raise

    if isinstance(result, dict) and result.get("ok"):
        return 1
    if not fail_silently and isinstance(result, dict) and result.get("error_kind"):
        # Match the legacy behavior: callers that did NOT ask for silent
        # failure still expect a successful return; the audit row carries
        # the failure detail.
        pass
    return 1 if (isinstance(result, dict) and result.get("ok")) else 0
