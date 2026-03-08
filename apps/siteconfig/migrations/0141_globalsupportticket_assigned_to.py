# Support queue refinement: assignment (SCOPED_WORK_VERIFICATION §2)

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0140_add_control_plane_pinned_items"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="globalsupportticket",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                help_text="Super-admin or support agent assigned to this ticket.",
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="assigned_support_tickets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
