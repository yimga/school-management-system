# Help-center HITL queue — resolution note field (batch 1340 gap close)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0004_support_deflection_and_ai_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportaiinteractionreview",
            name="note",
            field=models.TextField(blank=True, help_text="Operator resolution note (no PII)."),
        ),
    ]
