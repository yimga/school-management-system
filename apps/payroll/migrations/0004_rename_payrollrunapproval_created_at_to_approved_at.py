# Generated manually to fix field renames and removals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0003_payscale_and_links'),
        migrations.swappable_dependency('auth.user'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payrollrunapproval',
            old_name='created_at',
            new_name='approved_at',
        ),
        migrations.RemoveField(
            model_name='payrollrunapproval',
            name='status',
        ),
        migrations.RenameField(
            model_name='payrollrunapproval',
            old_name='note',
            new_name='notes',
        ),
        migrations.RenameField(
            model_name='payrollrunapproval',
            old_name='approved_by',
            new_name='approver',
        ),
        migrations.AlterField(
            model_name='payrollrunapproval',
            name='approver',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user'),
        ),
        migrations.AlterModelOptions(
            name='payrollrunapproval',
            options={'ordering': ['-approved_at']},
        ),
    ]
