"""
View helper for recent admin activity tracking.
RBAC: staff/superuser see all logs; other users see only their own.
"""
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.utils.timesince import timesince


def get_recent_activity(user=None, limit=10):
    """
    Get recent admin actions for display in sidebar/dashboard.
    If user is staff or superuser, returns all recent actions; otherwise
    returns only that user's actions (RBAC: users see only their own logs).
    Returns list of formatted activity entries.
    """
    qs = LogEntry.objects.select_related('user', 'content_type').order_by('-action_time')
    if user and not (getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)):
        qs = qs.filter(user=user)
    recent_actions = qs[:limit]
    
    activities = []
    for log in recent_actions:
        # Determine action type
        if log.is_addition():
            action_type = 'added'
            icon = 'fa-plus-circle'
            color = 'success'
        elif log.is_change():
            action_type = 'changed'
            icon = 'fa-edit'
            color = 'info'
        elif log.is_deletion():
            action_type = 'deleted'
            icon = 'fa-trash'
            color = 'danger'
        else:
            action_type = 'unknown'
            icon = 'fa-question-circle'
            color = 'secondary'
        
        activities.append({
            'user': log.user,
            'action': action_type,
            'object': log.object_repr,
            'model': log.content_type.model if log.content_type else 'unknown',
            'app': log.content_type.app_label if log.content_type else 'unknown',
            'time': log.action_time,
            'time_ago': timesince(log.action_time),
            'icon': icon,
            'color': color,
            'change_message': log.get_change_message(),
        })
    
    return activities
