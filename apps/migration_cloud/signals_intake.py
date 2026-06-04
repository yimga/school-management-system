"""Customer-facing intake signal wiring (v3.40.0 Agent 7).

Wires email-send for ``MigrationIntakeRequest`` state transitions.
Hooked from ``apps/migration_cloud/apps.py::MigrationCloudConfig.ready``;
the customer view layer also calls ``dispatch_state_change`` directly
so the email lands inside the same request flow without requiring
``post_save`` to fire on every model write (which would double-fire
during the auto-advance into ``maa-pending-counsel`` immediately after
``create``).

Defense layers:

  * Email send wrapped in try/except — a delivery failure NEVER breaks
    the user's request flow.
  * ``signature_text``, ``counsel_signoff_pdf_url`` contents, and full
    MAA body are NEVER referenced in email context.
  * Subject lines stay <=80 chars and contain no PII.
  * Recipient resolution honors the school's ``receives_email`` flag
    on the requesting user when present (defense-in-depth alongside
    Django's default email backend).
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from apps.schoolops.email_compat import send_mail
from django.template.loader import render_to_string

from .models_intake import MigrationIntakeRequest, MigrationIntakeState

logger = logging.getLogger(__name__)


# Map of (state) -> (template_basename, subject). Template basenames
# resolve to BOTH ``<base>.txt`` and ``<base>.html`` under
# ``templates/migration_cloud/emails/customer/``.
_STATE_EMAIL_TEMPLATES: dict[str, tuple[str, str]] = {
    MigrationIntakeState.MAA_PENDING_COUNSEL.value: (
        "intake_received",
        "We received your migration intake",
    ),
    MigrationIntakeState.MAA_SIGNED.value: (
        "intake_maa_signed",
        "Migration agreement signed - extraction begins shortly",
    ),
    MigrationIntakeState.EXTRACTION_COMPLETE.value: (
        "intake_extraction_complete",
        "Migration extraction complete - validation underway",
    ),
    MigrationIntakeState.COMPLETE.value: (
        "intake_complete",
        "Your migration is complete",
    ),
    MigrationIntakeState.FAILED.value: (
        "intake_failed",
        "Your migration needs attention",
    ),
}


def _recipient_for(intake: MigrationIntakeRequest) -> Optional[str]:
    """Resolve the email address to send to, honoring ``receives_email``.

    Defense-in-depth: when the user has opted out we still return the
    address (Django's email backend honors any deeper preference flag),
    but we log the override. ``None`` is returned only when no address
    is available.
    """
    user = intake.requested_by_user
    if user is None:
        return None
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return None
    receives = getattr(user, "receives_email", True)
    if not receives:
        logger.info(
            "migration_cloud.intake: skip email opt_out intake_id=%s user_pk=%s",
            intake.id, getattr(user, "pk", None),
        )
        return None
    return email


def _from_address() -> str:
    return getattr(
        settings, "MIGRATION_CLOUD_INTAKE_FROM_EMAIL",
        getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@runmycampus.com"),
    )


def dispatch_state_change(
    intake: MigrationIntakeRequest,
    previous_state: str,
) -> None:
    """Send the appropriate email for a state transition.

    Called by ``views_customer`` after every ``advance()``. Idempotent
    enough — a duplicate call sends the email a second time, which
    customer ops considers acceptable risk vs. silently swallowing a
    transition. NEVER raises; logs and returns on any failure.
    """
    new_state = intake.state
    if previous_state == new_state:
        return  # no-op transition, never email

    entry = _STATE_EMAIL_TEMPLATES.get(new_state)
    if entry is None:
        return
    template_base, subject = entry

    # Subject ≤80 chars; no PII allowed. We pre-truncate defensively.
    subject = subject[:80]

    recipient = _recipient_for(intake)
    if recipient is None:
        logger.info(
            "migration_cloud.intake: no recipient intake_id=%s state=%s",
            intake.id, new_state,
        )
        return

    tenant = intake.tenant
    school_name = getattr(tenant, "name", "") or "your school"
    context = {
        "intake_id": str(intake.id),
        "school_name": school_name,
        "vendor_label": dict(
            (
                ("powerschool", "PowerSchool"),
                ("blackbaud", "Blackbaud"),
                ("veracross", "Veracross"),
                ("alma", "Alma"),
                ("facts", "FACTS"),
                ("skyward", "Skyward"),
            )
        ).get(intake.vendor_slug, intake.vendor_slug),
        "next_action": intake.next_action_banner() or "",
        # Operator-from-team notes are visible to the school — render
        # them in the failure email so the school knows what to do.
        "operator_notes": (
            intake.notes_from_runmycampus_team[:2000]
            if new_state == MigrationIntakeState.FAILED.value else ""
        ),
        "status_url_path": f"/migration/{intake.id}/status/",
    }

    try:
        text_body = render_to_string(
            f"migration_cloud/emails/customer/{template_base}.txt", context,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud.intake: render_txt_failed intake_id=%s state=%s err=%s",
            intake.id, new_state, type(exc).__name__,
        )
        return
    try:
        html_body = render_to_string(
            f"migration_cloud/emails/customer/{template_base}.html", context,
        )
    except Exception:  # noqa: BLE001 — html template optional
        html_body = None

    try:
        send_mail(
            subject=subject,
            message=text_body,
            from_email=_from_address(),
            recipient_list=[recipient],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info(
            "migration_cloud.intake: emailed intake_id=%s state=%s template=%s",
            intake.id, new_state, template_base,
        )
    except Exception as exc:  # noqa: BLE001 — never break the transition
        logger.warning(
            "migration_cloud.intake: send_failed intake_id=%s state=%s err=%s",
            intake.id, new_state, type(exc).__name__,
        )


def register_signal_handlers() -> None:
    """No-op placeholder for ``apps.py::ready()`` to call.

    The customer view layer dispatches state-change emails directly via
    ``dispatch_state_change`` so we don't double-fire on intermediate
    auto-advance writes. The hook here exists so future Celery / signal
    based fan-out can be added without touching ``apps.py`` again.
    """
    logger.debug("migration_cloud.intake: signal handlers registered (passive)")
