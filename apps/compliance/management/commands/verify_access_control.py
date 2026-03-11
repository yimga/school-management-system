"""
Phase 4: Verify access control consistency across endpoints.

Scans all registered URL patterns and checks for:
1. Proper use of access control decorators
2. Authenticated requirements
3. Permission checks
4. Role-based access rules

Usage: python manage.py verify_access_control [--fix] [--verbose]
"""

import inspect

from django.core.management.base import BaseCommand
from django.urls import get_resolver
from django.views.generic import View


PUBLIC_ROUTE_EXACT = {
    "",
    "portal",
    "robots.txt",
    "sitemap.xml",
    "backend/",
    "api/weather/context/",
    "api/admissions/lead/",
    "api/interop/oneroster/",
    "api/interop/lti13/",
    "api/interop/edfi/",
    "api/interop/ceds/",
    "api/v1/enrollment/apply",
}

PUBLIC_ROUTE_PREFIXES = (
    "api/caddy-check/",
    "api/trial/",
    "api/v1/auth/check-domain/",
    "offline/",
    "i18n/setlang/",
    "ready/",
    "metrics/",
    "graphql/",
    "discover/",
    "find/",
    "verify/",
    "support/",
    "marketing/",
    "education-operating-system/",
    "platform/",
    "product/",
    "products/",
    "solutions/",
    "pricing/",
    "compare/",
    "case-studies/",
    "customers/",
    "security-compliance/",
    "integrations/",
    "book-demo/",
    "interactive-preview/",
    "product-tour/",
    "getting-started/",
    "themes/",
    "design-studio/",
    "uptime/",
    "buyer-toolkit/",
    "funnel-dashboard/",
    "about/",
    "features/",
    "blog/",
    "contact/",
    "why-switch/",
    "school-management-system/",
    "student-information-system/",
    "education-erp/",
    "school-administration-software/",
    "10-reasons/",
    "resources/",
    "research/",
    "reports/",
    "guides/",
    "events/",
    "trust-center/",
    "developers/",
    "app-marketplace/",
    "privacy/",
    "terms/",
    "cookie-policy/",
    "cm/",
    "ca/",
    "setup-studio/",
    "onboard/",
    "signup/",
    "verify-signup/",
    "authentication/",
    "portal/",
    "kb/",
    "lti/",
    "account-frozen/",
    "help/",
)

MIDDLEWARE_PROTECTED_PREFIXES = (
    "super/",
)

CRITICAL_ROUTE_PREFIXES = (
    "finance/",
    "api/v1/finance/",
    "api/interop/edfi/grades/",
    "api/interop/ceds/grades/",
    "salary/",
)


