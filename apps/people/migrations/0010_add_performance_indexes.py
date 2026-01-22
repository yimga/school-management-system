# Generated migration for Phase 1.1: People app performance indexes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0009_notificationpreference'),
    ]

    operations = [
        # Index for StudentGuardian lookups in dashboard queries
        # Common: StudentGuardian.objects.filter(guardian_user=user, can_view_results=True)
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(
                fields=['guardian_user', 'can_view_results'],
                name='people_guard_user_results_idx',
            ),
        ),
        # Index for finance lookups
        migrations.AddIndex(
            model_name='studentguardian',
            index=models.Index(
                fields=['guardian_user', 'can_view_finance'],
                name='people_guard_user_finance_idx',
            ),
        ),
        # Composite index for student lookups by classroom and academic year
        migrations.AddIndex(
            model_name='studentprofile',
            index=models.Index(
                fields=['classroom', 'academic_year'],
                name='people_student_classroom_year_idx',
            ),
        ),
    ]
