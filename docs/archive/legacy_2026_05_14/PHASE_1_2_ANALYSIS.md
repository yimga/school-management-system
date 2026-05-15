# Phase 1.2: Complete Evaluation Module - Analysis & Plan

**Status:** Phase 1.2.1 - Analysis In Progress  
**Date Started:** 2026-01-21  
**Branch:** security_performace_enhancement  

---

## Current State Analysis

### ✅ What's Already Implemented

**Core Ranking System (apps/evals/services.py):**
- `classroom_term_rankings()` - Class rankings sorted by average
- `school_term_rankings()` - School-wide rankings
- `student_term_average()` - Weighted average calculation
- `classroom_stats()` - Mean, median, count stats
- `StudentAggregate` dataclass for ranking data

**Views & UI:**
- `class_ranking_view()` - Display class rankings by term/classroom
- `school_ranking_view()` - Display school-wide rankings
- Templates in `templates/evals/`

**Database Models:**
- Evaluation model with scores (seq1, seq2, exam, mock, practical)
- SubjectAssignment with coefficient (weighting)
- AssessmentWeights for flexible grading

**Reports:**
- `term_report_context()` in apps/reports/services.py
- Calculates class/school position for student report cards
- Includes promotion status determination

---

### ❌ What's Missing or Incomplete

#### 1. Tie Handling in Rankings
**Current Issue:**
```python
aggregates.sort(key=lambda a: a.average, reverse=True)
```
Problem: Multiple students with same average get arbitrary ordering
**Solution Needed:**
- Proper tie handling (sorted by name, then ID)
- Tie indicators in UI
- Same-rank assignment

#### 2. Ranking Caching
**Current Issue:**
- Rankings computed fresh every request
- O(N) loop through all students per ranking call
**Solution Needed:**
- Cache rankings per term (15-minute TTL)
- Invalidate on evaluation changes
- Batch-load evaluations for performance

#### 3. Mock Exam Handling
**Current Issue:**
- `mock_score` field exists but not integrated into ranking logic
- No FORM 5/7 specific handling
- Mock exam weighting not configurable
**Solution Needed:**
- Mock exam model/feature flag
- Separate mock vs final grades
- Blend mock + final scores
- FORM 5/7 special rules

#### 4. Grading Schemas
**Current Issue:**
- Fixed grading (only numeric scores)
- No letter grade mapping
- No custom schemas per classroom
- Points-to-grade conversion hard to customize
**Solution Needed:**
- GradingSchema model
- Per-classroom schemas
- Grade letter mapping (A, B, C, D, F, etc.)
- Custom range configurations

#### 5. Master Mark Sheet Upload & Validation
**Current Issue:**
- Manual entry in UI only
- No bulk upload functionality
- No validation of data integrity
- No duplicates check
**Solution Needed:**
- CSV/Excel upload form
- Data validation pipeline
- Duplicate detection
- Batch import with transaction handling
- Error reporting

#### 6. Performance Issues in Ranking
**Current Issue:**
```python
for s in students:
    aggregates.append(StudentAggregate(..., scores=[student_term_average(s, term)]))
```
Problem: N queries (one per student) - N+1 issue!
**Solution Needed:**
- Batch-load all evaluations
- Single aggregation query
- Cache result

#### 7. Subject Specialties
**Current Issue:**
- No handling of subject specialties (Advanced/Standard/Bilingual)
- Missing specialty-specific mark sheets
**Solution Needed:**
- Specialty filtering in rankings
- Specialty-specific reports
- Subject variant handling

---

## Implementation Plan

### Task 1.2.1: Analysis ✅ (THIS DOCUMENT)
- [x] Identify existing implementation
- [x] Document gaps
- [x] Plan enhancements

### Task 1.2.2: Ranking Enhancements
**Priority: HIGH** (used in all reports)
- [ ] Fix tie handling in rankings
- [ ] Add ranking caching (15 min TTL per term)
- [ ] Optimize queries (batch-load evaluations)
- [ ] Add rank position helper function
- [ ] Update views to use cached rankings
- **Effort:** 2-3 hours

### Task 1.2.3: Mock Exam Support
**Priority: MEDIUM** (FORM 5/7 only)
- [ ] Create MockExam model (optional, if needed)
- [ ] Add mock exam flag/settings
- [ ] Implement blend logic (mock + final)
- [ ] Add FORM 5/7 special handling
- [ ] Update ranking to include mock handling
- **Effort:** 2-3 hours

