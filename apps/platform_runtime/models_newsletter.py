"""NewsletterSubscription model (v4.00.98 Phase 3).

Public-facing marketing list with double-opt-in (DOI):

  pending → confirmed   (email verified via timed token)
  confirmed → unsubscribed   (one-click unsubscribe at any time)

Fields:

* ``email`` — case-insensitive unique
* ``source`` — free-form attribution slug ("marketing_home_footer", "demo_page")
* ``ip_hash`` — sha256[:16] of submitting IP (privacy-preserving, no raw IP)
* ``utm_source / utm_medium / utm_campaign`` — last attribution captured
* ``confirmation_token`` — TimestampSigner-signed token used by the
  verification URL (NOT stored after confirmation — set to empty)
* ``unsubscribe_token`` — persistent, signed; allows one-click unsub
* ``confirmed_at`` — timestamp when DOI completed; null while pending
* ``unsubscribed_at`` — timestamp when user opted out; null while active
* ``created_at`` / ``last_send_at`` — bookkeeping
"""

from __future__ import annotations

from django.db import models


class NewsletterSubscriptionStatus(models.TextChoices):
    PENDING = "pending", "Pending verification"
    CONFIRMED = "confirmed", "Confirmed"
    UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
    BOUNCED = "bounced", "Bounced"


class NewsletterSubscription(models.Model):
    """Public marketing-list subscription."""

    email = models.EmailField(max_length=254, unique=True, db_index=True)  # magic-number-allow: charfield-max-length
    status = models.CharField(
        max_length=16,
        choices=NewsletterSubscriptionStatus.choices,
        default=NewsletterSubscriptionStatus.PENDING,
        db_index=True,
    )

    source = models.CharField(max_length=64, blank=True, default="")
    ip_hash = models.CharField(max_length=32, blank=True, default="")

    utm_source = models.CharField(max_length=64, blank=True, default="")
    utm_medium = models.CharField(max_length=64, blank=True, default="")
    utm_campaign = models.CharField(max_length=128, blank=True, default="")

    confirmation_token = models.CharField(max_length=256, blank=True, default="")
    unsubscribe_token = models.CharField(max_length=256, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    last_send_at = models.DateTimeField(null=True, blank=True)

    send_count = models.PositiveIntegerField(default=0)
    bounce_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "Newsletter subscription"
        verbose_name_plural = "Newsletter subscriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="newslettersub_status_idx"),
            models.Index(fields=["source", "-created_at"], name="newslettersub_source_idx"),
            models.Index(fields=["confirmed_at"], name="newslettersub_confirmed_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.email} [{self.status}]"
