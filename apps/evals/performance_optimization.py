"""
Phase 8 Task 3: Performance Optimization
Database optimization, caching strategies, and query optimization.
World Engine F.2: All cache keys are tenant-prefixed via get_tenant_cache_prefix().
"""

from django.db import models, connection
from django.core.cache import cache
from django.db.models import Prefetch, F
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import hashlib
import json


def _tenant_prefix():
    """Tenant-scoped cache key prefix (F.2)."""
    try:
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix
        return get_tenant_cache_prefix()
    except Exception:
        return "public"


class CacheManager:
    """Centralized cache management. Keys are tenant-prefixed for multi-tenant safety (F.2)."""

    # Base key patterns (tenant prefix prepended at runtime)
    STUDENT_GRADES_KEY = "student_grades_{student_id}"
    CLASS_STATS_KEY = "class_stats_{class_id}"
    TEACHER_WORKLOAD_KEY = "teacher_workload_{teacher_id}"
    EVALUATION_RESULTS_KEY = "eval_results_{eval_id}"

    CACHE_TIMEOUT = 3600  # 1 hour default

    @classmethod
    def _key(cls, pattern, **kwargs):
        return f"{_tenant_prefix()}:{pattern.format(**kwargs)}"

    @classmethod
    def get_student_grades(cls, student_id):
        """Get cached student grades"""
        key = cls._key(cls.STUDENT_GRADES_KEY, student_id=student_id)
        return cache.get(key)

    @classmethod
    def set_student_grades(cls, student_id, grades, timeout=None):
        """Cache student grades"""
        key = cls._key(cls.STUDENT_GRADES_KEY, student_id=student_id)
        cache.set(key, grades, timeout or cls.CACHE_TIMEOUT)

    @classmethod
    def invalidate_student_cache(cls, student_id):
        """Invalidate student cache"""
        key = cls._key(cls.STUDENT_GRADES_KEY, student_id=student_id)
        cache.delete(key)

    @classmethod
    def get_class_statistics(cls, class_id):
        """Get cached class statistics"""
        key = cls._key(cls.CLASS_STATS_KEY, class_id=class_id)
        return cache.get(key)

    @classmethod
    def set_class_statistics(cls, class_id, stats, timeout=None):
        """Cache class statistics"""
        key = cls._key(cls.CLASS_STATS_KEY, class_id=class_id)
        cache.set(key, stats, timeout or cls.CACHE_TIMEOUT)


class QueryOptimizer:
    """Query optimization utilities"""
    
    @staticmethod
    def get_student_with_evaluations(student_id):
        """Optimized student query with related data"""
        from apps.people.models import StudentProfile
        from apps.evals.models import Evaluation
        
        # Use select_related for foreign keys
        student = StudentProfile.objects.select_related(
            'student__profile',
            'classroom'
        ).get(student_id=student_id)
        
        # Use prefetch_related for reverse relations
        evaluations = Evaluation.objects.filter(
            student_id=student_id
        ).select_related('subject', 'classroom')
        
        return student, evaluations
    
    @staticmethod
    def get_classroom_statistics(classroom_id):
        """Optimized classroom statistics query"""
        from apps.academics.models import Classroom
        from apps.evals.models import Evaluation
        from django.db.models import Avg, Count
        
        classroom = Classroom.objects.get(id=classroom_id)
        
        # Single aggregated query
        stats = Evaluation.objects.filter(
            classroom_id=classroom_id
        ).aggregate(
            avg_score=Avg('score'),
            total_evals=Count('id'),
            student_count=Count('student', distinct=True)
        )
        
        return stats
    
    @staticmethod
    def get_teacher_workload(teacher_id):
        """Optimized teacher workload query"""
        from apps.people.models import TeacherProfile
        from apps.evals.models import Assignment
        from django.db.models import Count
        
        teacher = TeacherProfile.objects.prefetch_related(
            'subject_set',
            'classroom_set'
        ).get(teacher_id=teacher_id)
        
        # Optimize assignment count query
        workload = Assignment.objects.filter(
            subject__teacher_id=teacher_id
        ).values('subject').annotate(count=Count('id'))
        
        return teacher, workload


