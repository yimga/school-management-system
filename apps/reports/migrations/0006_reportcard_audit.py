from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0005_dashboardwidgetplacement_materializedreportcache_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportCardAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=40)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("report_card", models.ForeignKey(on_delete=models.CASCADE, related_name="audits", to="reports.reportcard")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="reportcardaudit",
            name="user",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="report_card_audits", to="accounts.user"),
        ),
    ]
