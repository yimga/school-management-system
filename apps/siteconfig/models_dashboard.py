"""
Phase 7 Task 6: Dashboard UX Overhaul with Widget System
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
import json

User = get_user_model()


class DashboardUserPreference(models.Model):
    """Store user UI/UX preferences and customizations for dashboard."""
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dashboard_preferences')
    
    # Dashboard customization
    dashboard_layout = models.JSONField(
        default=dict,
        help_text="Widget positions and layout configuration"
    )
    visible_widgets = models.JSONField(
        default=list,
        help_text="List of visible widget IDs on dashboard"
    )
    
    # Theme preferences
    THEME_CHOICES = [
        ('light', 'Light Mode'),
        ('dark', 'Dark Mode'),
        ('auto', 'System Default'),
    ]
    theme_preference = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default='auto'
    )
    
    # Language & localization
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('fr', 'Français'),
        ('es', 'Español'),
    ]
    language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default='en'
    )
    
    # Accessibility
    high_contrast = models.BooleanField(default=False, help_text="Enable high contrast mode")
    reduced_motion = models.BooleanField(default=False, help_text="Reduce animations")
    font_size = models.CharField(
        max_length=20,
        choices=[('normal', 'Normal'), ('large', 'Large'), ('extra-large', 'Extra Large')],
        default='normal'
    )
    
    # Notification preferences
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    push_notifications = models.BooleanField(default=True)
    
    # UI preferences
    items_per_page = models.IntegerField(default=10, choices=[(10, '10'), (25, '25'), (50, '50')])
    sidebar_collapsed = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dashboard User Preference"
        verbose_name_plural = "Dashboard User Preferences"

    def __str__(self):
        return f"{self.user.username}'s Dashboard Preferences"
    
    def get_dashboard_widgets(self):
        """Get list of visible dashboard widgets."""
        return self.visible_widgets or self._get_default_widgets()
    
    def _get_default_widgets(self):
        """Return default widgets for user role."""
        role = getattr(self.user, 'role', 'STUDENT')
        
        defaults = {
            'STUDENT': ['stats', 'recent-grades', 'upcoming-assignments', 'announcements'],
            'TEACHER': ['class-stats', 'student-performance', 'upcoming-classes', 'assignments'],
            'PARENT': ['child-progress', 'alerts', 'upcoming-events', 'fees-status'],
            'ADMIN': ['system-stats', 'user-activity', 'system-health', 'recent-changes'],
        }
        
        return defaults.get(role, ['stats', 'announcements'])
    
    def set_widget_position(self, widget_id, position):
        """Update widget position in dashboard."""
        if not self.dashboard_layout:
            self.dashboard_layout = {}
        
        self.dashboard_layout[widget_id] = {
            'position': position,
            'width': 'full',
            'collapsed': False,
        }
        self.save()
    
    def toggle_widget_visibility(self, widget_id):
        """Show or hide a widget."""
        if widget_id not in self.visible_widgets:
            self.visible_widgets.append(widget_id)
        else:
            self.visible_widgets.remove(widget_id)
        
        self.save()


class DashboardWidget(models.Model):
    """Available dashboard widgets."""
    
    TYPE_CHOICES = [
        ('stats', 'Statistics Card'),
        ('chart', 'Chart'),
        ('list', 'Recent Items'),
        ('action', 'Quick Action'),
        ('alert', 'Alert/Notification'),
        ('feed', 'Activity Feed'),
    ]
    
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    widget_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    # Access control
    required_role = models.CharField(
        max_length=20,
        choices=[
            ('STUDENT', 'Student'),
            ('TEACHER', 'Teacher'),
            ('PARENT', 'Parent'),
            ('ADMIN', 'Administrator'),
            ('ANY', 'Any User'),
        ],
        default='ANY'
    )
    
    # Display settings
    template_path = models.CharField(max_length=255, help_text="Path to widget template")
    default_width = models.IntegerField(default=1, choices=[(1, 'Full'), (2, 'Half'), (3, 'Third')])
    refresh_interval = models.IntegerField(default=300, help_text="Seconds between refreshes")
    
    # Metadata
    order = models.IntegerField(default=0, help_text="Display order")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Dashboard Widget"
        verbose_name_plural = "Dashboard Widgets"
        ordering = ['order']
    
    def __str__(self):
        return self.name


class WidgetData(models.Model):
    """Cache widget data for performance."""
    
    widget = models.ForeignKey(DashboardWidget, on_delete=models.CASCADE, related_name='cached_data')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    data = models.JSONField(help_text="Cached widget data")
    cached_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Widget Data Cache"
        verbose_name_plural = "Widget Data Caches"
        unique_together = ['widget', 'user']
    
    def __str__(self):
        return f"{self.widget.name} - {self.user.username if self.user else 'Global'}"
