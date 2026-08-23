# Classroom.code / Specialty.code: global-unique -> per-(school, code) unique.
#
# Mirrors 0076 for Department.code, which made exactly this change for exactly this
# reason and left these two behind. apps.academics is in TENANT_APPS, so under
# USE_DJANGO_TENANTS=1 each tenant has its own schema and the global unique never
# bit. The sovereign edge runs USE_DJANGO_TENANTS=0 with RLS: one schema, every
# school's rows in one table (see 0029_enable_rls_postgresql / 0038_rls_policy_
# default_deny). A unique INDEX is not RLS-filtered, so school B could not use a
# code school A had taken, and the IntegrityError revealed that another tenant
# held it.
#
# Strict LOOSENING: every row that satisfied the old global unique also satisfies
# (school, code), so this applies cleanly to existing data in either topology.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0084_academicyear_calendar_invariants'),
    ]

    operations = [
        # AlterField first -- that is what drops the standalone unique index --
        # then add the composite constraint.
        migrations.AlterField(
            model_name='classroom',
            name='code',
            field=models.CharField(max_length=30),
        ),
        migrations.AddConstraint(
            model_name='classroom',
            constraint=models.UniqueConstraint(
                fields=('school', 'code'),
                name='uniq_classroom_school_code',
            ),
        ),
        migrations.AlterField(
            model_name='specialty',
            name='code',
            field=models.CharField(max_length=30),
        ),
        migrations.AddConstraint(
            model_name='specialty',
            constraint=models.UniqueConstraint(
                fields=('school', 'code'),
                name='uniq_specialty_school_code',
            ),
        ),
    ]
