import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0018_auditoraccessgrant_ip_allowlist_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditArchiveRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archive_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("model_label", models.CharField(db_index=True, max_length=200)),
                ("timestamp_field", models.CharField(max_length=100)),
                ("cutoff_at", models.DateTimeField(db_index=True)),
                ("record_count", models.PositiveIntegerField()),
                ("first_record_at", models.DateTimeField(blank=True, null=True)),
                ("last_record_at", models.DateTimeField(blank=True, null=True)),
                ("relative_path", models.CharField(max_length=500, unique=True)),
                ("sha256", models.CharField(max_length=64)),
                ("signature", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("VERIFIED", "Verified"), ("PURGED", "Purged")], db_index=True, default="VERIFIED", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("purged_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AuditLegalHold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("reason", models.TextField()),
                ("model_label", models.CharField(blank=True, help_text="Optional app_label.ModelName scope. Blank applies to every supported model.", max_length=200)),
                ("object_id", models.CharField(blank=True, help_text="Optional primary-key scope. Requires model_label.", max_length=200)),
                ("starts_at", models.DateTimeField(blank=True, help_text="Optional protected record range start.", null=True)),
                ("ends_at", models.DateTimeField(blank=True, help_text="Optional protected record range end.", null=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_legal_holds_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="auditarchiverecord",
            index=models.Index(fields=["model_label", "status", "-created_at"], name="compliance__model__797756_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlegalhold",
            index=models.Index(fields=["is_active", "model_label"], name="compliance__is_acti_ca4908_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlegalhold",
            index=models.Index(fields=["model_label", "object_id"], name="compliance__model__70aa65_idx"),
        ),
    ]
