"""Wave B — G5: user-friction telemetry.

A row per ``(user, school, view_name, kind)`` aggregated per UTC day. The
browser-side recorder (``static/js/rmc-friction.js``) POSTs raw events to
``/api/observability/friction/`` and the endpoint upserts (incrementing
``count`` + updating ``last_seen``) rather than writing one row per event.

Why a separate model instead of folding into Sentry / structured logs:

* The signal we care about ("teacher is stuck on the gradebook form") is
  per-user-per-view friction, not per-request errors. Sentry already
  captures the latter; this captures the former.
* We want a join-friendly table for the nightly digest that emails
  success owners using the warm-tone ``CommunicationTemplate`` system.
* Rows are tenant-scoped (school FK) so retention and access policies
  align with the rest of tenant data.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


# Canonical friction kinds. Adding a new kind requires (a) extending this
# tuple, (b) recording it from the JS side, and (c) optionally surfacing
# it in the digest copy.
FRICTION_KINDS: tuple[tuple[str, str], ...] = (
    ("validation_retry", "Form submitted with errors ≥3 times"),
    ("form_abandon", "Started a form, navigated away without submit"),
    ("dwell_excess", "Lingered on a step far beyond normal"),
    ("repeat_error", "Same client-side error fired 3× in a session"),
)
FRICTION_KIND_CODES: frozenset[str] = frozenset(code for code, _ in FRICTION_KINDS)


class FrictionEvent(models.Model):
    """One ``(user, school, view_name, kind, utc_day)`` rollup.

    The combo is enforced by the unique constraint below so the POST
    endpoint can do a simple ``update_or_create`` without race-prone
    counter logic on the Python side.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="friction_events",
        help_text="Authenticated actor if available; null for anonymous.",
    )
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="friction_events",
    )
    view_name = models.CharField(
        max_length=200,  # magic-number-allow: Django CharField max_length convention
        db_index=True,
        help_text="Django URL-conf name, route template, or stable JS view-id.",
    )
    kind = models.CharField(
        max_length=32,
        choices=FRICTION_KINDS,
        db_index=True,
    )
    utc_day = models.DateField(db_index=True, help_text="UTC day the rollup covers.")
    count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    last_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Most recent client-side context (field names, error code, dwell ms).",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when an operator acknowledges or auto-resolution fires.",
    )

    class Meta:
        verbose_name = "Friction event"
        verbose_name_plural = "Friction events"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "view_name", "kind", "utc_day"],
                name="uniq_friction_actor_view_kind_day",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "kind", "utc_day"]),
            models.Index(fields=["resolved_at"]),
        ]
        ordering = ("-last_seen",)

    def __str__(self) -> str:
        actor = self.user_id or "anon"
        return f"{actor}·{self.view_name}·{self.kind}·{self.utc_day}"

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
