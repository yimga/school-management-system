"""
Management command to backfill department threads for existing teachers.
"""
from django.core.management.base import BaseCommand
from apps.communication.models import MessageThread
from apps.people.models import TeacherProfile
from apps.academics.models import Department


class Command(BaseCommand):
    help = 'Create department threads and add existing teachers to them'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))
        
        # Get all departments with teachers
        departments = Department.objects.filter(teachers__isnull=False).distinct()
        
        created_count = 0
        added_count = 0
        
        for department in departments:
            teachers = TeacherProfile.objects.filter(
                department=department,
                is_active=True
            ).select_related('user')
            
            if not teachers.exists():
                continue
            
            # Create or get department thread
            thread, created = MessageThread.objects.get_or_create(
                scope=MessageThread.Scope.DEPARTMENT,
                department=department,
                defaults={
                    'title': f"{department.name} Department",
                    'description': f"Group chat for {department.name} department members",
                    'created_by': teachers.first().user,  # Use first teacher as creator
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created thread: "{thread.title}"')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'→ Thread exists: "{thread.title}"')
                )
            
            # Add all teachers to thread
            for teacher in teachers:
                if teacher.user and teacher.user not in thread.members.all():
                    if not dry_run:
                        thread.members.add(teacher.user)
                    added_count += 1
                    self.stdout.write(
                        f'  + Added {teacher.user.get_full_name() or teacher.user.username}'
                    )
        
        self.stdout.write('\n' + '='*50)
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDRY RUN: Would create {created_count} threads, add {added_count} teachers'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Created {created_count} threads, added {added_count} teachers'
                )
            )
