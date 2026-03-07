"""
Custom Admin Site Configuration
Provides enhanced admin interface with logical app grouping and custom ordering
"""
from apps.dashboard.admin_context import build_admin_dashboard_context

from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, path, reverse
from django.utils.safestring import mark_safe
from unfold.sites import UnfoldAdminSite


class RunMyCampusAdminSite(UnfoldAdminSite):
    """
    Configuration engine: full model CRUD, raw settings, system config.
    Access: superuser only. Superadmin-only; no tenant context or branding.
    Extends UnfoldAdminSite for sidebar/app list.
    """

    enable_nav_sidebar = True
    login_template = "auth/admin_login.html"
    site_header = "Configuration Engine"
    site_title = "Configuration Engine"
    index_title = "Administration Dashboard"

    def each_context(self, request):
        context = super().each_context(request)
        context["is_manager_host"] = getattr(request, "public_host_kind", None) == "manager"
        if context["is_manager_host"]:
            try:
                from apps.schools.tenant_url import build_public_absolute_url
                context["public_site_url"] = build_public_absolute_url(request, "/")
            except Exception:
                context["public_site_url"] = "https://runmycampus.com"
        else:
            context["public_site_url"] = None
        try:
            context["extra_userlinks"] = mark_safe(
                render_to_string("admin/extra_user_links.html", context)
            )
        except Exception:
            context["extra_userlinks"] = ""
        # MFA encouragement: show dismissible banner for staff without MFA
        try:
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

    def login(self, request, extra_context=None):
        """Add safe password_reset_url and public_site_url to context for high-end login template."""
        extra_context = extra_context or {}
        try:
            extra_context["password_reset_url"] = reverse("admin:password_reset")
        except NoReverseMatch:
            try:
                extra_context["password_reset_url"] = reverse("admin:admin_password_reset")
            except NoReverseMatch:
                extra_context["password_reset_url"] = None
        try:
            from apps.schools.tenant_url import build_public_absolute_url
            extra_context["public_site_url"] = build_public_absolute_url(request, "/")
        except Exception:
            extra_context["public_site_url"] = "https://runmycampus.com"
        return super().login(request, extra_context=extra_context)

    def index(self, request, extra_context=None):
        """Render the custom admin dashboard at /admin/."""
        context = build_admin_dashboard_context(
            request,
            base_context=self.each_context(request),
            title=self.index_title,
        )
        if extra_context:
            context.update(extra_context)

        return TemplateResponse(request, "admin/index.html", context)

    def dashboard_redirect(self, request):
        """Legacy /admin/dashboard/ route redirected to canonical /admin/."""
        return redirect("admin:index")
    
    def get_urls(self):
        """Add custom URLs including 'home' for Unfold navigation."""
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_redirect), name='dashboard'),
            path('home/', lambda request: redirect('/'), name='home'),
            # search/ is provided by UnfoldAdminSite for sidebar "Jump to model" - do not override
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
admin_site = RunMyCampusAdminSite(name='admin')
