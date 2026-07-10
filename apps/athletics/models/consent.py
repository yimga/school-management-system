"""Guardian participation consent — clones the people.TransferConsent discipline.

The raw token is returned exactly once from ``mint()`` and never persisted
(sha256 only, constant-time compare), the consent text the guardian saw is
recorded immutably (version + sha256), decision IP/UA are server-captured
(XFF-first), and every transition is journaled best-effort. A membership
cannot leave ``PENDING`` (become ACTIVE) except through a CONSENTED row.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Optional, Tuple

from django.db import models, transaction
from django.utils import timezone

from apps.athletics.constants import (
    CONSENT_TEXT_VERSION,
    PARTICIPATION_CONSENT_EXPIRY_DAYS,
)

logger = logging.getLogger(__name__)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


class ParticipationConsentError(Exception):
    pass


class ParticipationConsentDecision(models.TextChoices):
    PENDING = "pending", "Pending"
    CONSENTED = "consented", "Consented"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"


class ParticipationConsent(models.Model):
    """One guardian's consent decision for one team membership."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="athletics_participation_consents",
    )
    membership = models.ForeignKey(
        "athletics.TeamMembership",
        on_delete=models.CASCADE,
        related_name="consents",
    )
    guardian_name = models.CharField(max_length=256)
    guardian_email = models.EmailField()
    token_sha256 = models.CharField(
        max_length=64,
        unique=True,
        help_text=(
            "sha256 of the raw URL-safe token. Raw token NEVER persisted; "
            "returned exactly once from mint()."
        ),
    )
    token_issued_at = models.DateTimeField(default=timezone.now, db_index=True)
    token_first_seen_at = models.DateTimeField(null=True, blank=True)
    consented_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    decision = models.CharField(
        max_length=16,
        choices=ParticipationConsentDecision.choices,
        default=ParticipationConsentDecision.PENDING,
        db_index=True,
    )
    consent_text_version = models.CharField(max_length=16)
    consent_text_sha256 = models.CharField(
        max_length=64,
        help_text="sha256 of the rendered consent text — immutable proof of what was agreed.",
    )
    ip_address_decision = models.GenericIPAddressField(null=True, blank=True)
    user_agent_decision = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "athletics"
        ordering = ["-token_issued_at"]
        indexes = [
            models.Index(fields=["membership", "decision"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"ParticipationConsent({self.pk} membership={self.membership_id} {self.decision})"

    # ─── Constructors / lookup ──────────────────────────────────────

    @classmethod
    def mint(
        cls,
        *,
        membership,
        guardian_name: str,
        guardian_email: str,
        consent_text: str,
        consent_text_version: str = CONSENT_TEXT_VERSION,
        expires_in_days: int = PARTICIPATION_CONSENT_EXPIRY_DAYS,
    ) -> Tuple[str, "ParticipationConsent"]:
        """Mint a consent token. Returns ``(raw_token, instance)`` — raw once."""
        if membership is None:
            raise ParticipationConsentError("mint requires a team membership")
        if not guardian_email:
            raise ParticipationConsentError("mint requires a guardian_email")
        raw_token = secrets.token_urlsafe(32)
        now = timezone.now()
        instance = cls.objects.create(
            school_id=membership.school_id,
            membership=membership,
            guardian_name=str(guardian_name)[:256],
            guardian_email=str(guardian_email)[:254],  # magic-number-allow: rfc5321-email-max-length
            token_sha256=_sha256_hex(raw_token),
            token_issued_at=now,
            expires_at=now + timedelta(days=max(1, int(expires_in_days))),
            consent_text_version=str(consent_text_version)[:16],
            consent_text_sha256=_sha256_hex(consent_text or ""),
        )
        logger.info(
            "participation_consent.minted sha_prefix=%s membership=%s",
            instance.token_sha256[:8],
            membership.pk,
            extra={"scope": "athletics_consent"},
        )
        return raw_token, instance

    @classmethod
    def lookup_by_raw_token(cls, raw_token: str) -> Optional["ParticipationConsent"]:
        """Lookup by sha of the raw token; None on miss (uniform-shape callers)."""
        if not raw_token or not isinstance(raw_token, str):
            return None
        if len(raw_token) < 16 or len(raw_token) > 128:
            return None
        return cls.objects.filter(  # tenant-isolation-allow: consent-lookup-by-token-sha-anonymous-by-design
            token_sha256=_sha256_hex(raw_token)
        ).first()

    def matches(self, raw_token: str) -> bool:
        if not raw_token or not isinstance(raw_token, str):
            return False
        return hmac.compare_digest(_sha256_hex(raw_token), self.token_sha256 or "")

    # ─── Properties ─────────────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_decided(self) -> bool:
        return self.decision != ParticipationConsentDecision.PENDING

    # ─── Transitions ────────────────────────────────────────────────

    def _guard_undecided(self) -> None:
        if self.is_decided:
            raise ParticipationConsentError("consent already decided")
        if self.is_expired:
            self.decision = ParticipationConsentDecision.EXPIRED
            self.save(update_fields=["decision", "updated_at"])
            raise ParticipationConsentError("consent token expired")

    def consent(self, request=None) -> None:
        """Guardian consented → the membership activates."""
        from apps.athletics.models.roster import TeamMembership

        # Guard OUTSIDE the atomic block so the expiry save survives the raise.
        self._guard_undecided()
        with transaction.atomic():
            now = timezone.now()
            self.decision = ParticipationConsentDecision.CONSENTED
            self.consented_at = now
            self._stamp_request(request)
            self.save()
            membership = self.membership
            if membership.status == TeamMembership.Status.PENDING:
                membership.status = TeamMembership.Status.ACTIVE
                if membership.joined_at is None:
                    membership.joined_at = now.date()
                membership.save(update_fields=["status", "joined_at", "updated_at"])
        self._audit("APPROVE")

    def decline(self, request=None) -> None:
        """Guardian declined → the membership is marked LEFT."""
        from apps.athletics.models.roster import TeamMembership

        self._guard_undecided()  # outside atomic — the expiry save must survive
        with transaction.atomic():
            now = timezone.now()
            self.decision = ParticipationConsentDecision.DECLINED
            self.declined_at = now
            self._stamp_request(request)
            self.save()
            membership = self.membership
            if membership.status == TeamMembership.Status.PENDING:
                membership.status = TeamMembership.Status.LEFT
                membership.left_at = now.date()
                membership.save(update_fields=["status", "left_at", "updated_at"])
        self._audit("REJECT")

    def mark_first_seen(self) -> None:
        if self.token_first_seen_at is None:
            self.token_first_seen_at = timezone.now()
            self.save(update_fields=["token_first_seen_at", "updated_at"])

    def _stamp_request(self, request) -> None:
        if request is None:
            return
        # XFF-first: behind the proxy REMOTE_ADDR is the load balancer, and a
        # constant infra IP is forensically worthless as consent evidence.
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            self.ip_address_decision = forwarded.split(",")[0].strip() or None
        else:
            self.ip_address_decision = request.META.get("REMOTE_ADDR") or None
        self.user_agent_decision = (request.META.get("HTTP_USER_AGENT") or "")[:256]

    def _audit(self, action: str) -> None:
        try:
            from apps.compliance.models_audit import AuditLog

            AuditLog.objects.create(
                action=action,
                user=None,
                model_name="ParticipationConsent",
                object_id=str(self.pk)[:200],
                object_repr=f"participation consent {self.decision} (membership {self.membership_id})"[:200],
                app_label="athletics",
                new_values={"decision": self.decision},
            )
        except Exception:  # noqa: BLE001 — audit must never block consent
            logger.warning("participation_consent_audit_failed consent=%s", self.pk)


__all__ = [
    "ParticipationConsent",
    "ParticipationConsentDecision",
    "ParticipationConsentError",
]
