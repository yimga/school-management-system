"""Guardian consent artifact for inter-school transfers (Wave B).

Clones the Migration Cloud ``GuardianConsentToken`` discipline
(design §4 / §5 step 2): the raw token is returned exactly once from
``mint()`` and never persisted (sha256 only, constant-time compare), the
consent text the guardian saw is recorded immutably (version + sha256),
decision IP/UA are server-captured, and every transition is journaled onto
the case and audited best-effort. A transfer case cannot leave
``consent_pending`` except through one of these rows.
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

logger = logging.getLogger(__name__)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


class TransferConsentError(Exception):
    pass


class TransferConsentDecision(models.TextChoices):
    PENDING = "pending", "Pending"
    CONSENTED = "consented", "Consented"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"


class TransferConsent(models.Model):
    """One guardian's consent decision for one transfer case."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        "people.TransferCase",
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
        choices=TransferConsentDecision.choices,
        default=TransferConsentDecision.PENDING,
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
        app_label = "people"
        ordering = ["-token_issued_at"]
        indexes = [
            models.Index(fields=["case", "decision"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"TransferConsent({self.pk} case={self.case_id} {self.decision})"

    # ─── Constructors / lookup ──────────────────────────────────────

    @classmethod
    def mint(
        cls,
        *,
        case,
        guardian_name: str,
        guardian_email: str,
        consent_text_version: str,
        consent_text: str,
        expires_in_days: int = 30,
    ) -> Tuple[str, "TransferConsent"]:
        """Mint a consent token. Returns ``(raw_token, instance)`` — raw once."""
        if case is None:
            raise TransferConsentError("mint requires a transfer case")
        if not guardian_email:
            raise TransferConsentError("mint requires a guardian_email")
        raw_token = secrets.token_urlsafe(32)
        now = timezone.now()
        instance = cls.objects.create(
            case=case,
            guardian_name=str(guardian_name)[:256],
            guardian_email=str(guardian_email)[:254],  # magic-number-allow: rfc5321-email-max-length
            token_sha256=_sha256_hex(raw_token),
            token_issued_at=now,
            expires_at=now + timedelta(days=max(1, int(expires_in_days))),
            consent_text_version=str(consent_text_version)[:16],
            consent_text_sha256=_sha256_hex(consent_text or ""),
        )
        logger.info(
            "transfer_consent.minted sha_prefix=%s case=%s",
            instance.token_sha256[:8],
            case.pk,
            extra={"scope": "transfer_consent"},
        )
        return raw_token, instance

    @classmethod
    def lookup_by_raw_token(cls, raw_token: str) -> Optional["TransferConsent"]:
        """Lookup by sha of the raw token; None on miss (anti-enumeration: callers
        should return a uniform-shape page either way)."""
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
        return self.decision != TransferConsentDecision.PENDING

    # ─── Transitions ────────────────────────────────────────────────

    def _guard_undecided(self) -> None:
        if self.is_decided:
            raise TransferConsentError("consent already decided")
        if self.is_expired:
            self.decision = TransferConsentDecision.EXPIRED
            self.save(update_fields=["decision", "updated_at"])
            raise TransferConsentError("consent token expired")

    def consent(self, request=None) -> None:
        """Guardian consented → the case advances to APPROVED."""
        from apps.people.models_transfer import TransferCase

        # Guard OUTSIDE the atomic block: on expiry it saves EXPIRED then
        # raises, and that save must survive the raise (an in-block raise
        # would roll it back).
        self._guard_undecided()
        with transaction.atomic():
            now = timezone.now()
            self.decision = TransferConsentDecision.CONSENTED
            self.consented_at = now
            self._stamp_request(request)
            self.save()
            if self.case.status == TransferCase.Status.CONSENT_PENDING:
                self.case.consent_reference = str(self.pk)
                self.case.save(update_fields=["consent_reference", "updated_at"])
                self.case.advance(
                    TransferCase.Status.APPROVED,
                    note=f"guardian consented (consent {str(self.pk)[:8]})",
                )
        self._audit("APPROVE")

    def decline(self, request=None) -> None:
        """Guardian declined → the case is cancelled."""
        from apps.people.models_transfer import TransferCase

        self._guard_undecided()  # outside atomic — the expiry save must survive the raise
        with transaction.atomic():
            self.decision = TransferConsentDecision.DECLINED
            self.declined_at = timezone.now()
            self._stamp_request(request)
            self.save()
            if self.case.status == TransferCase.Status.CONSENT_PENDING:
                self.case.advance(
                    TransferCase.Status.CANCELLED,
                    note=f"guardian declined (consent {str(self.pk)[:8]})",
                )
        self._audit("REJECT")

    def mark_first_seen(self) -> None:
        if self.token_first_seen_at is None:
            self.token_first_seen_at = timezone.now()
            self.save(update_fields=["token_first_seen_at", "updated_at"])

    def _stamp_request(self, request) -> None:
        if request is None:
            return
        # XFF-first: behind the proxy REMOTE_ADDR is the load balancer, and
        # a constant infra IP is forensically worthless as consent evidence.
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
                model_name="TransferConsent",
                object_id=str(self.pk)[:200],
                object_repr=f"transfer consent {self.decision} (case {self.case_id})"[:200],
                app_label="people",
                new_values={"decision": self.decision},
            )
        except Exception:  # noqa: BLE001 — audit must never block consent
            logger.warning("transfer_consent_audit_failed consent=%s", self.pk)


__all__ = [
    "TransferConsent",
    "TransferConsentDecision",
    "TransferConsentError",
]
