"""
Admin Extras Template Tags
Provides template tags for admin interface enhancements like item counts
"""
from django import template
from django.apps import apps
from django.core.cache import cache
from django.contrib.admin.sites import site as admin_site

register = template.Library()


@register.simple_tag
def get_model_count(app_label, model_name):
    """
    Get the count of objects for a specific model.
    Results are cached for 5 minutes to improve performance.
    
    Usage: {% get_model_count 'accounts' 'User' %}
    """
    cache_key = f"admin_count_{app_label}_{model_name}"
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


@register.simple_tag
def get_all_model_counts():
    """
    Get counts for all registered admin models.
    Returns a dictionary mapping 'app_label.model_name' to count.
    Cached for 5 minutes.
    
    Usage: {% get_all_model_counts as model_counts %}
    """
    cache_key = "admin_all_model_counts"
    counts = cache.get(cache_key)
    
    if counts is None:
        counts = {}
        for model, model_admin in admin_site._registry.items():
            app_label = model._meta.app_label
            model_name = model._meta.model_name
            key = f"{app_label}.{model_name}"
            try:
                counts[key] = model.objects.count()
            except Exception:
                counts[key] = 0
        
        # Cache for 5 minutes
        cache.set(cache_key, counts, 300)
    
    return counts


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


@register.inclusion_tag('admin/includes/model_count_badge.html')
def model_count_badge(app_label, model_name):
    """
    Render a count badge for a model.
    
    Usage: {% model_count_badge 'accounts' 'User' %}
    """
    count = get_model_count(app_label, model_name)
    return {
        'count': count,
        'formatted_count': format_count(count),
        'has_items': count > 0,
    }
