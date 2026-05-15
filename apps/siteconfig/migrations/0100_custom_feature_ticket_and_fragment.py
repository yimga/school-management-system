# Security Powerhouse & Request-to-Feature: CustomFeatureTicket, FeatureFragment only

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _tenant_upload_to(subpath):
    """Return an upload_to callable that prefixes path with tenants/{school_id}/.

    Inlined from ``apps.siteconfig.models._tenant_upload_to`` for migration
    historical-state safety.
    """

    def upload_to(instance, filename):
        school_id = getattr(instance, "school_id", None)
        if school_id is None and getattr(instance, "school", None):
            school_id = getattr(instance.school, "pk", None)
        if school_id is None:
            return f"tenant_uploads/{subpath}/{filename}"
        return f"tenants/{school_id}/{subpath}/{filename}"

    return upload_to


def tenant_upload_to_waiver_requests(instance, filename):
    """Serializable upload_to for WaiverRequest.proof_file.

    Inlined from ``apps.siteconfig.models.tenant_upload_to_waiver_requests`` for
    migration historical-state safety.
    """
    return _tenant_upload_to("waiver_requests")(instance, filename)


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0010_security_powerhouse_audit_passkey"),
        ("siteconfig", "0099_reporttemplate_template_family"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomFeatureTicket",
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
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("IN_REVIEW", "In Review"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="SUBMITTED",
                        max_length=20,
                    ),
                ),
                ("reviewer_comment", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_feature_tickets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="custom_feature_tickets",
                        to="schools.school",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="FeatureFragment",
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
                ("name", models.CharField(max_length=120)),
                (
                    "target_hook",
                    models.CharField(
                        help_text="e.g. STUDENT_PROFILE_SIDEBAR, GRADEBOOK_SIDEBAR",
                        max_length=80,
                    ),
                ),
                (
                    "metadata_schema",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Config and optional HTML/snippet for the hook",
                    ),
                ),
                (
                    "schema_version",
                    models.PositiveSmallIntegerField(
                        default=1,
                        help_text="Increment when metadata_schema format changes",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_fragments",
                        to="schools.school",
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fragments",
                        to="siteconfig.customfeatureticket",
                    ),
                ),
            ],
            options={
                "ordering": ["school", "target_hook"],
                "unique_together": {("school", "target_hook")},
            },
        ),
        migrations.AlterField(
            model_name="waiverrequest",
            name="proof_file",
            field=models.FileField(
                blank=True,
                help_text="Proof of NGO / non-profit status",
                upload_to=tenant_upload_to_waiver_requests,
            ),
        ),
        migrations.AddIndex(
            model_name="customfeatureticket",
            index=models.Index(
                fields=["school", "status"], name="siteconfig__school__12895a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="featurefragment",
            index=models.Index(
                fields=["school", "is_active"], name="siteconfig__school__e3b31f_idx"
            ),
        ),
    ]
