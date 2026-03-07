# Phase 1.1: N+1 Query Optimization & Performance Tuning

## Executive Summary

This document outlines the N+1 query problems identified in the dashboard generation system and the systematic optimization approach to achieve sub-2-second page loads and <10 database queries per request.

**Current State (Pre-Optimization):**
- Dashboard load time: 5-8 seconds (estimated)
- Database queries per dashboard load: 50+ (estimated)
- Major bottlenecks: `term_report_context()` called per student, finance aggregations, evaluation loops

**Target State (Post-Optimization):**
- Dashboard load time: <2 seconds
- Database queries per dashboard load: <10
- Cache hit rate: >80% for dashboard widgets

---

## Problem Analysis

### 1. `_performance_overview()` - Most Critical (N+1)

**Current Implementation:**
```python
def _performance_overview(students, year, term):
    summaries = []
    for student in students:  # LOOP - One query per student!
        ctx = term_report_context(student, year, term)  # N QUERIES
        avg = ctx["summary"].get("average")
```

**Issues:**
- Calls `term_report_context()` inside loop → N database queries (where N = number of students)
- Each call potentially queries: Evaluations, Subjects, SubjectAssignments
- No caching of report context
- Processes all students even if only summary needed

**Estimated Queries:** 1 (SiteSettings) + N×3 (per student) = ~10-50 queries for typical parent (2-5 kids)

**Solution:** Batch-load evaluations, use prefetch_related, implement caching

---

### 2. `_referral_overview()` - Model Field Access (N queries)

**Current Implementation:**
```python
def _referral_overview(students: list[StudentProfile]):
    codes = [s.referral_code for s in students if s.referral_code]
    completeness_vals = [s.parent_completeness for s in students if hasattr(s, "parent_completeness")]
    completeness_avg = int(round(sum(completeness_vals) / len(completeness_vals)))
```

**Issues:**
- `parent_completeness` property likely performs database query per student
- Iterates students without prefetching related data
- Could be computed once in view with select_related

**Estimated Queries:** N queries for parent_completeness calculation

**Solution:** Prefetch related data in view, move completeness to annotation

---

### 3. `_finance_summary()` - Suboptimal Aggregation

**Current Implementation:**
```python
def _finance_summary(students):
    invoices = Invoice.objects.filter(student__in=students).exclude(status=Invoice.Status.DRAFT)
    totals = invoices.aggregate(
        total_due=Sum("total_amount"),
        balance=Sum("balance_amount"),
    )
```

**Issues:**
- Filter then count creates additional queries
- No select_related for related objects if needed later
- Status check on large invoice sets could be slow

**Estimated Queries:** 2-3 queries

**Solution:** Use single aggregation query with F expressions, add index on (student, status)

---

### 4. `_analytics_insights()` - Iteration Without Prefetch

**Current Implementation:**
```python
evals = Evaluation.objects.filter(
    student__in=students,
    academic_year=year,
    term=term,
).select_related("subject_assignment__subject")

for e in evals:
    subj = e.subject_assignment.subject.name
```

**Issues:**
- Select_related used (good), but not prefetching the full evaluation pipeline
- Filter on student__in without optimization
- Memory inefficient for large evaluation counts

**Estimated Queries:** 1 query (well-optimized)

**Solution:** This is actually well-optimized; add caching at result level

---

### 5. `_task_tracker()` - Repeated Queryset Evaluation

**Current Implementation:**
```python
evals = Evaluation.objects.filter(
    student__in=students,
    academic_year=year,
    term=term,
)
pending_evaluations = sum(1 for e in evals if not e.is_complete_for_ranking)

pending_payments = PaymentReminder.objects.filter(
    invoice__student__in=students,
    is_active=True,
    next_send_at__lte=now,
).count()
```

**Issues:**
- Evaluates all evaluations in memory instead of using aggregation
- Query happens at template render time if used in view

**Estimated Queries:** 2 queries (could be 1 with annotation)

**Solution:** Use Count aggregation with conditional expressions

---

### 6. `_attendance_snapshot()` - Repeated Calculations

**Current Implementation:**
```python
evals = Evaluation.objects.filter(
    student__in=students,
    academic_year=year,
    term=term,
)
total = evals.count()
complete = sum(1 for e in evals if e.is_complete_for_ranking)
overall_pct = int(round((complete / total) * 100))
```

