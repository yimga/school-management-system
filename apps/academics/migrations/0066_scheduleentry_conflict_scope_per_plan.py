# Rescope the ScheduleEntry double-booking uniques from the TERM to the PLAN.
#
# Phase 4E (0055) keyed them on ``term``, which made the SECOND Schedule for any
# term impossible -- every entry collided on (term, teacher|room, time_slot) --
# so a school could generate its timetable exactly once, ever. See
# ScheduleEntry.Meta for the full reasoning.
#
# SAFE ON EXISTING DATA BY CONSTRUCTION: the term-scoped uniques were strictly
# STRONGER than these. Every entry in a plan shares that plan's term, so any two
# rows colliding on (schedule, teacher, time_slot) would already have collided on
# (term, teacher, time_slot) and could never have been stored. This migration only
# ever removes constraints and adds weaker ones -- it cannot fail on a live table.

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0065_ensure_incident_and_all_school_fk_columns'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='scheduleentry',
            name='uniq_schedentry_teacher_slot_termwide',
        ),
        migrations.RemoveConstraint(
            model_name='scheduleentry',
            name='uniq_schedentry_room_slot_termwide',
        ),
        migrations.RemoveConstraint(
            model_name='scheduleentry',
            name='uniq_schedentry_teacher_slot_shift',
        ),
        migrations.RemoveConstraint(
            model_name='scheduleentry',
            name='uniq_schedentry_room_slot_shift',
        ),
        migrations.AddConstraint(
            model_name='scheduleentry',
            constraint=models.UniqueConstraint(condition=models.Q(('is_cancelled', False)), fields=('schedule', 'teacher', 'time_slot'), name='uniq_schedentry_teacher_slot_in_plan'),
        ),
        migrations.AddConstraint(
            model_name='scheduleentry',
            constraint=models.UniqueConstraint(condition=models.Q(('is_cancelled', False)), fields=('schedule', 'room', 'time_slot'), name='uniq_schedentry_room_slot_in_plan'),
        ),
    ]
