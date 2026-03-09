"""
Admin Extras Template Tags
Provides template tags for admin interface enhancements like item counts.
RBAC: get_all_model_counts is request-aware and only returns counts for models
the user has view permission for.
World Engine: cache keys are tenant-scoped to avoid cross-tenant leakage.
"""
from django import template
from django.apps import apps
from django.core.cache import cache
from django.contrib.admin.sites import site as default_admin_site

register = template.Library()


def _admin_cache_prefix(context=None):
    from apps.siteconfig.cache_utils import get_tenant_cache_prefix
    request = context.get("request") if context else None
    return get_tenant_cache_prefix(request)


@register.simple_tag(takes_context=True)
def get_model_count(context, app_label, model_name):
    """
    Get the count of objects for a specific model.
    Results are cached for 5 minutes to improve performance (tenant-scoped).
    
    Usage: {% get_model_count 'accounts' 'User' %}
    """
    prefix = _admin_cache_prefix(context)
    cache_key = f"{prefix}:admin_count_{app_label}_{model_name}"
    count = cache.get(cache_key)
    
    if count is None:
        try:
            model = apps.get_model(app_label, model_name)
            count = model.objects.count()
            # Cache for 5 minutes
            cache.set(cache_key, count, 300)
        except (LookupError, AttributeError):
            count = 0
    
    return count


@register.simple_tag(takes_context=True)
def get_all_model_counts(context):
    """
    Get counts for registered admin models the current user has view permission for.
    Returns a dictionary mapping 'app_label.model_name' to count.
    Cached per user for 5 minutes (RBAC-compliant).

    Usage: {% get_all_model_counts as model_counts %}
    """
    request = context.get('request')
    if not request or not getattr(request, 'user', None):
        return {}

    user = request.user
    # Use admin site from context if available (e.g. custom RunMyCampusAdminSite), else default
    admin_site_obj = context.get('site', default_admin_site)
    registry = getattr(admin_site_obj, '_registry', default_admin_site._registry)

    prefix = _admin_cache_prefix(context)
    cache_key = f"{prefix}:admin_all_model_counts_{getattr(user, 'pk', id(user))}"
    counts = cache.get(cache_key)

    if counts is None:
        counts = {}
        for model, model_admin in registry.items():
            if not getattr(model_admin, 'has_view_permission', lambda r: True)(request):
                continue
            app_label = model._meta.app_label
            model_name = model._meta.model_name
            key = f"{app_label}.{model_name}"
            try:
                counts[key] = model.objects.count()
            except Exception:
                counts[key] = 0
        cache.set(cache_key, counts, 300)

    return counts


@register.simple_tag(takes_context=True)
def add_preserved_filters_with_next(context, add_url, is_popup=False, to_field=None):
    """
    Return the add URL with preserved changelist filters and next= for return-to-origin.
    Usage: {% add_preserved_filters_with_next add_url is_popup to_field %}
    """
    from urllib.parse import quote

    try:
        from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
        base = add_preserved_filters(context, add_url, is_popup, to_field)
    except Exception:
        base = add_url or ""
    request = context.get("request")
    if not request:
        return base
    full_path = request.get_full_path()
    if not full_path:
        return base
    sep = "&" if "?" in base else "?"
    return base + sep + "next=" + quote(full_path, safe="/")


@register.filter
def format_count(count):
    """
    Format a count number for display.
    Shows '1K' for 1000, '1M' for 1000000, etc.
    
    Usage: {{ count|format_count }}
    """
    if count is None:
        return '0'
    
    count = int(count)
    
    if count >= 1000000:
        return f'{count / 1000000:.1f}M'
    elif count >= 1000:
        return f'{count / 1000:.1f}K'
    else:
        return str(count)


@register.inclusion_tag('admin/includes/model_count_badge.html', takes_context=True)
def model_count_badge(context, app_label, model_name):
    """
    Render a count badge for a model (tenant-scoped cache).
    
    Usage: {% model_count_badge 'accounts' 'User' %}
    """
    count = get_model_count(context, app_label, model_name)
    return {
        'count': count,
        'formatted_count': format_count(count),
        'has_items': count > 0,
    }
