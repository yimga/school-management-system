"""
Dashboard widget and layout models.

Notes:
- DashboardUserPreference stores general UI preferences (theme, accessibility, default widgets).
- DashboardLayout stores per-page drag/drop layout and per-widget presentation config.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q

User = get_user_model()


PAGE_CHOICES = [
    ("parent", "Parent Portal"),
    ("teacher", "Teacher Portal"),
    ("backend", "Backend Dashboard"),
    ("backend-dashboard", "Backend Dashboard (alias)"),
    ("backend_console", "Backend Console"),
    ("admin", "Admin Portal"),
    ("admin-security", "Admin Security"),
    ("student", "Student Portal"),
    ("finance", "Finance Dashboard"),
    ("analytics", "Analytics Dashboard"),
    ("portal-kb", "Portal Knowledge Base"),
    ("entity-console", "Entity Console"),
]


class DashboardUserPreference(models.Model):
    """Store user UI/UX preferences and customizations for dashboards."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="dashboard_preferences")

    # Dashboard customization
    dashboard_layout = models.JSONField(default=dict, help_text="Legacy widget positions (Phase 7).")
    visible_widgets = models.JSONField(default=list, help_text="List of visible widget IDs on dashboard.")

    # Theme preferences (shared across portal pages)
    THEME_CHOICES = [
        ("system", "System"),
        ("light", "Light"),
        ("dark", "Dark"),
        ("classic", "Classic"),
        ("high_contrast", "High Contrast"),
    ]
    theme_preference = models.CharField(max_length=20, choices=THEME_CHOICES, default="system")

    # Language & localization
    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("fr", "Francais"),
        ("es", "Espanol"),
    ]
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default="en")

    # Accessibility
    high_contrast = models.BooleanField(default=False, help_text="Enable high contrast mode")
    reduced_motion = models.BooleanField(default=False, help_text="Reduce animations")
    font_size = models.CharField(
        max_length=20,
        choices=[("normal", "Normal"), ("large", "Large"), ("extra-large", "Extra Large")],
        default="normal",
    )

    # Notification preferences (legacy; kept for compatibility)
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    push_notifications = models.BooleanField(default=True)

    # UI preferences
    items_per_page = models.IntegerField(default=10, choices=[(10, "10"), (25, "25"), (50, "50")])
    sidebar_collapsed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dashboard User Preference"
        verbose_name_plural = "Dashboard User Preferences"

    def __str__(self) -> str:
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
        """Update widget position in legacy dashboard_layout."""
        if not self.dashboard_layout:
            self.dashboard_layout = {}
        self.dashboard_layout[str(widget_id)] = {
            "position": position,
            "width": "full",
            "collapsed": False,
        }
        self.save(update_fields=["dashboard_layout", "updated_at"])

    def toggle_widget_visibility(self, widget_id):
        """Show or hide a widget."""
        widget_id = str(widget_id)
        if widget_id not in self.visible_widgets:
            self.visible_widgets.append(widget_id)
        else:
            self.visible_widgets.remove(widget_id)
        self.save(update_fields=["visible_widgets", "updated_at"])


