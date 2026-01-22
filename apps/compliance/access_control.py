"""
Phase 8 Task 1: Access Control Module
Implements fine-grained RBAC and resource-level security
"""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import Permission, Group
from functools import wraps
from .models import IPAccessRule, CountryAccessRule


class AccessControlManager:
    """Manage fine-grained access control"""
    
    @staticmethod
    def check_ip_access(ip_address):
        """Check if IP address is allowed"""
        try:
            rule = IPAccessRule.objects.get(ip_address=ip_address)
            
            # Check if rule has expired
            if rule.expires_at and rule.expires_at < timezone.now():
                return True  # Expired rule is ignored
            
            return rule.action != 'DENY'
        except IPAccessRule.DoesNotExist:
            return True  # No rule means allow
    
    @staticmethod
    def check_country_access(country_code):
        """Check if country is allowed"""
        try:
            rule = CountryAccessRule.objects.get(country_code=country_code)
            return rule.action != 'DENY'
        except CountryAccessRule.DoesNotExist:
            return True  # No rule means allow
    
    @staticmethod
    def check_user_permission(user, permission_codename):
        """Check if user has specific permission"""
        return user.has_perm(f'auth.{permission_codename}')
    
    @staticmethod
    def check_resource_access(user, resource, action):
        """Check if user can access resource"""
        from django.apps import apps
        
        # Parse resource (format: app.model.id)
        try:
            app, model, obj_id = resource.split('.')
            model_class = apps.get_model(app, model)
            obj = model_class.objects.get(id=obj_id)
            
            # Check role-based access
            if hasattr(obj, 'check_access'):
                return obj.check_access(user, action)
            
            return True
        except:
            return False


class AccessControlDecorator:
    """Decorators for access control"""
    
    @staticmethod
    def require_permission(permission):
        """Require specific permission"""
        def decorator(view_func):
            @wraps(view_func)
            def wrapper(request, *args, **kwargs):
                if not request.user.has_perm(permission):
                    raise PermissionDenied(f"User lacks permission: {permission}")
                return view_func(request, *args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def require_role(role_name):
        """Require specific role"""
        def decorator(view_func):
            @wraps(view_func)
            def wrapper(request, *args, **kwargs):
                try:
                    user_group = request.user.groups.get(name=role_name)
                except:
                    raise PermissionDenied(f"User is not in group: {role_name}")
                return view_func(request, *args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def check_ip_access_decorator(view_func):
        """Check IP access before view"""
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from django.http import HttpResponseForbidden
            
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            if not AccessControlManager.check_ip_access(ip):
                return HttpResponseForbidden("Access denied from your IP address")
            
            return view_func(request, *args, **kwargs)
        return wrapper


class RoleBasedAccessControl:
    """RBAC system with predefined roles"""
    
    ROLES = {
        'ADMIN': {
            'permissions': [
                'auth.add_user',
                'auth.change_user',
                'auth.delete_user',
                'auth.view_user',
                'compliance.view_accesslog',
                'compliance.view_auditlog',
                'evals.add_eval',
                'evals.change_eval',
                'evals.delete_eval',
                'finance.add_invoice',
                'finance.change_invoice',
            ],
            'description': 'System administrator with full access',
        },
        'TEACHER': {
            'permissions': [
                'evals.view_eval',
                'evals.add_eval',
                'evals.change_eval',
                'people.view_studentprofile',
                'analytics.view_analytics',
            ],
            'description': 'Teacher - can manage grades and view student data',
        },
        'PARENT': {
            'permissions': [
                'portal.view_portal',
                'analytics.view_own_analytics',
            ],
            'description': 'Parent - can view own child\'s data',
        },
        'STUDENT': {
            'permissions': [
                'portal.view_portal',
                'evals.view_own_results',
            ],
            'description': 'Student - limited portal access',
        },
        'FINANCE': {
            'permissions': [
                'finance.view_invoice',
                'finance.add_invoice',
                'finance.change_invoice',
                'finance.view_payment',
                'reports.view_financial_reports',
            ],
            'description': 'Finance officer - financial data access',
        },
        'AUDITOR': {
            'permissions': [
                'compliance.view_accesslog',
                'compliance.view_auditlog',
                'compliance.view_compliancereport',
                'analytics.view_analytics',
            ],
            'description': 'Auditor - compliance and audit access',
        },
    }
    
    @classmethod
    def create_roles(cls):
        """Create predefined roles in system"""
        for role_name, role_data in cls.ROLES.items():
            group, created = Group.objects.get_or_create(name=role_name)
            
            if created:
                # Add permissions to group
                for perm in role_data['permissions']:
                    try:
                        app, codename = perm.split('.')
                        permission = Permission.objects.get(
                            content_type__app_label=app,
                            codename=codename
                        )
                        group.permissions.add(permission)
                    except:
                        pass
    
    @classmethod
    def assign_role(cls, user, role_name):
        """Assign role to user"""
        if role_name not in cls.ROLES:
            raise ValueError(f"Invalid role: {role_name}")
        
        group = Group.objects.get(name=role_name)
        user.groups.add(group)
    
    @classmethod
    def remove_role(cls, user, role_name):
        """Remove role from user"""
        group = Group.objects.get(name=role_name)
        user.groups.remove(group)


class ResourceLevelSecurity:
    """Implement resource-level access control"""
    
    @staticmethod
    def can_view_student(user, student):
        """Check if user can view student data"""
        if user.is_superuser:
            return True
        
        # Teacher can view own students
        if hasattr(user, 'teacherprofile'):
            return student in user.teacherprofile.classroom_set.values_list(
                'students', flat=True
            )
        
        # Parent can view own children
        if hasattr(user, 'studentguardian'):
            return student.id in user.studentguardian.student.values_list('id', flat=True)
        
        # Student can view self
        if hasattr(user, 'studentprofile'):
            return student.id == user.studentprofile.student.id
        
        return False
    
    @staticmethod
    def can_modify_grade(user, grade):
        """Check if user can modify grade"""
        if user.is_superuser:
            return True
        
        # Only assignment teacher can modify
        if hasattr(user, 'teacherprofile'):
            return grade.assignment.subject.teacher == user
        
        return False
    
    @staticmethod
    def can_view_finance(user, invoice):
        """Check if user can view financial data"""
        if user.is_superuser:
            return True
        
        # Finance staff can view all
        if user.groups.filter(name='FINANCE').exists():
            return True
        
        # Parent can view own invoices
        if hasattr(user, 'studentguardian'):
            return invoice.student in user.studentguardian.student.all()
        
        return False
