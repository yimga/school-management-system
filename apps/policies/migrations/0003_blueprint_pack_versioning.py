# Blueprint pack versioning (11.2): track applied pack and pack version for "Update bundle"

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policies", "0002_blueprint_pack"),
    ]

    operations = [
        migrations.AddField(
            model_name="policybundle",
            name="applied_pack_version",
            field=models.CharField(
                blank=True,
                help_text="When created from a BlueprintPack, store pack.version for update detection.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="tenantblueprint",
            name="applied_pack",
            field=models.ForeignKey(
                blank=True,
                help_text="Blueprint pack last applied; used to offer update when pack version increases.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tenant_blueprints",
                to="policies.blueprintpack",
            ),
        ),
    ]
