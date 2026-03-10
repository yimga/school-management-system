# Phase 1.2.9 Quick Reference Guide

## What is Phase 1.2.9?

Compliance Analytics & Dashboards - Extends Phase 1.2.8 (Compliance & Legal Framework) with real-time analytics, dashboards, and API endpoints for monitoring compliance across all regions.

## Key Components

### 1. ComplianceAnalytics Class
Location: `apps/compliance/analytics.py`
- Provides 9 analytics methods
- All methods return JSON-serializable data
- No side effects - pure analytics engine

### 2. Dashboard Views
Location: `apps/compliance/views.py`
- 1 main dashboard view (HTML template)
- 9 REST API endpoints
- All endpoints require login
- JSON response format

### 3. URL Configuration
Location: `apps/compliance/urls.py`
- Namespace: 'compliance'
- Routes all dashboard and API endpoints
- Prefix: `/compliance/`

### 4. Test Suite
Location: `apps/compliance/tests/test_analytics.py`
- 12 comprehensive tests
- 100% pass rate
- Tests all analytics methods and edge cases

## Quick Start

### Installation
```bash
# Migrations already applied during Phase 1.2.8
# No additional setup required
```

### Using Analytics Directly

```python
from apps.compliance.analytics import ComplianceAnalytics

analytics = ComplianceAnalytics()

# Get overview
overview = analytics.get_compliance_overview()
print(f"Completion: {overview['completion_percentage']}%")

# Get regional metrics
metrics = analytics.get_regional_metrics()
for region_code, data in metrics.items():
    print(f"{region_code}: {data['compliance_score']}%")

# Get critical items
critical = analytics.get_critical_items()
for item in critical:
    print(f"{item['severity']}: {item['description']}")
```

### Using Dashboard Views

```python
# In your URL configuration
from django.urls import path, include

urlpatterns = [
    path('compliance/', include('apps.compliance.urls')),
]

# Access dashboard
# GET /compliance/dashboard/
```

### Using API Endpoints

```bash
# Overview
curl http://localhost:8000/compliance/api/overview/

# Regional metrics
curl http://localhost:8000/compliance/api/regional-metrics/

# Check statistics
curl http://localhost:8000/compliance/api/check-statistics/

# Audit log summary (last 30 days)
curl http://localhost:8000/compliance/api/audit-log-summary/?days=30

# Document status
curl http://localhost:8000/compliance/api/document-status/

# Timeline data (last 90 days)
curl http://localhost:8000/compliance/api/timeline-data/?days=90

# Regional comparison
curl http://localhost:8000/compliance/api/regional-comparison/

# Critical items
curl http://localhost:8000/compliance/api/critical-items/
```

## API Endpoints Reference

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `/dashboard/` | GET | Required | HTML |
| `/api/overview/` | GET | Required | JSON - Overview metrics |
| `/api/regional-metrics/` | GET | Required | JSON - Regional breakdown |
| `/api/check-statistics/` | GET | Required | JSON - Check stats |
| `/api/audit-log-summary/` | GET | Required | JSON - Audit breakdown |
| `/api/document-status/` | GET | Required | JSON - Document tracking |
| `/api/timeline-data/` | GET | Required | JSON - Historical data |
| `/api/regional-comparison/` | GET | Required | JSON - Ranked regions |
| `/api/critical-items/` | GET | Required | JSON - Critical items |

## Analytics Methods Explained

### get_compliance_overview()
**Purpose:** High-level compliance status
**Returns:**
- total_regions, total_requirements
- active, pending, archived, completed counts
- completion_percentage, on_time_percentage
- at_risk_count

**Use Case:** Dashboard header widget, KPIs

### get_regional_metrics()
**Purpose:** Per-region compliance breakdown
**Returns:** Dict with region codes as keys
- region_name, total_requirements
- completion_percentage, compliance_score
- overdue_count, recent_checks

**Use Case:** Regional comparison table, details view

### get_check_statistics()
**Purpose:** Compliance check performance
**Returns:**
- total_checks, passed, failed, warnings
- pass_rate, fail_rate, warning_rate
- average_issues_per_check
- checks_by_type breakdown

**Use Case:** Quality metrics, trend analysis

### get_audit_log_summary(days)
**Purpose:** Audit trail analysis
**Returns:**
- period_days, total_actions
- action_breakdown dict
- severity_breakdown dict

**Use Case:** Activity reports, compliance audit

### get_document_status()
**Purpose:** Legal document tracking
**Returns:**
- total_documents, total_active_documents
- by_type breakdown (privacy_policy, etc.)
- by_language breakdown
- expiring_soon, expired counts

**Use Case:** Document management, expiration alerts

### get_timeline_data(days)
**Purpose:** Historical compliance trends
**Returns:** Array of daily data
- date (YYYY-MM-DD format)
- checks_performed, requirements_created
- documents_created, compliance_issues

**Use Case:** Line charts, trend visualization

