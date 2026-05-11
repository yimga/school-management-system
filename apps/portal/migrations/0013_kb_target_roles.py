# Generated manually for role-based KB visibility (PARENT / TEACHER)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0012_merge_20260128_1924'),
    ]

    operations = [
        migrations.AddField(
            model_name='kbcategory',
            name='target_roles',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Leave empty to show to everyone. Or list roles e.g. ['PARENT', 'TEACHER'] to show only to those roles.",
                verbose_name='Target roles',
            ),
        ),
        migrations.AddField(
            model_name='kbarticle',
            name='target_roles',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Leave empty to show to everyone. Or list roles e.g. ['PARENT', 'TEACHER'] to show only to those roles.",
                verbose_name='Target roles',
            ),
        ),
    ]
