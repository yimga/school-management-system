"""A number issued once and never issued again.

``generate_admission_number`` computed its sequence as
``StudentProfile.objects.filter(academic_year=...).count() + 1``. A count is not a
sequence: it goes DOWN when a row is deleted, so the next arrival is handed a departed
student's number. It also races -- two concurrent enrolments read the same count and both
believe they are issuing N -- and an admission number is the one value a school treats as
permanent, printed on documents and filed with the ministry.

The node mark (``identifier_policy_service.node_identifier_namespace``) fixed the OTHER
half: two nodes can no longer collide with each other. This fixes one node colliding with
itself, which the mark does nothing about, because the counter and the count are different
questions.

A counter row survives the deletion the count could not. It is keyed per node as well as
per year, so a box and the cloud keep separate counters -- neither has to ask the other
anything, which is what lets a box enrol a child with the internet down. It is deliberately
NOT on the sync rail: it is local bookkeeping, and syncing it would make two nodes fight
over one number line for no benefit.
"""

from __future__ import annotations

from django.db import models, transaction


class AdmissionNumberSequence(models.Model):
    """The next sequence number this node will issue, per school-year.

    One row per (school, academic year, node). ``next_seq`` only ever goes up.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="admission_sequences"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="admission_sequences",
    )
    #: Which node's number line this is. Same value the number itself carries, so a row
    #: cloned to a box at provisioning cannot be mistaken for the box's own counter.
    node_code = models.CharField(max_length=32)
    next_seq = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "academic_year", "node_code"],
                name="uniq_admission_sequence_per_school_year_node",
            )
        ]
        indexes = [models.Index(fields=["school", "academic_year"])]

    def __str__(self):
        return f"{self.school_id}/{self.academic_year_id}/{self.node_code} -> {self.next_seq}"


def _seed_from_existing(school, academic_year) -> int:
    """Where a brand-new counter starts on a school that has already enrolled people.

    The old code's answer for the very next number was ``count() + 1``, so starting there
    changes nothing about the number the school is about to see. It is a FLOOR, not the
    final answer: :func:`allocate_admission_seq` still steps past anything already taken,
    which is what covers a school that has deleted students (where the count is lower than
    the highest number it ever issued) without this module having to parse numbers back
    out of a format each school configures for itself.
    """
    from apps.people.models import StudentProfile

    return (
        StudentProfile.objects.filter(
            school=school, academic_year=academic_year
        ).count()
        + 1
    )


def allocate_admission_seq(school, academic_year, node_code, *, is_taken=None) -> int:
    """Claim the next number on this node's line, and never return it twice.

    ``is_taken(seq) -> bool`` lets the caller reject a number that a legacy row already
    holds. It is consulted under the same lock as the increment, so two concurrent
    enrolments cannot both step over the same obstacle and land on the same number.

    Row-locked rather than ``F("next_seq") + 1``, because the caller needs to KNOW which
    number it got. An expression update returns nothing to the caller and a read-back
    afterwards is exactly the race being closed.
    """
    with transaction.atomic():
        row, created = AdmissionNumberSequence.objects.select_for_update().get_or_create(
            school=school,
            academic_year=academic_year,
            node_code=node_code,
            defaults={"next_seq": _seed_from_existing(school, academic_year)},
        )
        if not created:
            # get_or_create's SELECT happens before the lock is available on the INSERT
            # path, so re-read the locked row rather than trusting the instance we were
            # handed. Without this the lock is held over a value read outside it.
            row = AdmissionNumberSequence.objects.select_for_update().get(pk=row.pk)

        seq = row.next_seq
        if is_taken is not None:
            # Bounded: a school whose numbers are ALL taken has a data problem no amount
            # of stepping will solve, and an unbounded loop would hold the row lock while
            # it looked for one. 10_000 is a school-year's worth of enrolments.
            for _ in range(10_000):
                if not is_taken(seq):
                    break
                seq += 1
        row.next_seq = seq + 1
        row.save(update_fields=["next_seq", "updated_at"])
        return seq
