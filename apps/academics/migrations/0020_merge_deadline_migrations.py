# Generated merge migration to resolve conflicting leaves:
# 0016_subjectassignment_deadline_at and 0019_subjectassignment_grading_deadline_at

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0016_subjectassignment_deadline_at'),
        ('academics', '0019_subjectassignment_grading_deadline_at'),
    ]

    operations = []
