"""
Custom Admin Site Configuration
Provides enhanced admin interface with logical app grouping and custom ordering
"""
import datetime
import sys

import django
from apps.finance.models import Notification
from apps.siteconfig.models import SiteSettings

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from unfold.sites import UnfoldAdminSite
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import connection
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

    index_title = "Administration Dashboard"

    def each_context(self, request):
        context = super().each_context(request)
        try:
            context["extra_userlinks"] = mark_safe(
                render_to_string("admin/extra_user_links.html", {"request": request})
            )
        except Exception:
            context["extra_userlinks"] = ""
        # MFA encouragement: show dismissible banner for staff without MFA
        try:
            from django.urls import reverse
            from django_otp import user_has_device
            show = (
                request.user.is_authenticated
                and request.user.is_staff
                and not user_has_device(request.user)
                and not request.session.get("mfa_banner_dismissed")
            )
            context["show_mfa_banner"] = show
            context["mfa_setup_url"] = reverse("accounts:mfa_setup") if show else ""
        except Exception:
            context["show_mfa_banner"] = False
            context["mfa_setup_url"] = ""
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
        # MFA compliance KPI: staff with at least one confirmed TOTP device
        mfa_enabled_count = 0
        mfa_staff_total = admin_count
        mfa_compliance_percent = 0
        mfa_by_role = []
        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
            staff_ids = list(User.objects.filter(is_staff=True).values_list("id", flat=True))
            if staff_ids:
                mfa_enabled_count = TOTPDevice.objects.filter(
                    user_id__in=staff_ids, confirmed=True
                ).values_list("user_id", flat=True).distinct().count()
                mfa_compliance_percent = round(100 * mfa_enabled_count / len(staff_ids)) if staff_ids else 0
            if role_field:
                staff_qs = User.objects.filter(is_staff=True).exclude(role__isnull=True).exclude(role="")
                for role in staff_qs.values_list("role", flat=True).distinct():
                    total = staff_qs.filter(role=role).count()
                    enabled = TOTPDevice.objects.filter(user__in=staff_qs.filter(role=role), confirmed=True).values_list("user_id", flat=True).distinct().count()
                    mfa_by_role.append({
                        "role": role,
                        "enabled": enabled,
                        "total": total,
                        "percent": round(100 * enabled / total) if total else 0,
                    })
        except Exception:
            pass

        # Site settings change audit (recent log entries)
        settings_change_log = []
        try:
            ct = ContentType.objects.get_for_model(SiteSettings)
            settings_change_log = list(
                LogEntry.objects.filter(content_type=ct).order_by("-action_time")[:5]
            )
        except Exception:
            settings_change_log = []

        # Action queue: pending AccessRequests (for users who can manage requests)
        pending_approvals_count = 0
        pending_approvals_list = []
        try:
            from apps.requests.models import AccessRequest
            from apps.requests.views import _can_manage_requests
            if _can_manage_requests(request.user):
                pending_approvals_count = AccessRequest.objects.filter(
                    status=AccessRequest.Status.PENDING
                ).count()
                pending_approvals_list = list(
                    AccessRequest.objects.filter(status=AccessRequest.Status.PENDING)
                    .select_related("requester")
                    .order_by("-requested_at")[:5]
                )
        except Exception:
            pass

        # RBAC: only expose KPIs the user has permission to see (superuser sees all)
        user = request.user
        can_see_user_stats = user.is_superuser or user.has_perm('auth.view_user')
        can_see_sessions = user.is_superuser or user.has_perm('sessions.view_session')
        can_see_compliance = user.is_superuser or user.has_perm('compliance.view_auditlog') or user.has_perm('compliance.view_accesslog')
        can_see_finance_inbox = user.is_superuser or getattr(user, 'has_feature_permission', lambda _: False)('finance.view_invoice')

        # System info (dynamic, not hardcoded)
        db_engine = connection.vendor  # 'sqlite', 'postgresql', etc.
        db_engine_display = {
            'sqlite': 'SQLite3',
            'postgresql': 'PostgreSQL',
            'mysql': 'MySQL',
            'oracle': 'Oracle',
        }.get(db_engine, db_engine.title())
        django_version = django.get_version()
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        is_debug = settings.DEBUG

        context = {
            **self.each_context(request),
            'title': self.index_title,
            'preview_data': preview_data,
            'admin_theme': admin_theme,
            'admin_palette': admin_palette,
            'django_version': django_version,
            'python_version': python_version,
            'db_engine_display': db_engine_display,
            'is_debug': is_debug,
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
        context.update({
            'mfa_enabled_count': mfa_enabled_count,
            'mfa_staff_total': mfa_staff_total,
            'mfa_compliance_percent': mfa_compliance_percent,
            'mfa_by_role': mfa_by_role,
            'pending_approvals_count': pending_approvals_count,
            'pending_approvals_list': pending_approvals_list,
            'settings_change_log': settings_change_log,
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
        
        # Define logical grouping with custom order.
        # section: visual separator group in sidebar (people, academic, financial, operations, system)
        app_order = {
            # Core Administration & People
            "accounts": {"order": 1, "name": "👤 Accounts", "icon": "👤", "section": "people"},
            "people": {"order": 2, "name": "👥 People Management", "icon": "👥", "section": "people"},
            "auth": {"order": 2.1, "name": "🔐 Auth & Authorization", "icon": "🔐", "section": "people"},

            # Academic Structure
            "academics": {"order": 4, "name": "🎓 Academic Structure", "icon": "🎓", "section": "academic"},
            "evals": {"order": 5, "name": "📊 Evaluations & Grading", "icon": "📊", "section": "academic"},
            "reports": {"order": 6, "name": "📄 Reports & Transcripts", "icon": "📄", "section": "academic"},

            # Financial
            "finance": {"order": 7, "name": "💰 Finance & Billing", "icon": "💰", "section": "financial"},
            "payroll": {"order": 8, "name": "💵 Payroll & Leave", "icon": "💵", "section": "financial"},

            # Operations & Portals
            "portal": {"order": 9, "name": "📢 Portal & Communication", "icon": "📢", "section": "operations"},
            "analytics": {"order": 10, "name": "📈 Analytics & Insights", "icon": "📈", "section": "operations"},
            "compliance": {"order": 11, "name": "🔒 Compliance & Audit", "icon": "🔒", "section": "operations"},
            "automation": {"order": 12, "name": "🤖 Automation", "icon": "🤖", "section": "operations"},
            "requests": {"order": 13, "name": "📋 Requests & Approvals", "icon": "📋", "section": "operations"},
            "communication": {"order": 14, "name": "💬 Communication", "icon": "💬", "section": "operations"},
            "emis": {"order": 15, "name": "📤 EMIS & Export", "icon": "📤", "section": "operations"},

            # Django Built-ins (if any remain)
            "sites": {"order": 998, "name": "🌐 Sites", "icon": "🌐", "section": "system"},

            # Configuration (force last)
            "siteconfig": {"order": 1000, "name": "⚙️ System Configuration", "icon": "⚙️", "section": "system"},
        }
        
        # Apply custom ordering, naming, and section grouping
        app_list = []
        for app_name, app_info in app_dict.items():
            if app_name in app_order:
                cfg = app_order[app_name]
                app_info['app_order'] = cfg['order']
                app_info['app_label'] = app_name
                app_info['name'] = cfg['name']
                app_info['section'] = cfg.get('section', 'other')
            else:
                app_info['app_order'] = 999
                app_info['app_label'] = app_name
                app_info['section'] = 'other'
            
            app_list.append(app_info)

        # Model ordering within apps (prioritize the most-used items)
        model_order = {
            "siteconfig": [
                "SiteSettings",
                "ThemePack",
                "ReportCardStyle",
                "ReportCardStyleAssignment",
                "ReportTemplate",
                "Integration",
                "RegionConfig",
                "GradingScaleConfig",
                "HolidayCalendar",
                "DashboardWidget",
                "DashboardLayout",
                "DashboardUserPreference",
                "UserPreference",
                "FeatureControlAudit",
            ],
        }
        for app_info in app_list:
            order_list = model_order.get(app_info.get("app_label"))
            if not order_list:
                continue
            order_map = {name: idx for idx, name in enumerate(order_list)}
            app_info["models"].sort(
                key=lambda m: (order_map.get(m.get("object_name"), 999), m.get("name", "").lower())
            )

        # RBAC: hide app groups with zero models (after permission filtering)
        app_list = [app_info for app_info in app_list if (app_info.get('models') or [])]

        # Sort by custom order
        app_list.sort(key=lambda x: (x.get('app_order', 999), x['name'].lower()))

        return app_list


# Create custom admin site instance
admin_site = GileadAdminSite(name='admin')
