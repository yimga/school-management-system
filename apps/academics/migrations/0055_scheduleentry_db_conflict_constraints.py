# ScheduleEntry term/shift denorm + partial unique conflict constraints (Phase 4E)

import django.db.models.deletion
from django.db import migrations, models


def _backfill_schedule_entry_scope(apps, schema_editor):
    ScheduleEntry = apps.get_model("academics", "ScheduleEntry")
    for entry in ScheduleEntry.objects.select_related("schedule").iterator(chunk_size=500):
        schedule = entry.schedule
        entry.term_id = schedule.term_id
        entry.instruction_shift_id = schedule.shift_id
        entry.save(update_fields=["term_id", "instruction_shift_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0054_rename_academic_structure_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleentry",
            name="term",
            field=models.ForeignKey(
                editable=False,
                help_text="Denormalized from schedule.term for DB conflict constraints.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="schedule_entries",
                to="academics.term",
            ),
        ),
        migrations.AddField(
            model_name="scheduleentry",
            name="instruction_shift",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                help_text="Denormalized from schedule.shift; NULL = term-wide booking scope.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schedule_entries",
                to="academics.instructionshift",
            ),
        ),
        migrations.RunPython(_backfill_schedule_entry_scope, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="scheduleentry",
            name="term",
            field=models.ForeignKey(
                editable=False,
                help_text="Denormalized from schedule.term for DB conflict constraints.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="schedule_entries",
                to="academics.term",
            ),
        ),
        migrations.AddIndex(
            model_name="scheduleentry",
            index=models.Index(
                fields=["term", "teacher", "time_slot"],
                name="academics_s_term_id_6f2a91_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="scheduleentry",
            index=models.Index(
                fields=["term", "room", "time_slot"],
                name="academics_s_term_id_8c4e12_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="scheduleentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("instruction_shift__isnull", False), ("is_cancelled", False)),
                fields=("term", "teacher", "time_slot", "instruction_shift"),
                name="uniq_schedentry_teacher_slot_shift",
            ),
        ),
        migrations.AddConstraint(
            model_name="scheduleentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("instruction_shift__isnull", True), ("is_cancelled", False)),
                fields=("term", "teacher", "time_slot"),
                name="uniq_schedentry_teacher_slot_termwide",
            ),
        ),
        migrations.AddConstraint(
            model_name="scheduleentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("instruction_shift__isnull", False), ("is_cancelled", False)),
                fields=("term", "room", "time_slot", "instruction_shift"),
                name="uniq_schedentry_room_slot_shift",
            ),
        ),
        migrations.AddConstraint(
            model_name="scheduleentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(("instruction_shift__isnull", True), ("is_cancelled", False)),
                fields=("term", "room", "time_slot"),
                name="uniq_schedentry_room_slot_termwide",
            ),
        ),
    ]
