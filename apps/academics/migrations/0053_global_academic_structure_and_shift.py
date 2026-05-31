# Global academic OS kernel — structure tree + instruction shifts

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0052_instruction_day_and_room_fraction"),
        ("schools", "0061_alter_school_governance_help_text"),
        ("schoolops", "0019_rename_micro_friction_handover_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="AcademicStructureNode",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "node_type",
                    models.CharField(
                        choices=[
                            ("cycle", "Cycle / stage"),
                            ("cohort", "Cohort / stream"),
                            ("shift", "Instruction shift (turno)"),
                            ("classroom_leaf", "Classroom leaf"),
                        ],
                        max_length=32,
                    ),
                ),
                ("local_label", models.CharField(max_length=150)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("structural_metadata", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campus",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="academic_structure_nodes",
                        to="schoolops.campus",
                    ),
                ),
                (
                    "classroom",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="structure_node",
                        to="academics.classroom",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="academics.academicstructurenode",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="academic_structure_nodes",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Academic structure node",
                "verbose_name_plural": "Academic structure nodes",
                "ordering": ["school_id", "sort_order", "local_label"],
            },
        ),
        migrations.AddIndex(
            model_name="academicstructurenode",
            index=models.Index(
                fields=["school", "parent", "node_type"],
                name="academics_a_school__a8f2c1_idx",
            ),
        ),
        migrations.CreateModel(
            name="InstructionShift",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.SlugField(max_length=32)),
                ("label", models.CharField(max_length=80)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="instruction_shifts",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "verbose_name": "Instruction shift",
                "verbose_name_plural": "Instruction shifts",
                "ordering": ["school_id", "sort_order", "code"],
                "unique_together": {("school", "code")},
            },
        ),
        migrations.AddField(
            model_name="schedule",
            name="shift",
            field=models.ForeignKey(
                blank=True,
                help_text="When set, room conflicts apply within this shift only.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="schedules",
                to="academics.instructionshift",
            ),
        ),
    ]
