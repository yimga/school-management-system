"""
Context processors for portal app.
"""
from .models import Announcement


def announcements(request):
    """
    Context processor to pass active announcements to all templates.
    """
    active_announcements = Announcement.objects.filter(
        is_active=True
    ).values('id', 'title', 'message', 'banner_type')
    
    # Filter for currently active based on date range
    filtered = []
    for ann in active_announcements:
        announcement = Announcement.objects.get(id=ann['id'])
        if announcement.is_currently_active:
            filtered.append(ann)
    
    return {
        'announcements': filtered
    }