### get_regional_comparison()
**Purpose:** Ranked regional performance
**Returns:** Array of regions sorted by completion %
- region_code, region_name
- requirement_completion %, compliance_score
- check_pass_rate, rank, overdue_items

**Use Case:** Leaderboard, performance comparison

### get_critical_items()
**Purpose:** High-priority alerts
**Returns:** Array of critical items sorted by severity
- type (overdue_requirement, failed_check, expired_document)
- region, description
- severity (low, medium, high, critical)
- created_at, action_required

**Use Case:** Alert dashboard, priority widget

## Testing

### Run All Compliance Tests
```bash
python manage.py test apps.compliance.tests -v 2
```

### Run Only Phase 1.2.9 Tests
```bash
python manage.py test apps.compliance.tests.test_analytics -v 2
```

### Run Specific Test
```bash
python manage.py test apps.compliance.tests.test_analytics.ComplianceAnalyticsTestCase.test_compliance_overview_with_data -v 2
```

### Check Test Coverage
```bash
python manage.py test apps.compliance.tests --cov=apps.compliance --cov-report=html
```

## Database Queries

### Get Compliance Overview
```python
from apps.compliance.models import RegionalComplianceRequirement
from django.db.models import Count

active_count = RegionalComplianceRequirement.objects.filter(status='active').count()
pending_count = RegionalComplianceRequirement.objects.filter(status='pending').count()
```

### Get Regional Metrics
```python
metrics = RegionalComplianceRequirement.objects.values('region__code').annotate(
    count=Count('id'),
    active=Count('id', filter=Q(status='active'))
)
```

### Get Check Statistics
```python
from apps.compliance.models import ComplianceCheck
from django.db.models import Q, Avg

stats = {
    'passed': ComplianceCheck.objects.filter(status='pass').count(),
    'failed': ComplianceCheck.objects.filter(status='fail').count(),
    'avg_issues': ComplianceCheck.objects.aggregate(Avg('issues_found'))['issues_found__avg']
}
```

## Performance Tips

### Cache Analytics Results
```python
from django.views.decorators.cache import cache_page

@cache_page(60 * 5)  # Cache for 5 minutes
def api_overview(request):
    analytics = ComplianceAnalytics()
    return JsonResponse(analytics.get_compliance_overview())
```

### Optimize Timeline Queries
```python
# Limit timeline to specific date range
timeline = analytics.get_timeline_data(days=30)  # Faster than 90 days
```

### Batch Regional Queries
```python
# Get metrics for all regions in one query
from django.db.models import Prefetch
regions = RegionConfig.objects.prefetch_related(
    Prefetch('regional_compliance_requirements')
)
```

## Common Issues & Solutions

### Issue: API returns 403 Forbidden
**Solution:** Ensure user is authenticated
```python
@login_required
def api_view(request):
    ...
```

### Issue: Empty timeline data
**Solution:** Check ComplianceCheck.check_date is set
```bash
# Verify data exists
python manage.py shell
>>> from apps.compliance.models import ComplianceCheck
>>> ComplianceCheck.objects.filter(check_date__gte='2026-01-22').count()
```

### Issue: Regional metrics shows 0%
**Solution:** Verify requirements have status='active'
```bash
>>> from apps.compliance.models import RegionalComplianceRequirement
>>> RegionalComplianceRequirement.objects.filter(status='active').count()
```

### Issue: Critical items not appearing
**Solution:** Check for overdue/failed/expired items
```bash
# Check for overdue requirements
>>> from django.utils import timezone
>>> from datetime import timedelta
>>> past = timezone.now().date() - timedelta(days=5)
>>> RegionalComplianceRequirement.objects.filter(deadline__lt=past).count()
```

## Extending Phase 1.2.9

### Add Custom Analytics Method
```python
# In apps/compliance/analytics.py
class ComplianceAnalytics:
    def get_custom_metric(self):
        # Your custom logic here
        return {
            'metric_name': 'value',
        }
```

### Add Custom API Endpoint
```python
# In apps/compliance/views.py
class CustomMetricAPI(View):
    @method_decorator(login_required)
    def get(self, request):
        analytics = ComplianceAnalytics()
        data = analytics.get_custom_metric()
        return JsonResponse(data)

# In apps/compliance/urls.py
path('api/custom-metric/', CustomMetricAPI.as_view()),
```

### Add Custom Dashboard Widget
```html
<!-- In compliance/dashboard.html -->
<div class="dashboard-widget">
    <h3>Custom Widget</h3>
    <p>Custom data: {{ custom_data }}</p>
</div>
```

## Documentation

- Full documentation: `docs/PHASE_1_2_9_ANALYTICS_DASHBOARDS.md`
- Phase 1.2.8 documentation: `docs/PHASE_1_2_8_COMPLIANCE_LEGAL.md`
- Project status: `PROJECT_STATUS.md`

## Support

For questions:
1. Check documentation files
2. Review test cases for usage examples
3. Check git commit messages
4. Admin interface: `/admin/compliance/`

---

Quick Reference Version: 1.0
Last Updated: 2026-01-22
Status: Complete and Production Ready
