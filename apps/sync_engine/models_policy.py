"""How a tenant's schedule behaves AROUND the rules: the check-in ceiling and catch-up.

WHY THIS IS A SYNCED ROW AND NOT AN ENV VAR. Both settings here are decisions the SCHOOL
makes, and both are acted on by the BOX. The cloud cannot open a connection to a box, so
a value that lives only in ``deploy/selfhost/.env`` on the host can never be set by the
administrator who cares about it — which is exactly how ``RMC_EDGE_SYNC_IDLE_CEILING_SECONDS``
started life, and exactly why "the tenant can configure their sync" was only half true.
A tenant decision that has to reach a box has to ride the rail. Same reasoning as
:class:`~apps.sync_engine.models_schedule.SyncSchedule`, same anchor fields, same rail.

ONE ROW PER SCHOOL, not one per rule. "How long may this box stay silent?" is not a
property of a Tuesday-afternoon window; it is a property of the deployment. A tenant with
four rules has one answer to it, and putting it on the rule would have forced them to keep
four copies in agreement.

WHAT IS DELIBERATELY *NOT* HERE. DST handling is not a setting. There is one defensible
answer in each direction (never drop a run; never double one), the tests assert both, and
offering a switch would only let a school choose the wrong one for a decision they should
never have had to think about. The Sync Center now SHOWS what will happen instead --
visible, which was the actual problem, rather than configurable, which was not.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models

# The floor is the schedule engine's own floor: below this the ceiling would be tighter
# than the tightest rule a tenant can write, which is not a ceiling at all.
MIN_IDLE_CEILING_MINUTES = 5

# The cap is an operator-safety limit, not a preference. `EdgeSyncDirective` is the ONLY
# cloud->box channel and it is COLLECTED BY THE BOX ASKING, so the ceiling is also the
# worst-case delay on "Queue full resync" reaching this box. A day is already a long time
# to wait for an instruction to land; beyond it, a box is indistinguishable from one that
# has been switched off, and no support conversation survives that.
MAX_IDLE_CEILING_MINUTES = 24 * 60

DEFAULT_IDLE_CEILING_MINUTES = 60

# See SyncPolicy.save(). One policy per school, so one stable anchor per school.
SINGLETON_ANCHOR = "sync-policy"


@dataclass(frozen=True)
class ResolvedPolicy:
    """A policy that always answers, whatever the database says.

    Read paths take this rather than the model so an unmigrated box, a missing row or a
    dead connection all degrade to the documented default instead of stopping a sync.
    """

    idle_ceiling_minutes: int = DEFAULT_IDLE_CEILING_MINUTES
    catch_up_missed: bool = True
    source: str = "default"

    @property
    def idle_ceiling_seconds(self) -> int:
        return int(self.idle_ceiling_minutes) * 60


class SyncPolicy(models.Model):
    """One row per school. Created on demand; absence means "the defaults"."""

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="sync_policy"
    )

    idle_ceiling_minutes = models.PositiveIntegerField(
        default=DEFAULT_IDLE_CEILING_MINUTES,
        help_text=(
            "Longest this box may go without checking in, even when no run is scheduled. "
            "The cloud cannot contact a box, so this is also how long an operator "
            "instruction can take to arrive."
        ),
    )

    catch_up_missed = models.BooleanField(
        default=True,
        help_text=(
            "If the box was off or offline through a scheduled time, sync once as soon as "
            "it is back instead of waiting for the next scheduled time."
        ),
    )

    # Edge<->cloud rail anchor, identical in shape to every other synced entity.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    client_offline_id = models.CharField(
        max_length=128, blank=True, default="", db_index=True
    )

    class Meta:
        verbose_name = "sync policy"
        verbose_name_plural = "sync policies"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_syncpolicy_school_offline_id",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Sync policy for {self.school_id}"

    def clean(self):
        value = self.idle_ceiling_minutes
        if value is None or value < MIN_IDLE_CEILING_MINUTES:
            raise ValidationError(
                {
                    "idle_ceiling_minutes": ValidationError(
                        f"Check in at least every {MIN_IDLE_CEILING_MINUTES} minutes."
                    )
                }
            )
        if value > MAX_IDLE_CEILING_MINUTES:
            raise ValidationError(
                {
                    "idle_ceiling_minutes": ValidationError(
                        "Check in at least once a day. The cloud cannot contact this box, "
                        "so a longer gap is also how long an operator instruction would "
                        "wait, and a box that silent cannot be told to start again."
                    )
                }
            )

    def save(self, *args, **kwargs):
        # A DETERMINISTIC anchor, because this row is a singleton and the rail matches
        # rows by (school, client_offline_id).
        #
        # SyncSchedule can afford a random anchor: it is a plain FK, so two rules created
        # on two sides are simply two rules. This is a OneToOne. If the cloud and the box
        # each minted their own anchor for their own policy row, the rail would treat them
        # as two DIFFERENT rows and try to INSERT the far side's -- straight into the
        # one-per-school constraint, on every cycle, forever. Giving both sides the same
        # anchor makes it one row that converges by last-write-wins, which is what a
        # settings row should do.
        #
        # A constant is enough: the anchor only has to be unique WITHIN a school's rows,
        # and there is exactly one of these per school. It deliberately does not embed a
        # school id -- School is a SHARED model whose pk is not portable box<->cloud.
        if not self.client_offline_id:
            self.client_offline_id = SINGLETON_ANCHOR
        return super().save(*args, **kwargs)

    def to_resolved(self) -> ResolvedPolicy:
        return ResolvedPolicy(
            idle_ceiling_minutes=int(self.idle_ceiling_minutes),
            catch_up_missed=bool(self.catch_up_missed),
            source="tenant",
        )


def policy_for(school) -> ResolvedPolicy:
    """The school's policy, or the documented defaults. Never raises.

    Clamped on READ as well as on save: a row that arrived down the rail from an older
    build, or was written straight to the database, must not be able to put this box
    outside the bounds the surface enforces.
    """
    if school is None:
        return ResolvedPolicy()
    try:
        row = SyncPolicy.objects.filter(school=school).first()
    except Exception:  # noqa: BLE001 — an unmigrated box still syncs on the default
        return ResolvedPolicy()
    if row is None:
        return ResolvedPolicy()
    resolved = row.to_resolved()
    clamped = min(
        MAX_IDLE_CEILING_MINUTES,
        max(MIN_IDLE_CEILING_MINUTES, resolved.idle_ceiling_minutes),
    )
    if clamped != resolved.idle_ceiling_minutes:
        return ResolvedPolicy(
            idle_ceiling_minutes=clamped,
            catch_up_missed=resolved.catch_up_missed,
            source="tenant (clamped)",
        )
    return resolved


__all__ = [
    "DEFAULT_IDLE_CEILING_MINUTES",
    "SINGLETON_ANCHOR",
    "MAX_IDLE_CEILING_MINUTES",
    "MIN_IDLE_CEILING_MINUTES",
    "ResolvedPolicy",
    "SyncPolicy",
    "policy_for",
]
