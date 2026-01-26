"""
Phase 7 Task 6: Dashboard UX Overhaul with Widget System
"""
from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
import json

User = get_user_model()


PAGE_CHOICES = [
    ("parent", "Parent Portal"),
    ("teacher", "Teacher Portal"),
    ("backend", "Backend Dashboard"),
    ("admin", "Admin Portal"),
    ("student", "Student Portal"),
]


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
        """Return default widgets aligned to the portal widget keys."""
        from apps.siteconfig.models import default_dashboard_widgets

        role = getattr(self.user, "role", None)
        return default_dashboard_widgets(role)
    
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
        ("stats", "Statistics Card"),
        ("chart", "Chart"),
        ("list", "Recent Items"),
        ("action", "Quick Action"),
        ("alert", "Alert/Notification"),
        ("feed", "Activity Feed"),
    ]

    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    widget_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    page = models.CharField(
        max_length=20,
        choices=PAGE_CHOICES,
        default="backend",
        help_text="Where this widget can be placed (parent/teacher/backend/etc.)",
    )

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
    allowed_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional: additional roles permitted to view this widget",
    )

    # Display settings
    template_path = models.CharField(max_length=255, help_text="Path to widget template")
    default_width = models.IntegerField(default=1, choices=[(1, 'Full'), (2, 'Half'), (3, 'Third')])
    refresh_interval = models.IntegerField(default=300, help_text="Seconds between refreshes")
    default_column = models.PositiveSmallIntegerField(default=1, help_text="Column hint for drag/drop layout")
    default_order = models.PositiveSmallIntegerField(default=1, help_text="Order hint within a column")

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


class DashboardLayout(models.Model):
    """
    Persisted layouts for drag-and-drop dashboards.
    Can be scoped to a specific user or a default for a role/page combo.
    """

    page = models.CharField(max_length=20, choices=PAGE_CHOICES)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dashboard_layouts",
    )
    role = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional role-scoped default when user layout is not present",
    )
    layout = models.JSONField(default=dict, blank=True, help_text="Serialized positions/sizes of widgets")
    is_default = models.BooleanField(default=False, help_text="Use as default layout for the role/page")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "page"], name="uniq_user_page_layout"),
            models.UniqueConstraint(
                fields=["role", "page"],
                condition=Q(is_default=True),
                name="uniq_default_role_page_layout",
            ),
        ]
        ordering = ["page", "user_id", "role"]

    def __str__(self):
        owner = self.user.username if self.user else (self.role or "global")
        return f"{self.page} layout for {owner}"
