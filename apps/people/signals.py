"""
Signal handlers for people models.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.communication.models import MessageThread
from apps.people.models import TeacherProfile


@receiver(post_save, sender=TeacherProfile)
def sync_teacher_department_thread(sender, instance, created, **kwargs):
    """
    Auto-add teacher to department thread when department is set or updated.
    Creates department thread if it doesn't exist.
    """
    if instance.department and instance.user:
        thread, thread_created = MessageThread.objects.get_or_create(
            scope=MessageThread.Scope.DEPARTMENT,
            department=instance.department,
            defaults={
                'title': f"{instance.department.name} Department",
                'description': f"Group chat for {instance.department.name} department members",
                'created_by': instance.user,
            }
        )
        # Add teacher to thread if not already a member
        if instance.user not in thread.members.all():
            thread.members.add(instance.user)
        
        # Remove from old department thread if department changed
        if not created and 'department' in kwargs.get('update_fields', []):
            # Get old department from previous state (if available)
            # For now, we'll just ensure they're in the current department thread
            pass
