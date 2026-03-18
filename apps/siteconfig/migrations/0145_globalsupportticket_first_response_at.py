# Control plane SLO: first response timestamp for support SLA (support_sla.ticket_response_breach).
# When set, ticket is no longer in "response breach" per support_sla.ticket_response_breach.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0144_alter_sitesettings_footer_accreditation_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalsupportticket",
            name="first_response_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the first agent response was recorded; used for SLA response breach.",
            ),
        ),
    ]
