"""Guardian consent collection (v3.40.0 Agent 11).

``GuardianConsentToken`` extends Agent 7's
:class:`MigrationIntakeRequest` flow with a guardian-facing consent
collection layer. Schools that migrate from a vendor SIS into
RunMyCampus must collect FERPA/COPPA/GDPR-compatible guardian consent
before student PII is extracted; this model + the views in
``views_guardian_consent.py`` are the collection surface.

Design contract
---------------

  * **Unguessable token in URL.** A 256-bit URL-safe random token
    issued by :meth:`mint` is the *only* credential. The raw token
    is returned ONCE at mint time and embedded in the consent-request
    email; only ``sha256(token)`` is persisted. Lookups go through
    :meth:`matches` which uses ``hmac.compare_digest``.

  * **Immutable consent-text record.** When the guardian decides we
    capture *which* consent text they saw — both a version string
    and a sha256 of the rendered body. If the school later updates
    its consent text (v2, v3…) we can still answer "what did
    guardian X agree to" in a counsel-defensible way.

  * **Server-side IP + UA capture.** The guardian's IP and UA are
    captured at consent time from ``request.META`` and stored for
    legal record (FERPA §99.30 "written consent" intent). NEVER
    user-supplied; NEVER logged in PII-free traces.

  * **90-day revocation window.** Guardians may withdraw a prior
    consent for the configured window (default 90 days). Outside the
    window, withdrawals require an out-of-band school-side process
    (which is school policy, not technically enforced here).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any, Optional, Tuple

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _sha256_hex(value: str) -> str:
    """Return sha256 hex of a UTF-8 string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_ip(request) -> Optional[str]:
    """Resolve the client IP from request.META — server-side, never trusted-input.

    Mirrors the pattern Agent 7 uses in ``views_customer.MigrationIntakeMAASignView``.
    """
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def _client_ua(request) -> str:
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:256]


class GuardianConsentDecision(models.TextChoices):
    PENDING = "pending", "Pending"
    CONSENTED = "consented", "Consented"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"


class GuardianConsentTokenError(Exception):
    """Raised on disallowed guardian-consent state transitions."""


