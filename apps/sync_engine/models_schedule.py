"""Tenant-owned sync schedule rules.

WHERE THIS LIVES AND WHY. ``apps.sync_engine`` is a SHARED app: one physical table
discriminated by the ``school`` FK, exactly like ``SyncApplyLedger`` and
``EdgeSyncDirective``. On a sovereign box there is only ever one school's rows here
anyway, and on the cloud the schedule is platform-level configuration ABOUT a tenant
rather than tenant curriculum data.

HOW IT REACHES THE BOX. The cloud cannot open a connection to a box — every transfer is
box-initiated — so a design where the cloud "triggers a sync at 09:00" cannot work. The
schedule is therefore replicated like any other row (``client_offline_id`` anchor +
``auto_now`` ``updated_at``, registered on the edge rail in ``apps.api.sync_services``)
and EVALUATED LOCALLY by the box against its own copy. A box that has never pulled one
runs the default, which is why the default has to be good enough to run a school forever.

A schedule change therefore takes effect at the box's NEXT cycle, not instantly. The Sync
Center says so in those words rather than implying otherwise.

WHY SCALAR COLUMNS AND NOT JSON. Every field on the edge rail has to survive
``save(update_fields=[...])`` and a JSON round trip through a bundle, on SQLite and
Postgres alike. Weekday sets and time lists are stored as short canonical CSV strings and
parsed on read: boring, portable, and diffable in a bundle. A JSONField would have been
one fewer parse and one more way for two deployments to disagree.
"""
from __future__ import annotations

import datetime as _dt

from django.core.exceptions import ValidationError
from django.db import models

from apps.sync_engine.schedule import (
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    MODE_AT_TIMES,
    MODE_INTERVAL,
    Rule,
)

_MAX_TIMES_PER_RULE = 12  # magic-number-allow: at-times entries per rule


def parse_days(raw: str) -> frozenset:
    """``"0,1,2"`` -> ``{0, 1, 2}``. Junk is dropped rather than raising.

    Read paths must never explode on a malformed row: a box that refuses to boot because
    one schedule string is wrong has turned a configuration typo into an outage. Save
    paths validate strictly (see :meth:`SyncSchedule.clean`), which is where a human is
    present to be told.
    """
    out = set()
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if chunk.isdigit() and 0 <= int(chunk) <= 6:
            out.add(int(chunk))
    return frozenset(out)


def format_days(days) -> str:
    return ",".join(str(d) for d in sorted(set(days)))


def parse_times(raw: str) -> tuple:
    """``"06:00,22:00"`` -> ``(time(6, 0), time(22, 0))``, sorted and deduplicated."""
    out = set()
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hour_s, _, minute_s = chunk.partition(":")
            hour, minute = int(hour_s), int(minute_s or 0)
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            out.add(_dt.time(hour, minute))
    return tuple(sorted(out))


def format_times(times) -> str:
    return ",".join(t.strftime("%H:%M") for t in sorted(set(times)))


