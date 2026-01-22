"""
API endpoints for compliance dashboard actions.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta

from apps.compliance.models_audit import ThreatDetectionConfig


def is_admin_or_staff(user):
    """Check if user is admin or staff."""
    return user.is_superuser or user.is_staff or user.role in ['ADMIN', 'LEADERSHIP']


@require_POST
@login_required
@user_passes_test(is_admin_or_staff)
@csrf_exempt  # For AJAX requests; alternatively handle CSRF token in template
def mute_threats(request):
    """
    Mute threat detection for a specified duration.
    
    POST parameters:
        - duration: '1h', '4h', '24h', or 'clear' to unmute
    """
    duration_str = request.POST.get('duration', '1h')
    
    try:
        config = ThreatDetectionConfig.get_active()
    except Exception:
        # Create default config if doesn't exist
        config = ThreatDetectionConfig.objects.create()
    
    now = timezone.now()
    
    if duration_str == 'clear':
        config.mute_until = None
        config.save()
        return JsonResponse({
            'success': True,
            'message': 'Threat detection unmuted',
            'muted_until': None,
        })
    
    # Parse duration
    duration_map = {
        '1h': timedelta(hours=1),
        '4h': timedelta(hours=4),
        '24h': timedelta(hours=24),
    }
    
    duration = duration_map.get(duration_str)
    if not duration:
        return JsonResponse({
            'success': False,
            'error': f'Invalid duration: {duration_str}. Use 1h, 4h, 24h, or clear.',
        }, status=400)
    
    config.mute_until = now + duration
    config.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Threat detection muted until {config.mute_until.strftime("%Y-%m-%d %H:%M")}',
        'muted_until': config.mute_until.isoformat(),
    })
