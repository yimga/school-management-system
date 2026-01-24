"""
Phase 7 Task 6: Dashboard customization API and utilities
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.middleware.csrf import get_token
import json
from django.db.models import Q

from apps.siteconfig.models import get_dashboard_widget_choices
from apps.siteconfig.models_dashboard import DashboardUserPreference, DashboardWidget


@login_required
@require_http_methods(["GET", "POST"])
def dashboard_customize(request):
    """Handle dashboard customization requests."""
    
    if request.method == "POST":
        return _update_dashboard_layout(request)
    
    # GET: Return current dashboard config
    preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
    
    # Get available widgets for user role
    role = getattr(request.user, "role", None)
    allowed_ids = {key for key, _ in get_dashboard_widget_choices(role)}
    widgets_qs = DashboardWidget.objects.filter(is_active=True)
    if not request.user.is_staff:
        widgets_qs = widgets_qs.filter(
            Q(required_role="ANY") | Q(required_role__iexact=role)
        )
    if allowed_ids:
        widgets_qs = widgets_qs.filter(id__in=allowed_ids)

    if widgets_qs.exists():
        available_widgets = [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "type": w.widget_type,
                "width": w.default_width,
            }
            for w in widgets_qs
        ]
    else:
        available_widgets = [
            {
                "id": key,
                "name": label,
                "description": "Standard dashboard widget",
                "type": "stats",
                "width": 1,
            }
            for key, label in get_dashboard_widget_choices(role)
        ]

    return JsonResponse({
        'success': True,
        'layout': preferences.dashboard_layout,
        'visible_widgets': preferences.get_dashboard_widgets(),
        'available_widgets': available_widgets,
    })


@login_required
@require_http_methods(["POST"])
def update_widget_position(request):
    """Update widget position in dashboard layout."""
    
    try:
        data = json.loads(request.body)
        widget_id = data.get('widget_id')
        position = data.get('position')
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.set_widget_position(widget_id, position)
        
        return JsonResponse({'success': True, 'message': 'Position updated'})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def toggle_widget_visibility(request):
    """Show/hide widget on dashboard."""
    
    try:
        data = json.loads(request.body)
        widget_id = data.get('widget_id')
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.toggle_widget_visibility(widget_id)
        
        return JsonResponse({
            'success': True,
            'visible_widgets': preferences.visible_widgets
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_theme(request):
    """Update user theme preference."""
    
    try:
        data = json.loads(request.body)
        theme = data.get('theme', 'auto')
        
        if theme not in ['light', 'dark', 'auto']:
            return JsonResponse({'success': False, 'error': 'Invalid theme'}, status=400)
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.theme_preference = theme
        preferences.save()
        
        return JsonResponse({'success': True, 'theme': theme})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def update_accessibility_preferences(request):
    """Update accessibility settings."""
    
    try:
        data = json.loads(request.body)
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.high_contrast = data.get('high_contrast', preferences.high_contrast)
        preferences.reduced_motion = data.get('reduced_motion', preferences.reduced_motion)
        preferences.font_size = data.get('font_size', preferences.font_size)
        preferences.save()
        
        return JsonResponse({
            'success': True,
            'settings': {
                'high_contrast': preferences.high_contrast,
                'reduced_motion': preferences.reduced_motion,
                'font_size': preferences.font_size,
            }
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def _update_dashboard_layout(request):
    """Update complete dashboard layout."""
    
    try:
        data = json.loads(request.body)
        layout = data.get('layout', {})
        visible_widgets = data.get('visible_widgets', [])
        
        preferences, _ = DashboardUserPreference.objects.get_or_create(user=request.user)
        preferences.dashboard_layout = layout
        preferences.visible_widgets = visible_widgets
        preferences.save()
        
        return JsonResponse({'success': True, 'message': 'Layout saved'})
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# JavaScript utilities for drag-and-drop
DASHBOARD_JS = """
// Phase 7 Task 6: Dashboard customization JavaScript

class DashboardManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.widgets = [];
        this.initDragAndDrop();
    }
    
    initDragAndDrop() {
        // Make widgets draggable
        this.container.querySelectorAll('.widget').forEach(widget => {
            widget.draggable = true;
            widget.addEventListener('dragstart', (e) => this.dragStart(e));
            widget.addEventListener('dragend', (e) => this.dragEnd(e));
            widget.addEventListener('dragover', (e) => this.dragOver(e));
            widget.addEventListener('drop', (e) => this.drop(e));
        });
    }
    
    dragStart(e) {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', e.target.innerHTML);
        e.target.classList.add('dragging');
    }
    
    dragEnd(e) {
        e.target.classList.remove('dragging');
        this.saveLayout();
    }
    
    dragOver(e) {
        if (e.preventDefault) {
            e.preventDefault();
        }
        e.dataTransfer.dropEffect = 'move';
        return false;
    }
    
    drop(e) {
        if (e.stopPropagation) {
            e.stopPropagation();
        }
        
        const from = document.querySelector('.dragging');
        const to = e.target.closest('.widget');
        
        if (from && to) {
            [from.style.order, to.style.order] = [to.style.order, from.style.order];
            this.saveLayout();
        }
        
        return false;
    }
    
    toggleWidget(widgetId) {
        fetch('/dashboard/toggle-widget/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ widget_id: widgetId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                location.reload();
            }
        });
    }
    
    saveLayout() {
        const layout = {};
        this.container.querySelectorAll('.widget').forEach((w, i) => {
            layout[w.id] = { position: i };
        });
        
        fetch('/dashboard/update-layout/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ layout: layout })
        });
    }
}

function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    new DashboardManager('dashboard-container');
});
"""
