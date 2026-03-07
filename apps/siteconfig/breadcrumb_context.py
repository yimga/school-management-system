"""
Phase 7 Task 5: Breadcrumb navigation context processor
Provides breadcrumb data to all templates for consistent navigation
"""
from django.http import QueryDict
from django.urls import resolve, reverse
from urllib.parse import urlparse, parse_qs


def breadcrumbs_context(request):
    """
    Add breadcrumb navigation to template context.
    
    Usage in templates:
    {% include "partials/breadcrumbs.html" %}
    """
    
    breadcrumbs = []
    
    # Always include home
    breadcrumbs.append({
        'name': 'Home',
        'url': '/',
        'active': request.path == '/',
    })
    
    # Get current path
    path = request.path
    path_parts = [p for p in path.split('/') if p]
    
    # Build breadcrumbs from path
    cumulative_path = ''
    for i, part in enumerate(path_parts):
        cumulative_path += f'/{part}'
        is_last = (i == len(path_parts) - 1)
        
        # Create human-readable name
        name = part.replace('-', ' ').replace('_', ' ').title()
        
        breadcrumbs.append({
            'name': name,
            'url': cumulative_path if not is_last else None,
            'active': is_last,
        })
    
    # Override with semantic names for specific paths
    breadcrumb_labels = {
        'academics': 'Academics',
        'evaluations': 'Evaluations',
        'report-cards': 'Report Cards',
        'finance': 'Finance',
        'invoices': 'Invoices',
        'pay-slips': 'Pay Slips',
        'payroll': 'Payroll',
        'portal': 'Portal',
        'student-portal': 'Student Portal',
        'teacher-portal': 'Teacher Portal',
        'parent-portal': 'Parent Portal',
        'authentication': 'Authentication',
        'administration': 'Administration',
        'settings': 'Settings',
        'siteconfig': 'Site Settings',
        'feature-control': 'Feature Control',
        'customizer': 'Customizer',
        'users': 'Users',
        'roles': 'Roles',
        'dashboard': 'Dashboard',
    }
    
    # Apply semantic labels
    for breadcrumb in breadcrumbs:
        path_part = breadcrumb['name'].lower().replace(' ', '-')
        if path_part in breadcrumb_labels:
            breadcrumb['name'] = breadcrumb_labels[path_part]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_breadcrumbs = []
    for bc in breadcrumbs:
        if bc['name'] not in seen:
            unique_breadcrumbs.append(bc)
            seen.add(bc['name'])
    
    return {
        'breadcrumbs': unique_breadcrumbs,
    }


def page_metadata_context(request):
    """
    Add page metadata (title, description, etc.) to context
    for SEO and accessibility.
    """
    
    path = request.path
    
    # Page metadata by path
    metadata = {
        '/': {
            'title': 'RunMyCampus',
            'description': 'Comprehensive school management solution',
        },
        '/student-portal/': {
            'title': 'Student Portal',
            'description': 'Access your academic information',
        },
        '/teacher-portal/': {
            'title': 'Teacher Portal',
            'description': 'Manage classes and grades',
        },
        '/parent-portal/': {
            'title': 'Parent Portal',
            'description': 'Monitor your child\'s progress',
        },
        '/administration/': {
            'title': 'Administration',
            'description': 'System administration panel',
        },
    }
    
    # Find best match
    page_meta = None
    for route, meta in metadata.items():
        if path.startswith(route):
            page_meta = meta
            break
    
    if not page_meta:
        page_meta = {
            'title': 'RunMyCampus',
            'description': 'School management system',
        }
    
    return {
        'page_title': page_meta.get('title', ''),
        'page_description': page_meta.get('description', ''),
    }