class Command(BaseCommand):
    help = "Verify access control consistency across all endpoints"

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix issues automatically (not implemented)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each endpoint'
        )

    def handle(self, *args, **options):
        self.verbose = options.get('verbose', False)
        self.issues = []
        self.checked = 0

        self.stdout.write("Phase 4: Verifying Access Control Consistency")
        self.stdout.write("=" * 60)

        # Get all URL patterns
        resolver = get_resolver()
        self._check_patterns(resolver.url_patterns)

        # Print results
        self.stdout.write(f"\nChecked: {self.checked} endpoints")
        if self.issues:
            self.stdout.write(self.style.WARNING(f"Issues found: {len(self.issues)}"))
            self._print_issues()
        else:
            self.stdout.write(self.style.SUCCESS("No access control issues found!"))

    def _check_patterns(self, patterns, prefix=""):
        """Recursively check all URL patterns."""
        for pattern in patterns:
            # Handle nested patterns (include())
            if hasattr(pattern, 'url_patterns'):
                new_prefix = prefix + str(pattern.pattern)
                self._check_patterns(pattern.url_patterns, new_prefix)
                continue

            # Get pattern info
            path = prefix + str(pattern.pattern)
            callback = pattern.callback

            # Skip admin, static, media
            if any(skip in str(path) for skip in ['admin/', 'static/', 'media/', '.well-known']):
                continue

            self.checked += 1

            # Check the view function/class
            if self.verbose:
                self.stdout.write(f"\nChecking: {path}")

            self._check_view_access(path, callback)

    def _check_view_access(self, path, view):
        """Check if view has proper access control."""
        if view is None:
            return

        view_funcs = self._view_functions_for_access_check(view)

        # Check for access control decorators
        has_login_required = any(self._has_login_protection(func) for func in view_funcs)
        has_permission_required = any(self._has_decorator(func, 'permission_required') for func in view_funcs)
        has_role_required = any(
            self._has_decorator(func, 'require_role')
            or self._has_decorator(func, 'role_required')
            for func in view_funcs
        )
        has_observability_auth = any(
            self._has_decorator(func, 'observability_auth_required')
            for func in view_funcs
        )
        has_staff_member_required = any(self._has_staff_member_protection(func) for func in view_funcs)
        has_user_passes_test = any(self._has_decorator(func, 'user_passes_test') for func in view_funcs)
        has_drf_permission_control = self._has_drf_permission_control(view)
        has_manual_auth_guard = any(self._has_manual_auth_guard(func) for func in view_funcs)
        has_manual_permission_guard = any(self._has_manual_permission_guard(func) for func in view_funcs)
        is_public_route = self._is_public_route(path)
        is_middleware_protected = self._is_middleware_protected(path)
        has_access_control = any(
            [
                has_login_required,
                has_permission_required,
                has_role_required,
                has_observability_auth,
                has_staff_member_required,
                has_user_passes_test,
                has_drf_permission_control,
                has_manual_auth_guard,
                has_manual_permission_guard,
                is_middleware_protected,
            ]
        )

        # Determine if endpoint needs protection
        needs_protection = not is_public_route and not any(skip in str(path) for skip in [
            'login',
            'logout',
            'register',
            'forgot',
            'reset',
            'health',
            'status',
        ])

        # Check for issues
        if needs_protection and not has_access_control:
            self.issues.append({
                'path': path,
                'issue': 'No access control decorator found',
                'severity': 'HIGH'
            })

        # Check for critical paths
        if self._is_critical_route(path):
            if not (
                has_permission_required
                or has_role_required
                or has_observability_auth
                or has_staff_member_required
                or has_drf_permission_control
                or has_manual_permission_guard
                or is_middleware_protected
            ):
                self.issues.append({
                    'path': path,
                    'issue': 'Critical endpoint missing permission check',
                    'severity': 'CRITICAL'
                })

        if self.verbose:
            decorators = []
            if has_login_required:
                decorators.append('login_required')
            if has_permission_required:
                decorators.append('permission_required')
            if has_role_required:
                decorators.append('require_role')
            if has_observability_auth:
                decorators.append('observability_auth_required')
            if has_staff_member_required:
                decorators.append('staff_member_required')
            if has_user_passes_test:
                decorators.append('user_passes_test')
            if has_drf_permission_control:
                decorators.append('drf_permissions')
            if has_manual_auth_guard:
                decorators.append('manual_auth_guard')
            if has_manual_permission_guard:
                decorators.append('manual_permission_guard')
            if is_middleware_protected:
                decorators.append('middleware_protected')
            if is_public_route:
                decorators.append('public_route')

            status = "✓ Protected" if decorators else "✗ Unprotected"
            self.stdout.write(f"  {status}: {', '.join(decorators) if decorators else 'none'}")

    def _view_functions_for_access_check(self, view):
        funcs = []

        def _add(candidate):
            if callable(candidate) and candidate not in funcs:
                funcs.append(candidate)

        _add(view)
        if isinstance(view, View):
            _add(view.dispatch)

        view_class = getattr(view, 'cls', None) or getattr(view, 'view_class', None)
        if view_class is not None:
            for method_name in ('dispatch', 'get', 'post', 'put', 'patch', 'delete', 'head', 'options'):
                _add(getattr(view_class, method_name, None))

        return funcs

    def _has_decorator(self, func, decorator_name):
        """Check if function has a specific decorator."""
        seen = set()
        current = func.__func__ if hasattr(func, '__self__') else func
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if hasattr(current, decorator_name):
                return True
            if hasattr(current, f'_{decorator_name}_decorated'):
                return True
            try:
                source = inspect.getsource(current)
                if f"@{decorator_name}" in source:
                    return True
            except (OSError, TypeError):
                pass
            if hasattr(current, '__closure__') and current.__closure__:
                for cell in current.__closure__:
                    try:
                        if decorator_name in repr(cell.cell_contents):
                            return True
                    except (ValueError, TypeError):
                        pass
            current = getattr(current, '__wrapped__', None)
        return False

    def _has_login_protection(self, func):
        if self._has_decorator(func, 'login_required'):
            return True
        return hasattr(func, 'login_url') or hasattr(func, 'redirect_field_name')

    def _has_staff_member_protection(self, func):
        if self._has_decorator(func, 'staff_member_required'):
            return True
        login_url = getattr(func, 'login_url', None)
        return login_url == 'admin:login'

    def _has_drf_permission_control(self, view) -> bool:
        callback = getattr(view, 'cls', None) or view
        permission_classes = getattr(callback, 'permission_classes', None)
        if not permission_classes:
            return False
        class_names = {getattr(permission, '__name__', str(permission)) for permission in permission_classes}
        return 'AllowAny' not in class_names

    def _is_public_route(self, path: str) -> bool:
        normalized = str(path or '').lstrip('/')
        if normalized in PUBLIC_ROUTE_EXACT:
            return True
        return any(normalized.startswith(prefix) for prefix in PUBLIC_ROUTE_PREFIXES)

    def _is_middleware_protected(self, path: str) -> bool:
        normalized = str(path or '').lstrip('/')
        return any(normalized.startswith(prefix) for prefix in MIDDLEWARE_PROTECTED_PREFIXES)

    def _is_critical_route(self, path: str) -> bool:
        normalized = str(path or '').lstrip('/')
        return any(normalized.startswith(prefix) for prefix in CRITICAL_ROUTE_PREFIXES)

    def _has_manual_auth_guard(self, func) -> bool:
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError):
            return False
        auth_markers = (
            "request.user.is_authenticated",
            "redirect_to_login(",
            "Authentication required",
            "@require_http_methods",
        )
        return any(marker in source for marker in auth_markers)

    def _has_manual_permission_guard(self, func) -> bool:
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError):
            return False
        permission_markers = (
            "_require_super_or_school(",
            "_require_finance_operator(",
            "_require_parent_finance_or_operator_access(",
            "_require_staff(",
            "_finance_access_state(",
            "HttpResponseForbidden(",
            "return err",
            "request.user.is_superuser",
            "request.user.is_staff",
            "role in allowed_roles",
            "user_passes_test(",
        )
        return any(marker in source for marker in permission_markers)

    def _print_issues(self):
        """Print all found issues."""
        critical = [i for i in self.issues if i.get('severity') == 'CRITICAL']
        high = [i for i in self.issues if i.get('severity') == 'HIGH']

        if critical:
            self.stdout.write(self.style.ERROR(f"\nCRITICAL ISSUES ({len(critical)}):"))
            for issue in critical:
                self.stdout.write(f"  • {issue['path']}")
                self.stdout.write(f"    {issue['issue']}")

        if high:
            self.stdout.write(self.style.WARNING(f"\nHIGH ISSUES ({len(high)}):"))
            for issue in high:
                self.stdout.write(f"  • {issue['path']}")
                self.stdout.write(f"    {issue['issue']}")
