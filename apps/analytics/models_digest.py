"""Digest delivery — operator-configured recipients for the AI risk digest.

One row per (school, channel, target) so a school can fan out to
multiple email addresses and Slack channels from one nightly run. The
`send_risk_digest` command iterates rows for each school and delivers.
"""

from __future__ import annotations

from django.db import models


class RiskDigestRecipient(models.Model):
    """A configured delivery target for the at-risk narrative digest."""

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SLACK_WEBHOOK = "slack_webhook", "Slack incoming webhook"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="risk_digest_recipients",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices)
    target = models.CharField(
        max_length=512,
        help_text="Email address for channel=email; webhook URL for channel=slack_webhook.",
    )
    label = models.CharField(
        max_length=120, blank=True,
        help_text="Operator-facing name (e.g. 'principal', '#success-team').",
    )
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "analytics"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "channel", "target"],
                name="uniq_risk_digest_recipient",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "enabled"]),
        ]
        verbose_name = "Risk digest recipient"
        verbose_name_plural = "Risk digest recipients"

    def __str__(self) -> str:
        return f"{self.label or self.target} ({self.channel})"
