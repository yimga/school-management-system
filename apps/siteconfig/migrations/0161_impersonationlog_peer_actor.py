# Four-eyes: optional second operator on impersonation audit rows.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0160_impersonationlog_reason_ticket_readonly"),
    ]

    operations = [
        migrations.AddField(
            model_name="impersonationlog",
            name="peer_actor",
            field=models.ForeignKey(
                blank=True,
                help_text="Second platform operator recorded for four-eyes impersonation.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="impersonation_logs_as_peer",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
