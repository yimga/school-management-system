"""Item 2.4 backfill — attribute existing Room / TimeSlot rows to a school.

WHY THIS IS THE CAREFUL PART. ``Room.school`` and ``TimeSlot.school`` were added
nullable in 0070. Filling them in is the destructive direction: handing a row
that several schools are actually using to ONE of them removes it from all the
others the moment anything filters on ``school``. So this migration only writes
an owner where the owner is UNAMBIGUOUS, and leaves everything else NULL.

NULL is a safe resting state, not a deferred bug. ``TimetableGenerator._scoped``
selects ``school IS NULL OR school = <mine>``, so an unattributed room or period
keeps behaving exactly as it did before item 2.4: visible to every school on the
instance. Nothing is lost by declining to guess.

THREE RULES, most confident first:

1. USAGE-DERIVED. A row referenced by ``ScheduleEntry`` rows that all resolve
   (entry -> schedule -> academic_year -> school) to exactly ONE school is owned
   by that school. Real evidence from real bookings, not a heuristic.
2. CONTESTED -> NULL. Two or more distinct schools have booked the row, so no
   single owner exists. Leave it shared.
3. SINGLE-TENANT FALLBACK. If the whole database contains exactly one School,
   every remaining unattributed row belongs to it by construction — there is
   nobody else. (Under schema-per-tenant this branch is normally skipped,
   because ``schools_school`` lives in the public schema and lists every
   tenant; those instances are covered by rules 1 and 2.)

NO UNIQUENESS RISK. Both per-school uniques added in 0070 are strictly weaker
than the global constraints they replaced: ``Room.name`` was globally unique and
``TimeSlot`` was globally unique on (day_of_week, start_time, end_time). Any set
of rows that satisfied a GLOBAL unique still satisfies the same unique once
partitioned by school, so no assignment this migration can make is able to
collide.
"""

from django.db import migrations


def backfill_school(apps, schema_editor):
    Room = apps.get_model("academics", "Room")
    TimeSlot = apps.get_model("academics", "TimeSlot")
    ScheduleEntry = apps.get_model("academics", "ScheduleEntry")
    School = apps.get_model("schools", "School")

    # Rule 1/2 — derive ownership from actual bookings.
    room_owners: dict = {}
    slot_owners: dict = {}
    rows = ScheduleEntry.objects.values_list(
        "room_id", "time_slot_id", "schedule__academic_year__school_id"
    )
    for room_id, slot_id, school_id in rows.iterator():
        if school_id is None:
            continue
        if room_id is not None:
            room_owners.setdefault(room_id, set()).add(school_id)
        if slot_id is not None:
            slot_owners.setdefault(slot_id, set()).add(school_id)

    for room_id, owners in room_owners.items():
        if len(owners) != 1:
            continue  # Contested — rule 2.
        Room.objects.filter(pk=room_id, school__isnull=True).update(
            school_id=next(iter(owners))
        )

    for slot_id, owners in slot_owners.items():
        if len(owners) != 1:
            continue
        TimeSlot.objects.filter(pk=slot_id, school__isnull=True).update(
            school_id=next(iter(owners))
        )

    # Rule 3 — single-tenant instance. ``[:2]`` so "is there more than one?"
    # costs two rows, not a full count of a large tenant table.
    school_ids = list(School.objects.values_list("id", flat=True).order_by("id")[:2])
    if len(school_ids) == 1:
        only_school = school_ids[0]
        Room.objects.filter(school__isnull=True).update(school_id=only_school)
        TimeSlot.objects.filter(school__isnull=True).update(school_id=only_school)


def unbackfill_school(apps, schema_editor):
    """Reverse: drop the attribution, restoring the pre-2.4 shared pool.

    Safe and total — every row was NULL before this migration ran, and NULL is
    the permissive state, so reversing cannot hide anything from anyone.
    """
    Room = apps.get_model("academics", "Room")
    TimeSlot = apps.get_model("academics", "TimeSlot")
    Room.objects.filter(school__isnull=False).update(school=None)
    TimeSlot.objects.filter(school__isnull=False).update(school=None)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0070_curriculum_allocation_and_tenant_scoped_room_timeslot"),
        ("schools", "0081_rls_backfill_unenumerated_tenant_tables"),
    ]

    operations = [
        migrations.RunPython(backfill_school, unbackfill_school),
    ]