class DashboardWidget(models.Model):
    """Available dashboard widgets (admin-configurable catalog)."""

    TYPE_CHOICES = [
        ("stats", "Statistics Card"),
        ("chart", "Chart"),
        ("list", "Recent Items"),
        ("action", "Quick Action"),
        ("alert", "Alert/Notification"),
        ("feed", "Activity Feed"),
    ]

    # UI size controls (used by drag/drop layout tool)
    SIZE_CHOICES = [
        ("sm", "Small"),
        ("md", "Medium"),
        ("lg", "Large"),
    ]
    VARIANT_CHOICES = [
        ("default", "Default"),
        ("compact", "Compact"),
        ("flat", "Flat"),
    ]

    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    widget_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    page = models.CharField(
        max_length=20,
        choices=PAGE_CHOICES,
        default="backend",
        help_text="Where this widget can be placed (parent/teacher/backend/etc.).",
    )

    # Access control
    required_role = models.CharField(
        max_length=20,
        choices=[
            ("STUDENT", "Student"),
            ("TEACHER", "Teacher"),
            ("PARENT", "Parent"),
            ("ADMIN", "Administrator"),
            ("ANY", "Any User"),
        ],
        default="ANY",
    )
    allowed_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional: additional roles permitted to view this widget.",
    )

    # Display settings
    template_path = models.CharField(max_length=255, help_text="Path to widget template")
    default_width = models.IntegerField(default=1, choices=[(1, "Full"), (2, "Half"), (3, "Third")])
    refresh_interval = models.IntegerField(default=300, help_text="Seconds between refreshes")
    default_column = models.PositiveSmallIntegerField(default=1, help_text="Column hint for drag/drop layout")
    default_order = models.PositiveSmallIntegerField(default=1, help_text="Order hint within a column")

    # Per-widget sizing/variant controls (admin-configurable)
    allowed_sizes = models.JSONField(
        default=list,
        blank=True,
        help_text="Allowed size options for this widget (sm/md/lg). Empty means all.",
    )
    default_size = models.CharField(
        max_length=8,
        choices=SIZE_CHOICES,
        default="md",
        help_text="Default size to apply when user has not customized.",
    )
    allowed_variants = models.JSONField(
        default=list,
        blank=True,
        help_text="Allowed style variants for this widget. Empty means all.",
    )
    default_variant = models.CharField(
        max_length=16,
        choices=VARIANT_CHOICES,
        default="default",
        help_text="Default style variant to apply when user has not customized.",
    )

    # Metadata
    order = models.IntegerField(default=0, help_text="Display order")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Dashboard Widget"
        verbose_name_plural = "Dashboard Widgets"
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name

    def resolved_allowed_sizes(self) -> list[str]:
        if self.allowed_sizes:
            return [s for s in self.allowed_sizes if s in {"sm", "md", "lg"}]
        return ["sm", "md", "lg"]

    def resolved_allowed_variants(self) -> list[str]:
        if self.allowed_variants:
            return [v for v in self.allowed_variants if v in {"default", "compact", "flat"}]
        return ["default", "compact", "flat"]


def get_dashboard_widget_metadata(widget_ids: list[str] | None = None) -> dict[str, dict]:
    """Return metadata for dashboard widgets (allowed sizes/variants + defaults)."""
    qs = DashboardWidget.objects.filter(is_active=True)
    if widget_ids:
        qs = qs.filter(id__in=widget_ids)
    metadata: dict[str, dict] = {}
    for widget in qs:
        metadata[widget.id] = {
            "allowed_sizes": widget.resolved_allowed_sizes(),
            "allowed_variants": widget.resolved_allowed_variants(),
            "default_size": widget.default_size or "md",
            "default_variant": widget.default_variant or "default",
        }
    return metadata


class WidgetData(models.Model):
    """Cache widget data for performance."""

    widget = models.ForeignKey(DashboardWidget, on_delete=models.CASCADE, related_name="cached_data")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    data = models.JSONField(help_text="Cached widget data")
    cached_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Widget Data Cache"
        verbose_name_plural = "Widget Data Caches"
        unique_together = ["widget", "user"]

    def __str__(self) -> str:
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
        help_text="Optional role-scoped default when user layout is not present.",
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

    def __str__(self) -> str:
        owner = self.user.username if self.user else (self.role or "global")
        return f"{self.page} layout for {owner}"


class DashboardLayoutAudit(models.Model):
    """Tracks per-user changes to dashboard layouts for auditing."""

    ACTION_CHOICES = [
        ("widget_meta", "Widget meta change"),
        ("settings", "Layout settings change"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="dashboard_layout_audits",
    )
    widget_id = models.CharField(max_length=50, blank=True, null=True)
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    summary = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dashboard Layout Audit"
        verbose_name_plural = "Dashboard Layout Audits"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.username} {self.action} {self.widget_id or 'layout'}"
