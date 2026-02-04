"""
Custom Admin Site Configuration
Provides enhanced admin interface with logical app grouping and custom ordering
"""
import datetime

from apps.finance.models import Notification
from apps.siteconfig.models import SiteSettings

from django.contrib import admin
from unfold.sites import UnfoldAdminSite
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.safestring import mark_safe


class GileadAdminSite(UnfoldAdminSite):
    """
    Configuration engine: full model CRUD, raw settings, system config.
    Access: superuser only.
    Extends UnfoldAdminSite for sidebar/app list.
    """

    enable_nav_sidebar = True
    site_header = "Gilead Tech High - Configuration"
    site_title = "Gilead Configuration"

    index_title = "Configuration Dashboard"

    def each_context(self, request):
        context = super().each_context(request)
        try:
            context["extra_userlinks"] = mark_safe(
                render_to_string("admin/extra_user_links.html", {"request": request})
            )
        except Exception:
            context["extra_userlinks"] = ""
        return context

    def has_permission(self, request):
        """Restrict admin to superusers only (configuration engine)."""
        return request.user.is_active and request.user.is_staff and request.user.is_superuser

    def index(self, request, extra_context=None):
        """Render the custom admin dashboard at /admin/."""
        User = get_user_model()
        total_users = User.objects.count()
        admin_count = User.objects.filter(is_staff=True).count()

        role_field = None
        for field in User._meta.get_fields():
            if getattr(field, "name", "") == "role":
                role_field = field
                break

        if role_field:
            student_count = User.objects.filter(role="STUDENT").count()
            teacher_count = User.objects.filter(role="TEACHER").count()
            parent_count = User.objects.filter(role="PARENT").count()
        else:
            student_count = 0
            teacher_count = 0
            parent_count = 0

        now = timezone.now()
        active_sessions = Session.objects.filter(expire_date__gte=now).count()
        sessions_24h = Session.objects.filter(
            expire_date__gte=now - datetime.timedelta(hours=24)
        ).count()

        new_logins_24h = 0
        failed_logins_24h = 0
        failed_logins_by_role = []
        security_alerts_24h = 0
        access_denials_24h = 0
        try:
            from apps.compliance.models_audit import AccessLog, AuditLog
            cutoff_24h = now - datetime.timedelta(hours=24)
            login_paths = ["/authentication/login/", "/admin/login/"]
            login_attempts = AccessLog.objects.filter(
                resource__in=login_paths,
                request_method="POST",
                timestamp__gte=cutoff_24h,
            )

            new_logins_24h = login_attempts.filter(status__in=["302", "303"]).count()
            failed_logins = login_attempts.exclude(status__in=["302", "303"])
            failed_logins_24h = failed_logins.count()
            failed_logins_by_role = list(
                failed_logins.values(
                    role=Coalesce("user__role", Value("Unknown"))
                ).annotate(count=Count("id")).order_by("-count")[:3]
            )

            security_alerts_24h = AuditLog.objects.filter(
                timestamp__gte=cutoff_24h
            ).filter(
                Q(action=AuditLog.Action.ACCESS_DENIED) | Q(sensitivity__in=["HIGH", "CRITICAL"])
            ).count()
            access_denials_24h = AuditLog.objects.filter(
                action=AuditLog.Action.ACCESS_DENIED,
                timestamp__gte=cutoff_24h,
            ).count()
        except Exception:
            new_logins_24h = 0
            failed_logins_24h = 0
            failed_logins_by_role = []
            security_alerts_24h = 0
            access_denials_24h = 0

        site = SiteSettings.get_solo()
        admin_theme = site.get_admin_theme()
        admin_palette = {}
        if admin_theme and getattr(admin_theme, "palette", None) and isinstance(admin_theme.palette, dict):
            admin_palette = admin_theme.palette.get("admin_dashboard") or {}
        finance_requests_qs = Notification.objects.filter(
            recipient=request.user,
            title__icontains="finance access request",
        ).order_by("-created_at")
        finance_inbox_preview = list(finance_requests_qs[:3])
        finance_inbox_unread = finance_requests_qs.filter(is_read=False).count()
        preview_data = {
            "preview_mode_enabled": getattr(site, "preview_mode_enabled", False),
            "preview_toggle_enabled": getattr(site, "preview_toggle_enabled", True),
            "preview_banner_text": getattr(site, "preview_banner_text", ""),
            "preview_note": getattr(site, "preview_note", ""),
            "preview_colors": {
                "primary": getattr(site, "primary_color", "#0d6efd"),
                "accent": getattr(site, "accent_color", "#198754"),
            },
        }
        # RBAC: only expose KPIs the user has permission to see (superuser sees all)
        user = request.user
        can_see_user_stats = user.is_superuser or user.has_perm('auth.view_user')
        can_see_sessions = user.is_superuser or user.has_perm('sessions.view_session')
        can_see_compliance = user.is_superuser or user.has_perm('compliance.view_auditlog') or user.has_perm('compliance.view_accesslog')
        can_see_finance_inbox = user.is_superuser or getattr(user, 'has_feature_permission', lambda _: False)('finance.view_invoice')

        context = {
            **self.each_context(request),
            'title': self.index_title,
            'preview_data': preview_data,
            'admin_theme': admin_theme,
            'admin_palette': admin_palette,
        }
        if can_see_user_stats:
            context.update({
                'total_users': total_users,
                'admin_count': admin_count,
                'student_count': student_count,
                'teacher_count': teacher_count,
                'parent_count': parent_count,
            })
        if can_see_sessions:
            context.update({
                'active_sessions': active_sessions,
                'sessions_24h': sessions_24h,
            })
        if can_see_compliance:
            context.update({
                'new_logins_24h': new_logins_24h,
                'failed_logins_24h': failed_logins_24h,
                'failed_logins_by_role': failed_logins_by_role,
                'security_alerts_24h': security_alerts_24h,
                'access_denials_24h': access_denials_24h,
            })
        if can_see_finance_inbox:
            context.update({
                'finance_inbox_preview': finance_inbox_preview,
                'finance_inbox_unread': finance_inbox_unread,
            })
        if extra_context:
            context.update(extra_context)

        return TemplateResponse(request, 'admin/admin_dashboard.html', context)
    
    def get_urls(self):
        """Add custom URLs including 'home' for Unfold navigation."""
        from django.contrib.admin.views.main import ChangeList
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.index), name='dashboard'),
            path('home/', lambda request: redirect('/'), name='home'),
            # search/ is provided by UnfoldAdminSite for sidebar "Jump to model" – do not override
            # Placeholder URLs for missing admin routes (prevent template errors)
            path('activity-logs/', lambda request: redirect('/compliance/access-logs/'), name='activity_logs'),
            path('system-health/', lambda request: redirect('/healthz/'), name='system_health'),
        ]
        return custom_urls + urls
    
    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all installed apps with models that have been registered.
        Groups models logically by function rather than by Django app.
        """
        app_dict = self._build_app_dict(request, app_label)
        
        # Define logical grouping with custom order
        app_order = {
            # Core Administration & People
            "accounts": {"order": 1, "name": "👤 Accounts", "icon": "👤"},
            "people": {"order": 2, "name": "👥 People Management", "icon": "👥"},
            # Keep auth tightly coupled with People Management
            "auth": {"order": 2.1, "name": "🔐 Authentication & Authorization", "icon": "🔐"},

            # Academic Structure
            "academics": {"order": 4, "name": "🎓 Academic Structure", "icon": "🎓"},
            "evals": {"order": 5, "name": "📊 Evaluations & Grading", "icon": "📊"},
            "reports": {"order": 6, "name": "📄 Reports & Transcripts", "icon": "📄"},

            # Financial
            "finance": {"order": 7, "name": "💰 Finance & Billing", "icon": "💰"},
            "payroll": {"order": 8, "name": "💵 Payroll & Leave", "icon": "💵"},

            # Operations & Portals
            "portal": {"order": 9, "name": "📢 Portal & Communication", "icon": "📢"},
            "analytics": {"order": 10, "name": "📈 Analytics & Insights", "icon": "📈"},
            "compliance": {"order": 11, "name": "🔒 Compliance & Audit", "icon": "🔒"},

            # Django Built-ins (if any remain)
            "sites": {"order": 998, "name": "🌐 Sites", "icon": "🌐"},

            # Configuration (force last)
            "siteconfig": {"order": 1000, "name": "⚙️ System Configuration", "icon": "⚙️"},
        }
        
        # Apply custom ordering and naming
        app_list = []
        for app_name, app_info in app_dict.items():
            if app_name in app_order:
                app_info['app_order'] = app_order[app_name]['order']
                app_info['app_label'] = app_name
                # Use custom name if available
                app_info['name'] = app_order[app_name]['name']
            else:
                # Unknown apps go to the end
                app_info['app_order'] = 999
                app_info['app_label'] = app_name
            
            app_list.append(app_info)

        # RBAC: hide app groups with zero models (after permission filtering)
        app_list = [app_info for app_info in app_list if (app_info.get('models') or [])]

        # Sort by custom order
        app_list.sort(key=lambda x: (x.get('app_order', 999), x['name'].lower()))

        return app_list


# Create custom admin site instance
admin_site = GileadAdminSite(name='admin')