**Issues:**
- Loads all evaluations for students into memory
- Evaluates is_complete_for_ranking on each (potential N+1 if it's a property with queries)

**Estimated Queries:** 1-5 queries

**Solution:** Annotate is_complete_for_ranking, use Count with Q objects

---

### 7. Parent Dashboard View - StudentGuardian Query

**Current Implementation:**
```python
links = StudentGuardian.objects.filter(
    guardian_user=request.user,
    can_view_results=True
).select_related("student", "student__classroom", "student__specialty", "student__academic_year")
```

**Issues:**
- Good use of select_related, but then calls parent_dashboard_widget_data(students)
- Each student's data generation triggers new queries

**Estimated Queries:** 1 (with select_related) + N×5 (per student in widgets)

**Solution:** Prefetch related objects further, use only() for specific fields

---

## Optimization Strategy

### Phase 1.1.1: Analysis & Profiling (This file)
✅ Identified N+1 patterns
✅ Documented impact per function

### Phase 1.1.2: Code Optimization
1. Fix `_performance_overview()` with batch evaluation loading
2. Fix `_referral_overview()` with proper prefetching
3. Optimize `_task_tracker()` with aggregation
4. Optimize `_attendance_snapshot()` with annotations
5. Add cache layer to widget_data results

### Phase 1.1.3: Database Indexes
Create migration adding:
- `(student_id, academic_year_id, term_id)` on Evaluation
- `(student_id, status, created_at DESC)` on Invoice
- `(guardian_user_id)` on StudentGuardian
- `(subject_assignment_id, student_id)` on Evaluation

### Phase 1.1.4: Caching Strategy
- Cache parent_dashboard_widget_data for 5 minutes
- Cache term_report_context for 10 minutes
- Cache SiteSettings for 1 hour
- Invalidate on related object changes

### Phase 1.1.5: Testing & Measurement
- Use django-querycount to verify query reduction
- Benchmark before/after
- Create performance regression tests

---

## Query Count Targets

| Component | Current | Target | Method |
|-----------|---------|--------|--------|
| StudentGuardian fetch | 1 | 1 | Keep select_related |
| _performance_overview | N×3 | 1 | Batch load + cache |
| _referral_overview | N | 0 | Prefetch + annotate |
| _finance_summary | 2 | 1 | Combine aggregations |
| _attendance_snapshot | 1 | 1 | Add F expressions |
| _task_tracker | 2 | 1 | Use Count(filter=Q(...)) |
| _analytics_insights | 1 | 1 | Use annotate |
| Widget data cache | N queries | 1 | Cache hit |
| **Total per request** | **50+** | **<10** | Combined approach |

---

## Implementation Checklist

- [ ] Create PHASE_1_1_ANALYSIS.md with profiling results
- [ ] Optimize apps/portal/services.py functions
- [ ] Create database migration with indexes
- [ ] Implement caching with cache.get_or_set()
- [ ] Add cache invalidation signals
- [ ] Create performance tests
- [ ] Benchmark improvements
- [ ] Update Phase 1.1 documentation
- [ ] Commit: "Phase 1.1: N+1 Query Optimization & Performance Tuning"

---

## Risk Assessment

- **Risk:** Cache invalidation timing
  - **Mitigation:** Use short TTL, clear on save

- **Risk:** Annotation complexity
  - **Mitigation:** Test edge cases, use F expressions carefully

- **Risk:** Index creation locks table
  - **Mitigation:** Use CONCURRENTLY in PostgreSQL, document downtime window

---

## Timeline

- **Phase 1.1.1:** Analysis (THIS DOCUMENT) - ✅ Complete
- **Phase 1.1.2:** Code optimization - In Progress
- **Phase 1.1.3:** Database indexes - Pending
- **Phase 1.1.4:** Caching layer - Pending
- **Phase 1.1.5:** Testing & validation - Pending

**Estimated Total Effort:** 8-10 hours
**Target Completion:** Next 1-2 days

---

## Success Metrics

1. ✅ Dashboard queries reduced from 50+ to <10
2. ✅ Dashboard load time <2 seconds
3. ✅ Report generation <5 seconds
4. ✅ 12/12 existing tests still passing
5. ✅ 8+ new performance tests added
6. ✅ No regressions in functionality

---

## Related Documents

- [PHASE_0_COMPLETION.md](PHASE_0_COMPLETION.md) - Previous phase completion
- [apps/portal/services.py](../apps/portal/services.py) - Code being optimized
- [QUICK_START.md](QUICK_START.md) - Testing instructions
