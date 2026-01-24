"""
Custom Admin Site Configuration
Provides enhanced admin interface with logical app grouping and custom ordering
"""
import datetime

from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone


class GileadAdminSite(AdminSite):
    """Custom admin site with enhanced organization and features."""
    
    site_header = "Gilead Tech High - Admin"
    site_title = "Gilead Admin"
    index_title = "Administration Dashboard"

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
        else:
            student_count = 0
            teacher_count = 0

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

        context = {
            **self.each_context(request),
            'title': self.index_title,
            'total_users': total_users,
            'admin_count': admin_count,
            'student_count': student_count,
            'teacher_count': teacher_count,
            'active_sessions': active_sessions,
            'sessions_24h': sessions_24h,
            'new_logins_24h': new_logins_24h,
            'failed_logins_24h': failed_logins_24h,
            'failed_logins_by_role': failed_logins_by_role,
            'security_alerts_24h': security_alerts_24h,
            'access_denials_24h': access_denials_24h,
        }
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
            path('search/', self.admin_view(self.search_view), name='search'),
            # Placeholder URLs for missing admin routes (prevent template errors)
            path('activity-logs/', lambda request: redirect('/compliance/access-logs/'), name='activity_logs'),
            path('system-health/', lambda request: redirect('/healthz/'), name='system_health'),
        ]
        return custom_urls + urls
    
    def search_view(self, request):
        """Global admin search across all registered models."""
        from django.shortcuts import render
        query = request.GET.get('q', '')
        # Redirect to default admin index with search applied
        if query:
            return redirect(f'{self.name}:index?q={query}')
        return redirect(f'{self.name}:index')
    
    def get_app_list(self, request, app_label=None):
        """
        Return a sorted list of all installed apps with models that have been registered.
        Groups models logically by function rather than by Django app.
        """
        app_dict = self._build_app_dict(request, app_label)
        
        # Define logical grouping with custom order
        app_order = {
            # Core Administration
            'accounts': {'order': 1, 'name': '👤 Accounts & Authentication', 'icon': '👤'},
            'people': {'order': 2, 'name': '👥 People Management', 'icon': '👥'},
            
            # Academic Structure
            'academics': {'order': 3, 'name': '🎓 Academic Structure', 'icon': '🎓'},
            'evals': {'order': 4, 'name': '📊 Evaluations & Grading', 'icon': '📊'},
            'reports': {'order': 5, 'name': '📄 Reports & Transcripts', 'icon': '📄'},
            
            # Financial
            'finance': {'order': 6, 'name': '💰 Finance & Billing', 'icon': '💰'},
            'payroll': {'order': 7, 'name': '💵 Payroll & Leave', 'icon': '💵'},
            
            # Operations
            'analytics': {'order': 8, 'name': '📈 Analytics & Insights', 'icon': '📈'},
            'compliance': {'order': 9, 'name': '🔒 Compliance & Audit', 'icon': '🔒'},
            
            # Configuration
            'siteconfig': {'order': 10, 'name': '⚙️ System Configuration', 'icon': '⚙️'},
            
            # Content & Communication
            'portal': {'order': 11, 'name': '📢 Portal & Communication', 'icon': '📢'},
            
            # Django Built-ins (if any remain)
            'auth': {'order': 99, 'name': '🔐 Authentication & Authorization', 'icon': '🔐'},
            'sites': {'order': 100, 'name': '🌐 Sites', 'icon': '🌐'},
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
        
        # Sort by custom order
        app_list.sort(key=lambda x: (x.get('app_order', 999), x['name'].lower()))
        
        return app_list


# Create custom admin site instance
admin_site = GileadAdminSite(name='admin')
