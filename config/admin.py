"""
Custom Admin Site Configuration
Provides enhanced admin interface with logical app grouping and custom ordering
"""
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.urls import path
from django.shortcuts import redirect


class GileadAdminSite(AdminSite):
    """Custom admin site with enhanced organization and features."""
    
    site_header = "Gilead Tech High - Admin"
    site_title = "Gilead Admin"
    index_title = "Administration Dashboard"
    
    def get_urls(self):
        """Add custom URLs including 'home' for Unfold navigation."""
        urls = super().get_urls()
        custom_urls = [
            path('home/', lambda request: redirect('/'), name='home'),
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

# Register app admin modules into the custom admin site
# This ensures all @admin.register(...) in app admin.py files bind to our custom site
from django.utils.module_loading import autodiscover_modules
autodiscover_modules('admin', register_to=admin_site)
