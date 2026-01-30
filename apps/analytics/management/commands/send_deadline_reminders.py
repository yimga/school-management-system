"""
Management command to send deadline reminder notifications to teachers.

Uses SubjectAssignment.deadline_at. Teachers are linked via TeacherAssignment.

Usage:
    python manage.py send_deadline_reminders
    python manage.py send_deadline_reminders --days 7,3,1
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from apps.academics.models import SubjectAssignment
from apps.evals.models import TeacherAssignment
from apps.siteconfig.models import SiteSettings
from apps.evals.notifications import NotificationService


class Command(BaseCommand):
    help = 'Send grading deadline reminders to teachers (SubjectAssignment.deadline_at)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=str,
            default='7,3,1,0.5',
            help='Comma-separated days before deadline to send reminders',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print reminders without sending',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        reminder_days_str = options.get('days', '7,3,1,0.5')

        try:
            reminder_days = [float(d.strip()) for d in reminder_days_str.split(',')]
        except ValueError:
            self.stdout.write(self.style.ERROR('Invalid days format'))
            return

        notification_service = NotificationService()
        site_settings = SiteSettings.get_solo()
        now = timezone.now()
        teachers_notified = set()
        reminder_count = 0

        for days_threshold in reminder_days:
            # Deadlines whose date is target_date (within the reminder window)
            target_start = now + timedelta(days=days_threshold)
            target_end = target_start + timedelta(days=1)
            qs = (
                SubjectAssignment.objects.filter(
                    deadline_at__isnull=False,
                    deadline_at__gte=target_start,
                    deadline_at__lt=target_end,
                )
                .select_related('academic_year', 'term', 'classroom', 'subject')
            )
            for sa in qs:
                # Teachers assigned to this SubjectAssignment
                for ta in TeacherAssignment.objects.filter(
                    subject_assignment=sa, is_active=True
                ).select_related('teacher', 'teacher__user'):
                    teacher = ta.teacher
                    teacher_key = (teacher.id, sa.id, days_threshold)
                    if teacher_key in teachers_notified:
                        continue
                    teachers_notified.add(teacher_key)
                    if not getattr(teacher, 'user', None) or not getattr(teacher.user, 'email', None):
                        continue
                    subject_name = sa.subject.name
                    classroom_name = sa.classroom.name
                    deadline_at = sa.deadline_at
                    deadline_date = deadline_at.strftime('%B %d, %Y')
                    subject_count = 1

                    if dry_run:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[DRY-RUN] Would send reminder to {teacher.user.email} "
                                f"({subject_name} in {classroom_name}, due {deadline_date})"
                            )
                        )
                    else:
                        try:
                            notification_service.send_deadline_reminder_email(
                                teacher=teacher,
                                deadline_at=deadline_at,
                                subject_count=subject_count,
                            )
                            self.stdout.write(
                                self.style.SUCCESS(f"✓ Sent reminder to {teacher.user.email}")
                            )
                            reminder_count += 1
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"✗ Failed to send reminder to {teacher.user.email}: {str(e)}"
                                )
                            )

        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Command completed. Sent {reminder_count} reminders.")
        )