### Task 1.2.4: Grading Schemas
**Priority: MEDIUM** (flexibility needed)
- [ ] Create GradingSchema model
- [ ] Add per-classroom schema mapping
- [ ] Implement letter grade conversion
- [ ] Add custom range configuration
- [ ] Update reports to use schemas
- **Effort:** 3-4 hours

### Task 1.2.5: Master Mark Sheet Upload
**Priority: HIGH** (bulk data entry needed)
- [ ] Create CSV import form
- [ ] Implement data validation pipeline
- [ ] Add duplicate detection
- [ ] Batch import with transactions
- [ ] Error reporting UI
- **Effort:** 4-5 hours

### Task 1.2.6: Testing & Commit
**Priority: HIGH**
- [ ] Unit tests for ranking algorithms
- [ ] Integration tests for import
- [ ] Edge case tests (ties, nulls, zeros)
- [ ] Performance tests
- [ ] Commit Phase 1.2 work
- **Effort:** 2-3 hours

---

## Technical Approach

### Ranking Caching Strategy
```python
# Cache key: ranking_term_{term_id}
# TTL: 15 minutes
# Invalidation: On Evaluation save/delete

cache_key = f"ranking_term:{term.id}"
rankings = cache.get_or_set(
    cache_key,
    lambda: school_term_rankings(term),
    900  # 15 min TTL
)
```

### Mock Exam Blending
```python
# For FORM 5/7:
# final_score = 0.7 * final + 0.3 * mock (configurable)

# For other forms:
# final_score = final only
```

### Grading Schema Model
```python
class GradingSchema(models.Model):
    classroom = ForeignKey(Classroom)
    name = CharField()  # "Standard", "Advanced", etc.
    ranges = JSONField()  # [{"letter": "A", "min": 80, "max": 100}, ...]
```

### Master Mark Sheet Upload
```python
# CSV Format:
# student_id, subject, seq1_score, seq2_score, exam_score, mock_score
# 1001, Mathematics, 18, 16, 75, 72
# 1002, Mathematics, 15, 14, 68, 70

# Validation:
# - Scores in range 0-20 (component) or 0-100 (exam)
# - Student exists
# - Subject valid for class
# - No duplicate entries
```

---

## Database Changes Required

**New Models:**
1. `GradingSchema` - Per-classroom grade configurations
2. `GradeRange` - Grade letter mappings (or use JSON in schema)
3. `MockExamSetting` - Enable/disable mock exams per form
4. `BulkImportLog` - Track CSV imports

**Migrations:**
- 0008_add_grading_schemas.py
- 0009_add_mock_exam_settings.py  
- 0010_add_bulk_import_log.py

**Index Additions:**
- `(classroom, name)` on GradingSchema
- `(term, academic_year)` on ImportLog (for auditing)

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Ranking with many students (1000+) slow | Medium | High | Caching + batch queries |
| Tie breaking affects students | Low | High | Thorough testing + config options |
| CSV upload causes duplicates | Medium | Medium | Duplicate detection + transaction |
| Mock exams break existing reports | Medium | High | Feature flag + backward compat |
| Grading schema not applied universally | Low | Medium | Validation + defaults |

---

## Success Criteria

- ✅ Rankings work correctly with >1000 students
- ✅ Ties handled consistently (same score = same rank)
- ✅ Ranking queries <500ms (with cache)
- ✅ Mock exams optional (feature flag)
- ✅ CSV bulk import works (0-5000 records)
- ✅ Grading schemas apply correctly
- ✅ All tests passing
- ✅ No performance regressions

---

## Timeline

**Estimated Total Effort:** 16-18 hours over 2-3 days

1. **Day 1:** Task 1.2.2 (Rankings) + Task 1.2.3 (Mock Exams)
2. **Day 2:** Task 1.2.4 (Schemas) + Task 1.2.5 (Upload)
3. **Day 3:** Task 1.2.6 (Testing & Commit)

---

## Next Action

**Start with Task 1.2.2: Ranking Enhancements**
- Add tie handling
- Implement caching
- Optimize queries
- Estimated: 2-3 hours