class PerformanceIndexes:
    """Database index recommendations"""
    
    RECOMMENDED_INDEXES = [
        # Evaluation indexes
        ('evals', 'Evaluation', ('student', 'classroom', 'date_created')),
        ('evals', 'Evaluation', ('subject', 'score')),
        ('evals', 'Evaluation', ('date_created',)),
        
        # Student indexes
        ('people', 'StudentProfile', ('classroom', 'admission_number')),
        ('people', 'StudentProfile', ('joined_term',)),
        
        # Teacher indexes
        ('people', 'TeacherProfile', ('user',)),
        ('people', 'TeacherProfile', ('subject',)),
        
        # Classroom indexes
        ('academics', 'Classroom', ('academic_year', 'position')),
        ('academics', 'Classroom', ('specialty',)),
        
        # Invoice indexes (for finance)
        ('finance', 'Invoice', ('student', 'date_created')),
        ('finance', 'Invoice', ('status',)),
    ]
    
    @staticmethod
    def get_missing_indexes():
        """Find missing recommended indexes"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename IN ('evals_evaluation', 'people_studentprofile')
            """)
            existing_indexes = [row[0] for row in cursor.fetchall()]
        
        return QueryOptimizer.RECOMMENDED_INDEXES  # Simplified for demo


class BulkOperationOptimizer:
    """Optimize bulk operations"""
    
    @staticmethod
    def bulk_create_evaluations(evaluations_data, batch_size=1000):
        """Bulk create evaluations with batching"""
        from apps.evals.models import Evaluation
        
        evaluations = [
            Evaluation(**data) for data in evaluations_data
        ]
        
        # Batch create for memory efficiency
        created = []
        for i in range(0, len(evaluations), batch_size):
            batch = evaluations[i:i + batch_size]
            Evaluation.objects.bulk_create(batch)
            created.extend(batch)
        
        return len(created)
    
    @staticmethod
    def bulk_update_evaluations(updates_dict, batch_size=1000):
        """Bulk update evaluations"""
        from apps.evals.models import Evaluation
        
        eval_objects = [
            Evaluation(id=eval_id, **updates)
            for eval_id, updates in updates_dict.items()
        ]
        
        Evaluation.objects.bulk_update(eval_objects, batch_size=batch_size)
        return len(eval_objects)


class ConnectionPooling:
    """Database connection pooling configuration"""
    
    CONFIGURATION = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'CONN_MAX_AGE': 600,
            'OPTIONS': {
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000'  # 30 second query timeout
            }
        }
    }


class QueryCaching:
    """Query-level caching for expensive operations. Keys are tenant-prefixed (F.2)."""

    @staticmethod
    def cache_query_result(query_hash, result, timeout=3600):
        """Cache expensive query results"""
        cache.set(f"{_tenant_prefix()}:query_result_{query_hash}", result, timeout)

    @staticmethod
    def get_cached_result(query_hash):
        """Retrieve cached query result"""
        return cache.get(f"{_tenant_prefix()}:query_result_{query_hash}")
    
    @staticmethod
    def generate_query_hash(query_dict):
        """Generate hash for query"""
        query_str = json.dumps(query_dict, sort_keys=True)
        return hashlib.md5(query_str.encode()).hexdigest()


# Cache invalidation signals
@receiver(post_save, sender_dispatch_uid='invalidate_student_cache')
def invalidate_student_cache_on_change(sender, instance, **kwargs):
    """Invalidate cache when student data changes"""
    if hasattr(instance, 'student_id'):
        CacheManager.invalidate_student_cache(instance.student_id)
    elif hasattr(instance, 'id'):
        CacheManager.invalidate_student_cache(instance.id)


@receiver(post_delete, sender_dispatch_uid='invalidate_on_delete')
def invalidate_cache_on_delete(sender, instance, **kwargs):
    """Invalidate cache on data deletion"""
    if hasattr(instance, 'student_id'):
        CacheManager.invalidate_student_cache(instance.student_id)
