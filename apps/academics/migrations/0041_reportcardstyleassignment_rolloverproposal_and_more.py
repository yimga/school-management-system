import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0025_alter_securityauditlog_event_type"),
        ("academics", "0040_alter_certificationfeetemplate_currency"),
        ("people", "0039_tenant_upload_to_profiles_passport"),
        ("schools", "0033_alter_school_timezone"),
        ("siteconfig", "0145_globalsupportticket_first_response_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ReportCardStyleAssignment",
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
                        (
                            "classroom",
                            models.OneToOneField(
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="report_card_style_assignment",
                                to="academics.classroom",
                            ),
                        ),
                        (
                            "style",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.PROTECT,
                                related_name="assignments",
                                to="siteconfig.reportcardstyle",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "siteconfig_reportcardstyleassignment",
                        "ordering": ["classroom__name"],
                    },
                ),
                migrations.CreateModel(
                    name="RolloverProposal",
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
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("PENDING", "Pending review"),
                                    ("APPROVED", "Approved"),
                                    ("APPLIED", "Applied"),
                                    ("CANCELLED", "Cancelled"),
                                ],
                                db_index=True,
                                default="PENDING",
                                max_length=20,
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("approved_at", models.DateTimeField(blank=True, null=True)),
                        ("applied_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "approved_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="approved_rollover_proposals",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "created_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="created_rollover_proposals",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "school",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rollover_proposals",
                                to="schools.school",
                            ),
                        ),
                        (
                            "source_year",
                            models.ForeignKey(
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rollover_proposals_as_source",
                                to="academics.academicyear",
                            ),
                        ),
                        (
                            "target_year",
                            models.ForeignKey(
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rollover_proposals_as_target",
                                to="academics.academicyear",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Rollover proposal",
                        "verbose_name_plural": "Rollover proposals",
                        "db_table": "accounts_rolloverproposal",
                        "ordering": ["-created_at"],
                    },
                ),
                migrations.CreateModel(
                    name="RolloverProposalItem",
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
                        (
                            "current_classroom_id",
                            models.PositiveIntegerField(blank=True, null=True),
                        ),
                        (
                            "promotion_status",
                            models.CharField(blank=True, max_length=20),
                        ),
                        (
                            "annual_average",
                            models.DecimalField(
                                blank=True, decimal_places=2, max_digits=5, null=True
                            ),
                        ),
                        ("outstanding_returns", models.PositiveIntegerField(default=0)),
                        (
                            "is_graduate",
                            models.BooleanField(
                                default=False,
                                help_text="If True, student will be marked Alumni and removed from active roll.",
                            ),
                        ),
                        (
                            "approved_next_classroom",
                            models.ForeignKey(
                                blank=True,
                                db_constraint=False,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="rollover_items_approved",
                                to="academics.classroom",
                            ),
                        ),
                        (
                            "proposal",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="items",
                                to="academics.rolloverproposal",
                            ),
                        ),
                        (
                            "student",
                            models.ForeignKey(
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="rollover_proposal_items",
                                to="people.studentprofile",
                            ),
                        ),
                        (
                            "suggested_next_classroom",
                            models.ForeignKey(
                                blank=True,
                                db_constraint=False,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="rollover_items_suggested",
                                to="academics.classroom",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Rollover proposal item",
                        "verbose_name_plural": "Rollover proposal items",
                        "db_table": "accounts_rolloverproposalitem",
                        "ordering": ["proposal", "student"],
                    },
                ),
                migrations.CreateModel(
                    name="HolidayCalendar",
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
                        (
                            "name",
                            models.CharField(
                                help_text="Holiday name (e.g., 'Christmas Break', 'Eid al-Fitr')",
                                max_length=200,
                            ),
                        ),
                        (
                            "date_start",
                            models.DateField(help_text="Holiday start date"),
                        ),
                        (
                            "date_end",
                            models.DateField(help_text="Holiday end date (inclusive)"),
                        ),
                        (
                            "holiday_type",
                            models.CharField(
                                choices=[
                                    ("school_holiday", "School Holiday"),
                                    ("public_holiday", "Public Holiday"),
                                    ("exam_period", "Exam Period"),
                                    ("religious", "Religious Holiday"),
                                    ("special_event", "Special Event"),
                                ],
                                help_text="Type of holiday",
                                max_length=50,
                            ),
                        ),
                        (
                            "is_working_day",
                            models.BooleanField(
                                default=False,
                                help_text="Some regions work during certain holidays (e.g., religious holidays)",
                            ),
                        ),
                        (
                            "description",
                            models.TextField(
                                blank=True, help_text="Holiday description"
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "academic_year",
                            models.ForeignKey(
                                db_constraint=False,
                                help_text="Academic year for this holiday",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="holidays_by_region",
                                to="academics.academicyear",
                            ),
                        ),
                        (
                            "region",
                            models.ForeignKey(
                                help_text="Region this holiday applies to",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="holidays",
                                to="siteconfig.regionconfig",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "siteconfig_holidaycalendar",
                        "ordering": ["date_start"],
                        "unique_together": {("region", "academic_year", "name")},
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
