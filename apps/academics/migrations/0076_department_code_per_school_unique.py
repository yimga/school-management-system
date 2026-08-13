# Department.code: global-unique -> per-(school, code) unique, so an edge box can create
# a department whose code already exists for ANOTHER tenant on the shared cloud without a
# cross-tenant collision. This is a strict LOOSENING: every row that satisfied the old
# global unique also satisfies (school, code), so it applies cleanly to existing data.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0075_academicyear_client_offline_id_and_more'),
    ]

    operations = [
        # Drop the global unique on code first (AlterField removes the standalone unique
        # index), then add the composite constraint.
        migrations.AlterField(
            model_name='department',
            name='code',
            field=models.CharField(max_length=30),
        ),
        migrations.AddConstraint(
            model_name='department',
            constraint=models.UniqueConstraint(
                fields=('school', 'code'),
                name='uniq_department_school_code',
            ),
        ),
    ]
