"""Can each integrated service actually deliver — not merely: is it configured?

Every integration on this platform has two different questions attached to it,
and until now only the first was ever asked:

    configured?  a setting is present
    delivering?  something actually leaves the building

A school can attach its own mail server, have the form accept it, and never send
a single message — because ``_get_connection_for_send`` takes host / port /
credentials from the school's config but the BACKEND CLASS from the global
``EMAIL_BACKEND``. On a box shipping ``EMAIL_BACKEND=console`` (the default in
``deploy/selfhost/.env.edge.example``) the school's mail server is not contacted
at all. Nothing errors. The tenant is simply wrong about their own platform.

Two rules this module exists to hold:

**Prove the outcome, not the mechanism.** See
``docs/ENGINEERING_STANDARD_PROVE_THE_OUTCOME.md``. We do NOT open a socket on a
page render — that is slow, flaky, and still only proves a moment. We use the
cheaper and stronger evidence: **count what failed to leave.** A parked message
is an empirical statement that delivery is not happening, and it costs one query.

**Never block.** These probes inform; they do not gate. A school that has
deliberately chosen no email is not broken, and must not be told it is.

Adding an integration: write a ``_probe_x() -> DeliveryStatus`` and register it in
``_PROBES``. A probe MUST be cheap, MUST NOT perform network I/O, and MUST NOT
raise — :func:`delivery_statuses` guards each one, but a probe that throws every
call is a defect, not a degradation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


@dataclass
class DeliveryStatus:
    """One integration's answer to "can you actually deliver?"."""

    key: str
    name: Any
    can_deliver: bool
    #: Short, admin-facing. Empty when everything is fine.
    reason: Any = ""
    #: What the admin should do about it. Empty when there is nothing to do.
    remedy: Any = ""
    #: Items empirically stuck because of this. The outcome measurement.
    blocked: int = 0
    #: Where the configuration came from, for "why is my setting being ignored?".
    config_source: str = ""
    #: True when the school configured something that is not being used.
    config_ignored: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def is_problem(self) -> bool:
        """Worth showing an admin. A deliberate 'no email' school is not a problem."""
        return bool(self.blocked) or self.config_ignored


# Backends that accept a message, report success, and deliver it to nobody.
NON_DELIVERING_BACKENDS = ("console", "locmem", "dummy")


def _email_backend_token() -> tuple[bool, str]:
    """(can_deliver, matched_token) for the ACTIVE global mail backend."""
    from django.conf import settings

    backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    for token in NON_DELIVERING_BACKENDS:
        if token in backend:
            return False, token
    return True, ""


def _parked_email_count() -> int:
    """How many messages are sitting undelivered. Zero on any read failure."""
    try:
        from apps.schoolops.models_email_deadletter import (
            DeadLetterStatus,
            EmailDeadLetter,
        )

        # tenant-isolation-allow: platform-email-dead-letter-no-tenant-scope
        return int(EmailDeadLetter.objects.filter(status=DeadLetterStatus.PENDING).count())
    except Exception:  # noqa: BLE001 — a health probe must never break a dashboard
        logger.debug("integration_delivery: parked email count unavailable", exc_info=True)
        return 0


def _probe_email(school=None) -> DeliveryStatus:
    can_deliver, dead_backend = _email_backend_token()
    parked = _parked_email_count()

    source = ""
    host = ""
    try:
        from apps.schoolops.email_delivery import get_resolved_smtp_config

        cfg = get_resolved_smtp_config(school=school) or {}
        source = str(cfg.get("source") or "")
        host = str(cfg.get("host") or "")
    except Exception:  # noqa: BLE001 — probe, not a gate
        logger.debug("integration_delivery: smtp config unavailable", exc_info=True)

    school_supplied = source == "tenant_school_settings" and bool(host)

    if not can_deliver:
        # The school's own mail server is configured and being ignored. This is
        # the single most misleading state the platform can be in, because the
        # tenant has evidence (their saved settings) that it should be working.
        if school_supplied:
            return DeliveryStatus(
                key="email",
                name=_("Email"),
                can_deliver=False,
                reason=_("Your mail server is configured but is not being used."),
                remedy=_(
                    "This installation is set to a preview mail mode, so no mail "
                    "leaves the server. Ask your administrator to switch it to live "
                    "sending — your settings are saved and will be used as soon as "
                    "they do."
                ),
                blocked=parked,
                config_source=source,
                config_ignored=True,
                extra={"backend_kind": dead_backend},
            )
        return DeliveryStatus(
            key="email",
            name=_("Email"),
            can_deliver=False,
            reason=_("Email is not being delivered."),
            remedy=_(
                "This installation has no mail path configured. Messages are held "
                "safely and will send once one is set up — nothing is lost."
            ),
            blocked=parked,
            config_source=source,
            extra={"backend_kind": dead_backend},
        )

    if not host:
        return DeliveryStatus(
            key="email",
            name=_("Email"),
            can_deliver=False,
            reason=_("No mail server address is set."),
            remedy=_("Add your mail server details so messages can be sent."),
            blocked=parked,
            config_source=source,
        )

    # Configured and capable. `blocked` is still reported: a healthy backend with
    # a parked backlog means something WAS wrong, and the queue has not drained yet.
    return DeliveryStatus(
        key="email",
        name=_("Email"),
        can_deliver=True,
        blocked=parked,
        config_source=source,
    )


_PROBES: tuple[Callable[..., DeliveryStatus], ...] = (
    _probe_email,
)


def delivery_statuses(school=None) -> list[DeliveryStatus]:
    """Run every probe. A probe that raises is skipped, never propagated."""
    out: list[DeliveryStatus] = []
    for probe in _PROBES:
        try:
            out.append(probe(school))
        except Exception:  # noqa: BLE001 — one bad probe must not blank the panel
            logger.warning(
                "integration_delivery: probe %s failed",
                getattr(probe, "__name__", "?"),
                exc_info=True,
            )
    return out


def delivery_problems(school=None) -> list[DeliveryStatus]:
    """Only the statuses an admin needs to see."""
    return [s for s in delivery_statuses(school) if s.is_problem]
