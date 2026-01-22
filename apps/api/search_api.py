# apps/api/search_api.py
"""
Global Search API
Location: apps/api/search_api.py

Unified search across all system resources
"""

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Q
from django.views.decorators.http import require_http_methods
import logging

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
@method_decorator(require_http_methods(["GET"]), name='dispatch')
class GlobalSearchAPI(View):
    """
    Global search across system
    
    Query Parameters:
    - q: search query (required, min 2 chars)
    - type: specific type to search (optional: all, student, teacher, class, invoice, subject)
    - limit: results per type (default 20)
    
    Usage:
    GET /api/search/?q=john&limit=20
    GET /api/search/?q=math&type=subject
    """
    
    SEARCH_CONFIG = {
        'student': {
            'model': 'StudentProfile',
            'search_fields': ['user__first_name', 'user__last_name', 'student_id'],
            'icon': 'bi-person',
            'color': 'primary',
        },
        'teacher': {
            'model': 'TeacherProfile',
            'search_fields': ['user__first_name', 'user__last_name', 'staff_id', 'subject'],
            'icon': 'bi-person-badge',
            'color': 'success',
        },
        'class': {
            'model': 'ClassRoom',
            'search_fields': ['name', 'code'],
            'icon': 'bi-people',
            'color': 'info',
        },
        'subject': {
            'model': 'Subject',
            'search_fields': ['name', 'code'],
            'icon': 'bi-book',
            'color': 'warning',
        },
        'invoice': {
            'model': 'Invoice',
            'search_fields': ['invoice_number', 'student__user__first_name', 'student__user__last_name'],
            'icon': 'bi-receipt',
            'color': 'danger',
        },
    }
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        search_type = request.GET.get('type', 'all')
        limit = int(request.GET.get('limit', 20))
        
        # Validate query
        if len(query) < 2:
            return JsonResponse({
                'error': 'Query too short. Minimum 2 characters required.'
            }, status=400)
        
        results = []
        
        # Determine which types to search
        if search_type == 'all':
            types_to_search = list(self.SEARCH_CONFIG.keys())
        else:
            types_to_search = [search_type]
        
        # Search each type
        for search_type_key in types_to_search:
            config = self.SEARCH_CONFIG.get(search_type_key)
            if not config:
                continue
            
            try:
                items = self._search_type(config, query, limit)
                results.extend(items)
            except Exception as e:
                logger.error(f"Search error for {search_type_key}: {e}")
        
        return JsonResponse({
            'query': query,
            'count': len(results),
            'results': results
        })
    
    def _search_type(self, config, query, limit):
        """Search a specific resource type"""
        results = []
        
        # Build query
        q_object = Q()
        for field in config['search_fields']:
            q_object |= Q(**{f'{field}__icontains': query})
        
        # Get model dynamically
        if config['model'] == 'StudentProfile':
            from apps.people.models import StudentProfile
            items = StudentProfile.objects.filter(q_object, is_active=True)[:limit]
            for item in items:
                results.append({
                    'id': item.id,
                    'type': 'student',
                    'title': item.user.get_full_name(),
                    'description': f"Grade {item.current_class} - ID: {item.student_id}",
                    'url': f"/portal/student/{item.id}/",
                    'icon': 'bi-person',
                    'metadata': {
                        'grade': str(item.current_class),
                        'status': 'Active' if item.is_active else 'Inactive'
                    }
                })
        
        elif config['model'] == 'TeacherProfile':
            from apps.people.models import TeacherProfile
            items = TeacherProfile.objects.filter(q_object, is_active=True)[:limit]
            for item in items:
                results.append({
                    'id': item.id,
                    'type': 'teacher',
                    'title': item.user.get_full_name(),
                    'description': f"Staff ID: {item.staff_id}",
                    'url': f"/portal/teacher/{item.id}/",
                    'icon': 'bi-person-badge',
                    'metadata': {
                        'subject': item.subject or 'N/A',
                        'status': 'Active' if item.is_active else 'Inactive'
                    }
                })
        
        elif config['model'] == 'ClassRoom':
            from apps.academics.models import ClassRoom
            items = ClassRoom.objects.filter(q_object)[:limit]
            for item in items:
                results.append({
                    'id': item.id,
                    'type': 'class',
                    'title': item.name,
                    'description': f"Code: {item.code}",
                    'url': f"/evals/class/{item.id}/",
                    'icon': 'bi-people',
                    'metadata': {
                        'code': item.code,
                        'level': str(item.level)
                    }
                })
        
        elif config['model'] == 'Subject':
            from apps.academics.models import Subject
            items = Subject.objects.filter(q_object)[:limit]
            for item in items:
                results.append({
                    'id': item.id,
                    'type': 'subject',
                    'title': item.name,
                    'description': f"Code: {item.code}",
                    'url': f"/evals/subject/{item.id}/",
                    'icon': 'bi-book',
                    'metadata': {
                        'code': item.code,
                        'grade': 'All'
                    }
                })
        
        elif config['model'] == 'Invoice':
            from apps.finance.models import Invoice
            items = Invoice.objects.filter(q_object)[:limit]
            for item in items:
                results.append({
                    'id': item.id,
                    'type': 'invoice',
                    'title': f"Invoice #{item.invoice_number}",
                    'description': f"Student: {item.student.user.get_full_name()}",
                    'url': f"/finance/invoices/{item.id}/",
                    'icon': 'bi-receipt',
                    'metadata': {
                        'amount': f"{item.amount}",
                        'status': item.status
                    }
                })
        
        return results


@method_decorator(login_required, name='dispatch')
class SearchSuggestionsAPI(View):
    """
    Get search suggestions for autocomplete
    
    Returns recently searched queries by user
    """
    
    def get(self, request):
        from django.core.cache import cache
        
        # Get from cache or return empty
        key = f'search_history_{request.user.id}'
        history = cache.get(key, [])
        
        return JsonResponse({
            'suggestions': history[-5:]  # Last 5 searches
        })
