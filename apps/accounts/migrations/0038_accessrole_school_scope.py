# School-scoped AccessRole catalog (global templates keep school=NULL)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0037_tenant_staff_invite"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accessrole",
            name="code",
            field=models.CharField(max_length=120),
        ),
        migrations.AddField(
            model_name="accessrole",
            name="school",
            field=models.ForeignKey(
                blank=True,
                help_text="Null = global template role; set = school-specific catalog entry.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="access_roles",
                to="schools.school",
            ),
        ),
        migrations.AlterModelOptions(
            name="accessrole",
            options={"ordering": ["school_id", "code"]},
        ),
        migrations.AddConstraint(
            model_name="accessrole",
            constraint=models.UniqueConstraint(
                condition=models.Q(("school__isnull", True)),
                fields=("code",),
                name="uniq_accessrole_global_code",
            ),
        ),
        migrations.AddConstraint(
            model_name="accessrole",
            constraint=models.UniqueConstraint(
                condition=models.Q(("school__isnull", False)),
                fields=("school", "code"),
                name="uniq_accessrole_school_code",
            ),
        ),
    ]
