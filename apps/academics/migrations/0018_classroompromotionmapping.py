# Generated for promotion-level mapping (source classroom → target classroom for rollover)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0017_attendance'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClassroomPromotionMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promotion_mappings_from', to='academics.academicyear')),
                ('source_classroom', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promotion_mappings_from', to='academics.classroom')),
                ('target_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promotion_mappings_to', to='academics.academicyear')),
                ('target_classroom', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='promotion_mappings_to', to='academics.classroom')),
            ],
            options={
                'ordering': ['source_year', 'source_classroom'],
                'unique_together': {('source_year', 'source_classroom', 'target_year')},
            },
        ),
    ]
