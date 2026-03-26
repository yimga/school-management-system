from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schools", "0041_school_impersonation_dual_control"),
        ("portal", "0027_help_audience_faq_regional_kb_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="HostedOfficeDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Title")),
                ("file", models.FileField(upload_to="office_docs/%Y/%m/", verbose_name="File")),
                ("mime_type", models.CharField(blank=True, max_length=120, verbose_name="MIME type")),
                ("help_audience", models.CharField(choices=[("TENANT", "Tenant / school users"), ("OPERATOR", "Platform operators (manager host)"), ("BOTH", "All audiences")], default="BOTH", max_length=20, verbose_name="Help audience")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_office_documents", to=settings.AUTH_USER_MODEL)),
                ("school", models.ForeignKey(blank=True, help_text="Optional school scoping. Blank = global document.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="office_documents", to="schools.school")),
            ],
            options={
                "verbose_name": "Hosted Office Document",
                "verbose_name_plural": "Hosted Office Documents",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="hostedofficedocument",
            index=models.Index(fields=["help_audience", "updated_at"], name="portal_host_help_aud_0f446f_idx"),
        ),
        migrations.AddIndex(
            model_name="hostedofficedocument",
            index=models.Index(fields=["school"], name="portal_host_school_i_86558e_idx"),
        ),
    ]
