"""
Phase 4: Verify access control consistency across endpoints.

Scans all registered URL patterns and checks for:
1. Proper use of access control decorators
2. Authenticated requirements
3. Permission checks
4. Role-based access rules

Usage: python manage.py verify_access_control [--fix] [--verbose]
"""

from django.core.management.base import BaseCommand
from django.urls import get_resolver
from django.views.generic import View
import inspect


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

        # Get the actual view function (handles class-based views)
        if isinstance(view, View):
            dispatch = view.dispatch
            view_func = dispatch
        else:
            view_func = view

        # Check for access control decorators
        has_login_required = self._has_decorator(view_func, 'login_required')
        has_permission_required = self._has_decorator(view_func, 'permission_required')
        has_role_required = self._has_decorator(view_func, 'require_role')

        # Determine if endpoint needs protection
        needs_protection = not any(skip in str(path) for skip in [
            'login',
            'logout',
            'register',
            'forgot',
            'reset',
            'health',
            'status',
        ])

        # Check for issues
        if needs_protection and not (has_login_required or has_permission_required or has_role_required):
            self.issues.append({
                'path': path,
                'issue': 'No access control decorator found',
                'severity': 'HIGH'
            })

        # Check for critical paths
        if any(critical in str(path) for critical in ['admin', 'finance', 'grade', 'payment', 'salary']):
            if not (has_permission_required or has_role_required):
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

            status = "✓ Protected" if decorators else "✗ Unprotected"
            self.stdout.write(f"  {status}: {', '.join(decorators) if decorators else 'none'}")

    def _has_decorator(self, func, decorator_name):
        """Check if function has a specific decorator."""
        # For class-based views, check the method
        if hasattr(func, '__self__'):
            func = func.__func__

        # Check closure for decorator
        if hasattr(func, '__closure__') and func.__closure__:
            for cell in func.__closure__:
                try:
                    if decorator_name in str(cell.cell_contents):
                        return True
                except (ValueError, TypeError):
                    pass

        # Check function attributes
        if hasattr(func, decorator_name):
            return True

        # Check for specific marker attributes set by decorators
        if hasattr(func, f'_{decorator_name}_decorated'):
            return True

        return False

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
