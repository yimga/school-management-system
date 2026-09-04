"""Identity provisioning requests: how a box-created person reaches the cloud.

THE PROBLEM THIS SOLVES, stated the way it was actually reported: "if a user is
added on the box the cloud should ingest it on the next sync, and vice versa --
we keep insisting on a 100% replica and it is not configured that way."

The vice-versa half is done and has been since 2026-09-02: ``export_tenant_staff``
on the cloud, ``import_tenant_staff`` on the box. The authentication decision was
already made by a human up there; the box is just handed the result.

The box -> cloud half is the one that could not be a sync change. ``teacher`` and
``student_guardian`` both require an ``accounts.User``, and the rail creating one
would mean a box can mint a login on the cloud -- so a stolen or tampered box
becomes an account factory, and every "who may sign in" decision moves from a
person to whatever arrives in a bundle. That is why the insert is held, and the
hold is right.

What was missing is the OTHER half of a refusal: somewhere for it to go. A box
would submit the same 39 teachers on all 687 cycles of a day, be refused 39 times
each cycle, and nothing anywhere asked a human the question. The refusal was
correct and the outcome was that the staff never existed.

A request row is the answer, and it is not a loophole:

* what rides up is DATA -- a name, a staff id, a phone, a requested role. No
  password, no session, no permission. It grants nothing on arrival;
* a human on the cloud approves it, which is the authentication decision the hold
  says must be explicit, made in the one place it can legitimately be made;
* approval mints the User carrying the box's ``client_offline_id``, so the next
  ordinary sync matches the two rows by anchor and converges them. No second
  identity, no merge.

The row is unique per ``(school, entity_type, client_offline_id)``. That is
load-bearing rather than tidy: without it the box's re-submission every cycle
would write a new request each time, and a day of 687 cycles would bury the
queue under 26,000 copies of the same question.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ProvisioningRequest(models.Model):
    """A box asking the cloud to create a person who needs a login."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        DECLINED = "DECLINED", "Declined"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="provisioning_requests",
    )
    #: The rail entity that was refused: "teacher" or "student_guardian".
    entity_type = models.CharField(max_length=64, db_index=True)
    #: The BOX's anchor for the row. Approval carries it onto the created record,
    #: which is the whole reason the two sides converge afterwards instead of
    #: ending up with one person twice.
    # 128 to match TeacherProfile.client_offline_id exactly. A longer value here
    # would be storable in the queue and then unstorable on the record approval
    # creates, so the anchor would be truncated at the one moment it has to match.
    client_offline_id = models.CharField(max_length=128, db_index=True)
    #: The refused insert's portable field values. Never a credential: the rail
    #: drops user_id as non-portable before this is written, and nothing in the
    #: sync payload carries a password, a hash or a session.
    payload = models.JSONField(default=dict, blank=True)
    #: What the box called the person's job. A REQUEST, not a grant -- approval
    #: decides the role, and the same forbidden set the importer uses applies.
    requested_role = models.CharField(max_length=64, blank=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    #: Bumped every time the box re-submits. The queue can then say "asked 687
    #: times since Tuesday", which is the number that makes someone act.
    last_seen_at = models.DateTimeField(auto_now=True)
    times_seen = models.PositiveIntegerField(default=1)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    #: What approval actually created, so the decision is auditable after the fact.
    created_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "entity_type", "client_offline_id"],
                name="uniq_provisioning_request_per_anchor",
            ),
        ]
        indexes = [models.Index(fields=["school", "status"])]

    def __str__(self) -> str:
        name = (self.payload or {}).get("last_name") or self.client_offline_id
        return f"{self.entity_type} {name} ({self.status})"

    @property
    def display_name(self) -> str:
        data = self.payload or {}
        parts = [str(data.get("first_name") or "").strip(), str(data.get("last_name") or "").strip()]
        return " ".join(p for p in parts if p) or self.client_offline_id
