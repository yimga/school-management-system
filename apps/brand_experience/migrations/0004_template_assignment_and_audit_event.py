"""Wave B-1/B-2: TemplateAssignment + TemplateAuditEvent first-class models.

Pure CreateModel migration — adds two new tables under brand_experience.
TemplateAssignment OneToOnes to packages.InstalledPackage; TemplateAuditEvent
is append-only (delete-blocked at the model layer; this migration only
allocates the schema).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("brand_experience", "0003_svg_safe_validator"),
        ("packages", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TemplateAssignment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("template_key", models.CharField(db_index=True, max_length=80)),
                ("local_profile_key", models.CharField(blank=True, db_index=True, max_length=80)),
                ("surface", models.CharField(blank=True, max_length=32)),
                ("role_target", models.JSONField(blank=True, default=list)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("rollback_snapshot", models.JSONField(blank=True, default=dict)),
                ("customizations", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
                (
                    "applied_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "installed_package",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="template_assignment",
                        to="packages.installedpackage",
                    ),
                ),
            ],
            options={
                "verbose_name": "Template Assignment",
                "verbose_name_plural": "Template Assignments",
            },
        ),
        migrations.AddIndex(
            model_name="TemplateAssignment",
            index=models.Index(fields=["template_key", "applied_at"], name="be_tplassign_tplkey_idx"),
        ),
        migrations.AddIndex(
            model_name="TemplateAssignment",
            index=models.Index(fields=["local_profile_key", "applied_at"], name="be_tplassign_lockey_idx"),
        ),
        migrations.CreateModel(
            name="TemplateAuditEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenant_id_hash", models.CharField(db_index=True, max_length=12)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("template.preview", "Preview"),
                            ("template.apply_requested", "Apply requested"),
                            ("template.applied", "Applied"),
                            ("template.rolled_back", "Rolled back"),
                            ("template.customized", "Customized"),
                            ("template.recommendation", "Recommendation"),
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                ("template_key", models.CharField(db_index=True, max_length=80)),
                ("local_profile_key", models.CharField(blank=True, max_length=80)),
                ("actor_id", models.IntegerField(blank=True, null=True)),
                ("payload_summary", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Template Audit Event",
                "verbose_name_plural": "Template Audit Events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="TemplateAuditEvent",
            index=models.Index(fields=["tenant_id_hash", "created_at"], name="be_tplaudit_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="TemplateAuditEvent",
            index=models.Index(fields=["event_type", "created_at"], name="be_tplaudit_evtype_idx"),
        ),
        migrations.AddIndex(
            model_name="TemplateAuditEvent",
            index=models.Index(fields=["template_key", "created_at"], name="be_tplaudit_tplkey_idx"),
        ),
    ]