class SyncSchedule(models.Model):
    """One rule in a tenant's sync schedule. A tenant may hold several.

    Term time and school holidays are two rules, not two products — so the union of
    enabled rules is the schedule, and :func:`apps.sync_engine.schedule.next_run_at`
    returns the earliest moment any of them fires.
    """

    class Mode(models.TextChoices):
        INTERVAL = MODE_INTERVAL, "Every N minutes, within a window"
        AT_TIMES = MODE_AT_TIMES, "At specific times"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="sync_schedules"
    )
    name = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="What this rule is for, e.g. 'Term time' or 'Overnight catch-up'.",
    )
    is_enabled = models.BooleanField(default=True)
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.INTERVAL)

    # Monday=0 .. Sunday=6, matching date.weekday() so nothing has to translate.
    days_of_week = models.CharField(max_length=32, blank=True, default="0,1,2,3,4,5,6")

    # INTERVAL mode.
    window_start = models.TimeField(null=True, blank=True)
    window_end = models.TimeField(null=True, blank=True)
    interval_minutes = models.PositiveIntegerField(null=True, blank=True)

    # AT_TIMES mode: "06:00,22:00".
    at_times = models.CharField(max_length=128, blank=True, default="")

    # Edge<->cloud bidirectional sync: change cursor + offline-insert anchor. Same shape
    # as every other synced entity so the generic rail carries this with no special case.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    client_offline_id = models.CharField(
        max_length=128, blank=True, default="", db_index=True
    )

    class Meta:
        verbose_name = "sync schedule rule"
        verbose_name_plural = "sync schedule rules"
        ordering = ("school_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_syncschedule_school_offline_id",
            ),
        ]
        indexes = [models.Index(fields=["school", "is_enabled"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name or f"Sync rule {self.pk}"

    # ------------------------------------------------------------------ shape --
    @property
    def days(self) -> frozenset:
        return parse_days(self.days_of_week)

    @property
    def times(self) -> tuple:
        return parse_times(self.at_times)

    def to_rule(self) -> Rule:
        """The pure-evaluator view of this row. No ORM beyond this boundary."""
        return Rule(
            mode=self.mode,
            days=self.days,
            window_start=self.window_start,
            window_end=self.window_end,
            interval_minutes=self.interval_minutes,
            times=self.times,
            label=self.name,
        )

    # ------------------------------------------------------------- validation --
    def clean(self):
        """Refuse the impossible, and say which field is wrong.

        A schedule that saves cleanly and then silently never fires is the failure mode
        this whole feature exists to avoid — the operator would have no way to tell it
        from a broken box, which is exactly the confusion that started this work.
        """
        errors = {}

        if not self.days:
            errors["days_of_week"] = ValidationError(
                "Choose at least one day, otherwise this rule can never run."
            )

        if self.mode == self.Mode.INTERVAL:
            if not self.window_start or not self.window_end:
                errors["window_start"] = ValidationError(
                    "A recurring rule needs a start and an end time."
                )
            if not self.interval_minutes:
                errors["interval_minutes"] = ValidationError("Choose how often to sync.")
            elif self.interval_minutes < MIN_INTERVAL_MINUTES:
                errors["interval_minutes"] = ValidationError(
                    f"Syncing more often than every {MIN_INTERVAL_MINUTES} minutes is not "
                    "allowed — it would keep the box talking to the cloud continuously "
                    "without moving any more data."
                )
            elif self.interval_minutes > MAX_INTERVAL_MINUTES:
                errors["interval_minutes"] = ValidationError(
                    "Choose an interval of a day or less."
                )
            # An end EARLIER than the start is read as an overnight window, deliberately —
            # 22:00 to 02:00 is a real and common thing to want. Only an end EQUAL to the
            # start is rejected, because that has no reading a human intended.
            if (
                self.window_start
                and self.window_end
                and self.window_start == self.window_end
            ):
                errors["window_end"] = ValidationError(
                    "The end time must be different from the start time. For an overnight "
                    "window, set an end earlier in the day than the start (22:00 to 02:00)."
                )
        elif self.mode == self.Mode.AT_TIMES:
            if not self.times:
                errors["at_times"] = ValidationError("Add at least one time of day.")
            elif len(self.times) > _MAX_TIMES_PER_RULE:
                errors["at_times"] = ValidationError(
                    f"At most {_MAX_TIMES_PER_RULE} times per rule. Use a recurring rule "
                    "instead of listing many times."
                )
        else:
            errors["mode"] = ValidationError("Unknown schedule type.")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Canonicalise so two deployments that mean the same thing store the same bytes —
        # otherwise "0,1,2" and "2,1,0" are one schedule that looks like two changes to the
        # delta cursor and re-syncs forever.
        self.days_of_week = format_days(self.days)
        if self.at_times:
            self.at_times = format_times(self.times)
        return super().save(*args, **kwargs)


def rules_for(school) -> list:
    """Enabled rules for ``school``, as pure evaluator Rules.

    Returns ``[]`` when nothing is configured, which every caller must read as "fall back
    to the adaptive cadence" — never as "do not sync".
    """
    if school is None:
        return []
    try:
        rows = SyncSchedule.objects.filter(school=school, is_enabled=True)
        return [row.to_rule() for row in rows]
    except Exception:  # noqa: BLE001 — an unmigrated box must still sync on the default
        return []
