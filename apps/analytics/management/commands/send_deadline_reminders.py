"""
Management command to send deadline reminder notifications to teachers.

Usage:
    python manage.py send_deadline_reminders
    python manage.py send_deadline_reminders --days 7,3,1
"""
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.apps import apps as django_apps

from apps.siteconfig.models import SiteSettings
from apps.evals.notifications import NotificationService


class Command(BaseCommand):
    help = 'Send grading deadline reminders to teachers'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=str,
            default='7,3,1,0.5',
            help='Comma-separated days before deadline to send reminders'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print reminders without sending'
        )
    
    def handle(self, *args, **options):
        """
        Send deadline reminders.
        
        NOTE: GradingDeadline model was removed. This command is disabled.
        TODO: Re-implement using SubjectAssignment.deadline_at when field is added.
        """
        self.stdout.write(
            self.style.WARNING(
                "⚠ Deadline reminder command is currently disabled.\n"
                "The GradingDeadline model was removed. This feature will be restored\n"
                "once deadline_at field is added to SubjectAssignment model or a new\n"
                "deadline management system is implemented.\n"
            )
        )
        return
        
        # Code below is kept for reference when re-implementing
        dry_run = options.get('dry_run', False)
        reminder_days_str = options.get('days', '7,3,1,0.5')
        
        try:
            reminder_days = [float(d.strip()) for d in reminder_days_str.split(',')]
        except ValueError:
            self.stdout.write(self.style.ERROR('Invalid days format'))
            return
        
        site_settings = SiteSettings.get_solo()
        notification_service = NotificationService()
        
        today = timezone.now().date()
        teachers_notified = set()
        reminder_count = 0
        
        # TODO: Re-implement using SubjectAssignment.deadline_at
        # For each reminder day threshold
        for days_threshold in reminder_days:
            # Calculate target deadline date
            target_date = today + timedelta(days=days_threshold)
            
            # Find deadlines matching this date
            # deadlines = SubjectAssignment.objects.filter(
            #     deadline_at__date=target_date
            # ).select_related(...)
            
            for deadline in []:  # Placeholder
                teacher = deadline.subject_assignment.teacher
                teacher_key = (teacher.id, days_threshold)
                
                # Skip if already notified for this threshold
                if teacher_key in teachers_notified:
                    continue
                
                teachers_notified.add(teacher_key)
                
                subject_name = deadline.subject_assignment.subject.name
                classroom_name = deadline.subject_assignment.classroom.name
                deadline_date = deadline.deadline_date.strftime('%B %d, %Y')
                
                # Build email content
                context = {
                    'teacher_name': f"{teacher.user.first_name} {teacher.user.last_name}",
                    'subject_name': subject_name,
                    'classroom_name': classroom_name,
                    'days_left': int(days_threshold),
                    'deadline_date': deadline_date,
                    'academic_year': deadline.academic_year.name,
                    'term': deadline.term.name,
                }
                
                if dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[DRY-RUN] Would send reminder to {teacher.user.email} "
                            f"({subject_name} in {classroom_name}, due {deadline_date})"
                        )
                    )
                else:
                    # Send email
                    try:
                        notification_service.send_deadline_reminder_email(
                            teacher=teacher,
                            context=context
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Sent reminder to {teacher.user.email}"
                            )
                        )
                        reminder_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"✗ Failed to send reminder to {teacher.user.email}: {str(e)}"
                            )
                        )
                    
                    # Send SMS if configured
                    if site_settings.sms_provider and site_settings.sms_provider != 'console':
                        try:
                            sms_body = (
                                f"Hi {teacher.user.first_name}, your grading deadline for "
                                f"{subject_name} ({classroom_name}) is {deadline_date}. "
                                f"Please submit your marks."
                            )
                            notification_service.send_sms(
                                phone_number=teacher.user.phone_number,
                                body=sms_body
                            )
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"✓ Sent SMS to {teacher.user.phone_number}"
                                )
                            )
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"⚠ SMS failed for {teacher.user.phone_number}: {str(e)}"
                                )
                            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Command completed. Sent {reminder_count} reminders."
            )
        )