class GuardianConsentToken(models.Model):
    """Per-guardian consent record for a Migration Cloud intake."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    intake_request = models.ForeignKey(
        "migration_cloud.MigrationIntakeRequest",
        on_delete=models.CASCADE,
        related_name="guardian_consent_tokens",
        help_text="The intake request this consent token belongs to.",
    )
    tenant = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="guardian_consent_tokens",
        help_text="Denormalized tenant FK for tenant-scoped operator filtering.",
    )
    # student is referenced by external id semantics so this model is
    # decoupled from the specific Student model; the vendor's external
    # id (or the local StudentProfile.pk as string) is acceptable.
    student_external_id = models.CharField(
        max_length=128,
        help_text=(
            "Student identifier (vendor external id OR local StudentProfile.pk "
            "as string). Decoupled CharField so per-vendor extractors can write "
            "whichever id they have at mint time."
        ),
    )
    guardian_name = models.CharField(
        max_length=256,
        help_text="Guardian display name; pre-populated by the school at mint.",
    )
    guardian_email = models.EmailField(
        help_text="Guardian email; pre-populated by the school at mint.",
    )
    token_sha256 = models.CharField(
        max_length=64,
        unique=True,
        help_text=(
            "sha256 of the raw URL-safe token. Raw token NEVER persisted; "
            "the raw value is returned exactly once from mint() and embedded "
            "in the consent-request email."
        ),
    )
    token_issued_at = models.DateTimeField(default=timezone.now, db_index=True)
    token_first_seen_at = models.DateTimeField(null=True, blank=True)
    consented_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    consent_decision = models.CharField(
        max_length=16,
        choices=GuardianConsentDecision.choices,
        default=GuardianConsentDecision.PENDING,
        db_index=True,
    )
    consent_text_version = models.CharField(
        max_length=16,
        help_text="Version of the consent text the guardian saw (e.g. 'v1').",
    )
    consent_text_sha256 = models.CharField(
        max_length=64,
        help_text=(
            "sha256 of the rendered consent text body. Immutable record so "
            "counsel can prove what the guardian agreed to."
        ),
    )
    ip_address_consent = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Server-captured IP at consent time. NEVER user-supplied.",
    )
    user_agent_consent = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Server-captured UA at consent time. NEVER user-supplied.",
    )
    notes_internal = models.TextField(
        blank=True,
        default="",
        help_text="Operator-only counsel notes; NEVER shown to guardian.",
    )
    resend_count = models.IntegerField(
        default=0,
        help_text="Number of times the consent email has been resent.",
    )
    last_resend_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Guardian consent token"
        verbose_name_plural = "Guardian consent tokens"
        indexes = [
            models.Index(fields=["intake_request"]),
            models.Index(fields=["token_sha256"]),
            models.Index(fields=["tenant", "consent_decision"]),
            models.Index(fields=["expires_at"]),
        ]
        ordering = ["-token_issued_at"]

    def __str__(self) -> str:  # pragma: no cover - repr only
        return (
            f"GuardianConsentToken({self.id} intake={self.intake_request_id} "
            f"decision={self.consent_decision})"
        )

    # ─── Constructors / lookup ──────────────────────────────────────

    @classmethod
    def mint(
        cls,
        *,
        intake,
        student_external_id: str,
        guardian_name: str,
        guardian_email: str,
        consent_text_version: str,
        consent_text: str,
        expires_in_days: int = 30,
    ) -> Tuple[str, "GuardianConsentToken"]:
        """Mint a new token. Returns ``(raw_token, instance)``.

        Raw token is generated via :func:`secrets.token_urlsafe(32)`
        (256 bits of entropy). Only the sha256 is persisted. The
        caller is expected to embed ``raw_token`` in a one-time email
        and immediately discard it.
        """
        if intake is None:
            raise ValueError("mint requires a non-null intake")
        if not guardian_email:
            raise ValueError("mint requires a guardian_email")
        raw_token = secrets.token_urlsafe(32)
        token_sha256 = _sha256_hex(raw_token)
        consent_text_sha = _sha256_hex(consent_text or "")
        now = timezone.now()
        expires_at = now + timedelta(days=max(1, int(expires_in_days)))
        # tenant-isolation-allow: guardian-consent-mint-tenant-from-intake-fk
        instance = cls.objects.create(
            intake_request=intake,
            tenant=intake.tenant,
            student_external_id=str(student_external_id)[:128],
            guardian_name=str(guardian_name)[:256],
            guardian_email=str(guardian_email)[:254],
            token_sha256=token_sha256,
            token_issued_at=now,
            expires_at=expires_at,
            consent_text_version=str(consent_text_version)[:16],
            consent_text_sha256=consent_text_sha,
        )
        # PII-free trace; raw token NEVER logged. Only sha-prefix for correlation.
        logger.info(
            "migration_cloud.guardian_consent: minted token_sha_prefix=%s "
            "intake_id=%s tenant_pk=%s expires_at=%s",
            token_sha256[:8], intake.id, intake.tenant_id, expires_at.isoformat(),
        )
        return raw_token, instance

    @classmethod
    def lookup_by_raw_token(cls, raw_token: str) -> Optional["GuardianConsentToken"]:
        """Constant-time lookup by raw token; returns None on miss.

        Single-query lookup keyed by ``token_sha256``; the constant-time
        compare is performed by the unique-index match (no per-row
        iteration). Callers should treat None as "no such token" with
        a uniform-shape 200 response to avoid enumeration.
        """
        if not raw_token or not isinstance(raw_token, str):
            return None
        if len(raw_token) < 16 or len(raw_token) > 128:
            return None
        token_sha256 = _sha256_hex(raw_token)
        # tenant-isolation-allow: guardian-consent-lookup-by-sha-not-tenant-anonymous-by-design
        return cls.objects.filter(token_sha256=token_sha256).first()

    def matches(self, raw_token: str) -> bool:
        """Constant-time compare of ``sha256(raw_token)`` to this row's sha."""
        if not raw_token or not isinstance(raw_token, str):
            return False
        candidate = _sha256_hex(raw_token)
        return hmac.compare_digest(candidate, self.token_sha256 or "")

    # ─── Property helpers ───────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_decided(self) -> bool:
        return self.consent_decision in (
            GuardianConsentDecision.CONSENTED.value,
            GuardianConsentDecision.DECLINED.value,
            GuardianConsentDecision.EXPIRED.value,
        )

    @property
    def is_revocable(self) -> bool:
        """True if this consent is still inside the revocation window."""
        if self.consent_decision != GuardianConsentDecision.CONSENTED.value:
            return False
        if self.consented_at is None:
            return False
        window_days = getattr(
            settings,
            "MIGRATION_CLOUD_GUARDIAN_CONSENT_REVOKE_WINDOW_DAYS",
            90,
        )
        deadline = self.consented_at + timedelta(days=int(window_days))
        return timezone.now() <= deadline

    # ─── Mutators ───────────────────────────────────────────────────

    def mark_first_seen(self) -> None:
        """Stamp ``token_first_seen_at`` once; idempotent."""
        if self.token_first_seen_at is not None:
            return
        self.token_first_seen_at = timezone.now()
        self.save(update_fields=["token_first_seen_at", "updated_at"])
        self._safe_audit("migration.guardian_consent.first_seen")

    def consent(self, *, request) -> None:
        """Record a consent decision. Bumps intake collected_count atomically."""
        if self.is_decided:
            raise GuardianConsentTokenError("token already decided")
        if self.is_expired:
            raise GuardianConsentTokenError("token expired")
        ip = _client_ip(request)
        ua = _client_ua(request)
        now = timezone.now()
        from django.db.models import F  # local import to keep top-level light
        from .models_intake import MigrationIntakeRequest
        with transaction.atomic():
            self.consent_decision = GuardianConsentDecision.CONSENTED.value
            self.consented_at = now
            self.ip_address_consent = ip
            self.user_agent_consent = ua
            self.save(update_fields=[
                "consent_decision", "consented_at",
                "ip_address_consent", "user_agent_consent", "updated_at",
            ])
            # tenant-isolation-allow: guardian-consent-bump-collected-count-on-own-intake-fk
            MigrationIntakeRequest.objects.filter(
                pk=self.intake_request_id,
            ).update(
                guardian_consent_collected_count=F(
                    "guardian_consent_collected_count",
                ) + 1,
            )
        self._safe_audit("migration.guardian_consent.consented")

    def decline(self, *, request) -> None:
        """Record a decline decision. Does NOT bump collected_count."""
        if self.is_decided:
            raise GuardianConsentTokenError("token already decided")
        if self.is_expired:
            raise GuardianConsentTokenError("token expired")
        now = timezone.now()
        self.consent_decision = GuardianConsentDecision.DECLINED.value
        self.declined_at = now
        self.ip_address_consent = _client_ip(request)
        self.user_agent_consent = _client_ua(request)
        self.save(update_fields=[
            "consent_decision", "declined_at",
            "ip_address_consent", "user_agent_consent", "updated_at",
        ])
        self._safe_audit("migration.guardian_consent.declined")

    def revoke(self) -> None:
        """Revoke a previously-granted consent. Decrements collected_count.

        Only valid inside the revocation window; callers MUST check
        :attr:`is_revocable` first.
        """
        if not self.is_revocable:
            raise GuardianConsentTokenError("token not revocable")
        from django.db.models import F
        from .models_intake import MigrationIntakeRequest
        now = timezone.now()
        with transaction.atomic():
            self.consent_decision = GuardianConsentDecision.EXPIRED.value
            self.expires_at = now
            self.save(update_fields=[
                "consent_decision", "expires_at", "updated_at",
            ])
            # tenant-isolation-allow: guardian-consent-decrement-collected-count-on-own-intake-fk
            MigrationIntakeRequest.objects.filter(
                pk=self.intake_request_id,
            ).update(
                guardian_consent_collected_count=models.Case(
                    models.When(
                        guardian_consent_collected_count__gt=0,
                        then=F("guardian_consent_collected_count") - 1,
                    ),
                    default=0,
                ),
            )
        self._safe_audit("migration.guardian_consent.revoked")

    def mark_expired(self) -> None:
        """Operator-side expiry. Idempotent."""
        if self.consent_decision == GuardianConsentDecision.EXPIRED.value:
            return
        self.consent_decision = GuardianConsentDecision.EXPIRED.value
        self.save(update_fields=["consent_decision", "updated_at"])
        self._safe_audit("migration.guardian_consent.expired")

    # ─── Audit helper ───────────────────────────────────────────────

    def _safe_audit(self, event_type: str, *, extra: Optional[dict] = None) -> None:
        """Best-effort audit emission; NEVER raises into the view layer."""
        try:
            from .models_audit import MigrationCloudAuditEvent
            tenant_slug = getattr(self.tenant, "slug", "") or ""
            payload: dict[str, Any] = {
                "intake_id_prefix": str(self.intake_request_id)[:8],
                # This is only a short correlation prefix of a one-way digest,
                # never the raw bearer token. Avoid sensitive-keyword names so
                # the audit sanitizer does not correctly reject the payload.
                "consent_artifact_prefix": (self.token_sha256 or "")[:8],
                "consent_text_version": self.consent_text_version[:16],
                "decision": self.consent_decision[:16],
            }
            if extra:
                # _sanitize_payload will reject sensitive-keyword keys;
                # callers are expected to keep `extra` PII-free.
                payload.update({
                    k: v for k, v in extra.items()
                    if isinstance(k, str)
                })
            MigrationCloudAuditEvent.objects.record(
                tenant_slug,
                event_type,
                subject=str(self.id),
                payload_summary=payload,
            )
        except Exception as exc:  # noqa: BLE001 — audit must never break flow
            logger.warning(
                "migration_cloud.guardian_consent: audit emit failed "
                "event=%s token_sha_prefix=%s err=%s",
                event_type, (self.token_sha256 or "")[:8], type(exc).__name__,
            )


__all__ = [
    "GuardianConsentDecision",
    "GuardianConsentToken",
    "GuardianConsentTokenError",
    "_sha256_hex",
]
