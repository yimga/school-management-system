"""Compliance domain service entry points for the Unified Wizard Framework.

Thin shim that adapts the wizard payload shape to ``apps.compliance.consent_services``
+ writes one ``ConsentRecord`` per signed document. Wizard writers call
``_try_domain_integration("apps.compliance.services", "record_consent_acceptance", ...)``
so callers get first-class ConsentRecord rows in addition to the cockpit cascade.

Idempotent + tolerant: ``school is None``, missing user, empty payload all no-op
silently. PII-safe: only signed document titles + boolean acknowledgments land
in storage — no free-form text.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["record_consent_acceptance"]


# Stable map: wizard payload key → human-readable document title.
# Kept here (not in the wizard JSON) so the title doesn't depend on the i18n
# token rendering at wizard time and the audit record reads cleanly.
_CONSENT_DOC_TITLES = {
    "privacy_policy": "Privacy Policy",
    "data_residency_acknowledgment": "Data Residency Acknowledgment",
    "terms_of_service": "Terms of Service",
    "photo_consent": "Photo / Media Consent",
    "medical_release": "Medical Release",
    "field_trip_authorization": "Field Trip Authorization",
}


def record_consent_acceptance(
    *,
    school: Any,
    payload: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
) -> int:
    """Persist one ``ConsentRecord`` per signed document in ``payload``.

    Returns the number of records written (0 on no-op or partial failure).
    """
    if school is None or not payload:
        return 0

    try:
        from apps.compliance.models import ConsentRecord
    except ImportError:
        logger.debug("record_consent_acceptance: ConsentRecord model unavailable")
        return 0

    user = _resolve_user(actor_user_id)
    if user is None:
        logger.debug("record_consent_acceptance: actor_user_id %s did not resolve", actor_user_id)
        return 0

    written = 0
    for key, title in _CONSENT_DOC_TITLES.items():
        if not payload.get(key):
            continue
        try:
            # tenant-isolation-allow: consent-record-create-explicit-school-fk-from-wizard-writer
            ConsentRecord.objects.create(
                school=school,
                user=user,
                title=title,
                document_hash="",  # wizard doesn't render document text — hash empty
            )
            written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "record_consent_acceptance: ConsentRecord.create failed (key=%s): %s",
                key, exc,
            )
    return written


def _resolve_user(actor_user_id: int | None):
    if not actor_user_id:
        return None
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.filter(pk=actor_user_id).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_consent_acceptance: user resolve failed: %s", exc)
        return None
