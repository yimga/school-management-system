from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("schools", "0002_enable_rls_postgresql"),
        ("reports", "0009_enable_rls_postgresql"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportDocumentHash",
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
                ("sha256_hash", models.CharField(db_index=True, max_length=64)),
                ("file_size_bytes", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "generated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="generated_report_hashes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "report_card",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_hash",
                        to="reports.reportcard",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="report_document_hashes",
                        to="schools.school",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reportdocumenthash",
            index=models.Index(
                fields=["sha256_hash", "created_at"],
                name="reports_rep_sha256_9bb6cb_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="reportdocumenthash",
            index=models.Index(
                fields=["school", "created_at"], name="reports_rep_school__6d1cfb_idx"
            ),
        ),
    ]
