"""
Caching layer for rankings and performance optimization.
"""
from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone
from django.db.models import Avg, Count
from decimal import Decimal

from apps.academics.models import AcademicYear, Term
from apps.evals.models import Evaluation
from apps.siteconfig.models import SiteSettings
from apps.siteconfig.cache_utils import get_tenant_cache_prefix


def get_cache_key(subject_id=None, classroom_id=None, year_id=None, term_id=None):
    """Generate cache key for rankings (tenant-scoped to avoid cross-tenant leakage)."""
    prefix = get_tenant_cache_prefix(None)
    return f"{prefix}:rankings_{subject_id}_{classroom_id}_{year_id}_{term_id}"


def get_cached_rankings(year_id=None, term_id=None, subject_id=None, classroom_id=None, force_refresh=False):
    """
    Get cached rankings with TTL from site settings.
    
    Args:
        year_id: Academic year
        term_id: Term
        subject_id: Optional subject filter
        classroom_id: Optional classroom filter
        force_refresh: Force cache invalidation
    
    Returns:
        List of ranking dicts
    """
    # Use active year/term if not provided
    if not year_id or not term_id:
        year = AcademicYear.objects.filter(is_active=True).first()
        term = Term.objects.filter(is_active=True).first()
        year_id = year.id if year else None
        term_id = term.id if term else None
    
    if not year_id or not term_id:
        return []
    
    # Generate cache key
    cache_key = get_cache_key(subject_id, classroom_id, year_id, term_id)
    
    # Force refresh
    if force_refresh:
        cache.delete(cache_key)
    
    # Try to get from cache
    cached_rankings = cache.get(cache_key)
    if cached_rankings:
        return cached_rankings
    
    # Calculate rankings
    query = Evaluation.objects.filter(
        academic_year_id=year_id,
        term_id=term_id
    ).select_related('student', 'subject_assignment')
    
    if subject_id:
        query = query.filter(subject_assignment__subject_id=subject_id)
    if classroom_id:
        query = query.filter(student__classroom_id=classroom_id)
    
    # Group by student and calculate average
    rankings = query.values('student_id', 'student__user__first_name', 'student__user__last_name').annotate(
        avg_score=Avg('final_score')
    ).order_by('-avg_score')
    
    # Convert to list with rank and percentile
    result = []
    for idx, ranking in enumerate(rankings, start=1):
        percentile = (100 - ((idx - 1) / max(rankings.count() - 1, 1) * 100)) if rankings.count() > 1 else 100
        result.append({
            'rank': idx,
            'student_id': ranking['student_id'],
            'student_name': f"{ranking['student__user__first_name']} {ranking['student__user__last_name']}",
            'score': float(ranking['avg_score']) if ranking['avg_score'] else 0,
            'percentile': round(percentile, 1),
        })
    
    # Set cache TTL from site settings
    site_settings = SiteSettings.load()
    cache_ttl_minutes = site_settings.cache_rankings_interval_minutes or 60
    cache_ttl_seconds = cache_ttl_minutes * 60
    
    cache.set(cache_key, result, cache_ttl_seconds)
    
    return result


def invalidate_rankings_cache(year_id=None, term_id=None, subject_id=None, classroom_id=None):
    """Invalidate cache for specific rankings."""
    if not year_id and not term_id:
        # Invalidate all rankings caches
        prefix = get_tenant_cache_prefix(None)
        cache.delete_pattern(f"{prefix}:rankings_*")
    else:
        cache_key = get_cache_key(subject_id, classroom_id, year_id, term_id)
        cache.delete(cache_key)


def warm_rankings_cache(year_id=None, term_id=None):
    """Pre-populate cache for faster subsequent queries."""
    if not year_id or not term_id:
        year = AcademicYear.objects.filter(is_active=True).first()
        term = Term.objects.filter(is_active=True).first()
        year_id = year.id if year else None
        term_id = term.id if term else None
    
    if not year_id or not term_id:
        return 0
    
    # Get all unique subject/classroom combinations
    combinations = Evaluation.objects.filter(
        academic_year_id=year_id,
        term_id=term_id
    ).values('subject_assignment__subject_id', 'student__classroom_id').distinct()
    
    warmed_count = 0
    for combo in combinations:
        subject_id = combo['subject_assignment__subject_id']
        classroom_id = combo['student__classroom_id']
        
        # Pre-populate cache
        get_cached_rankings(
            year_id=year_id,
            term_id=term_id,
            subject_id=subject_id,
            classroom_id=classroom_id,
            force_refresh=True
        )
        warmed_count += 1
    
    return warmed_count


def get_cache_stats():
    """Get cache performance statistics."""
    # This requires Django cache with statistics support
    try:
        stats = cache._cache.get_stats()
        return stats
    except Exception:
        return {}
