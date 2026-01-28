# Code Review: Gaps, Redundancies & Unnecessary Code

## 🔴 CRITICAL GAPS (Missing Functionality)

### 1. **GradingDeadline Model Missing** ⚠️ HIGH PRIORITY
**Location**: `apps/analytics/views.py:323-368`, `apps/portal/services.py:714`, `apps/analytics/services.py:85,473`

**Problem**: 
- Model was deleted in migration `0008_attendancelog_delete_gradingdeadline.py`
- Multiple views/services still reference it with "no-op" comments
- `grading_deadlines` view is completely non-functional
- Management command `send_deadline_reminders.py` will fail

**Impact**: 
- Deadline management feature is broken
- Users can't set grading deadlines
- Reminder system won't work

**Fix Required**:
- Either restore `GradingDeadline` model OR
- Remove all references and implement alternative (e.g., use `SubjectAssignment.deadline_at`)

**Files Affected**:
- `apps/analytics/views.py` (lines 323-368)
- `apps/analytics/services.py` (lines 85, 473)
- `apps/portal/services.py` (line 714)
- `apps/evals/views.py` (lines 1638-1650)
- `apps/analytics/management/commands/send_deadline_reminders.py`

---

### 2. **Duplicate Dashboard Layout Logic** ⚠️ MEDIUM PRIORITY
**Location**: `static/js/dashboard-layout.js` AND `static/js/dashboard-customizer.js`

**Problem**:
- Two separate JavaScript files handling drag-and-drop
- `dashboard-layout.js` uses Sortable.js (better)
- `dashboard-customizer.js` uses native HTML5 drag (redundant)
- Both loaded on same pages, causing potential conflicts
- Duplicate layout saving logic

**Current State**:
- `dashboard-layout.js`: 273 lines, Sortable.js-based, column-aware
- `dashboard-customizer.js`: 477 lines, native drag, settings management

**Recommendation**:
- **Option A**: Merge into single file, use Sortable.js as primary
- **Option B**: Keep `dashboard-customizer.js` only for settings (sidebar, links, variants), remove drag logic
- **Option C**: Remove `dashboard-customizer.js` entirely, move settings to `dashboard-layout.js`

**Files**:
- `static/js/dashboard-layout.js`
- `static/js/dashboard-customizer.js`
- Templates loading both: `teacher/dashboard.html`, `parent/dashboard.html`, `accounts/backend_dashboard.html`, etc.

---

### 3. **Repeated Dashboard Context Setup** ⚠️ MEDIUM PRIORITY
**Location**: Multiple view files

**Problem**: Same 4-5 lines of code repeated in every dashboard view:
```python
dashboard_settings = load_dashboard_layout_settings(request.user, "page_name")
allow_custom_layout = _can_customize(request.user)
dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "page_name"})
widget_meta_json = mark_safe(json.dumps(get_dashboard_widget_metadata()))
```

**Found in**:
- `apps/portal/views.py` (parent dashboard)
- `apps/evals/views.py` (teacher dashboard)
- `apps/finance/views.py` (finance dashboard)
- `apps/analytics/views.py` (analytics dashboard)
- `apps/accounts/views.py` (backend dashboard)

**Fix**: Create a context processor or helper function:
```python
def get_dashboard_context(user, page: str) -> dict:
    return {
        "dashboard_settings": load_dashboard_layout_settings(user, page),
        "allow_custom_layout": _can_customize(user),
        "dashboard_layout_url": reverse("api:dashboard-layout", kwargs={"page": page}),
        "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
    }
```

---

## 🟡 REDUNDANCIES (Duplicate Code)

### 4. **Duplicate Layout Loading Logic**
**Location**: `apps/api/dashboard_layout_api.py` AND `apps/siteconfig/dashboard_views.py`

**Problem**:
- `DashboardLayoutAPI.get()` loads layout (lines 251-278)
- `load_dashboard_layout_settings()` also loads layout (lines 119-132)
- Similar logic for user/role/default fallback

**Recommendation**: Consolidate into shared utility function

---

### 5. **Duplicate Settings Normalization**
**Location**: `apps/siteconfig/dashboard_views.py` AND `apps/api/dashboard_layout_api.py`

**Problem**:
- `_normalize_dashboard_settings()` in `dashboard_views.py` (lines 72-84)
- `_sanitize_layout_settings()` in `dashboard_layout_api.py` (lines 172-187)
- Both do similar sanitization

**Recommendation**: Merge into single function, use in both places

---

### 6. **Repeated Role Checking**
**Location**: Multiple files

**Pattern**: `(getattr(user, "role", "") or "").upper()` appears 10+ times

**Files**:
- `apps/siteconfig/dashboard_views.py` (lines 32, 108, 124)
- `apps/api/dashboard_layout_api.py` (line 243)
- `apps/accounts/views.py` (multiple)

**Fix**: Create helper: `def get_user_role(user) -> str: return (getattr(user, "role", "") or "").upper()`

---

## 🟢 UNNECESSARY / DEAD CODE

### 7. **Unused Imports**
**Location**: Various files

**Examples**:
- `apps/evals/views.py`: Line 1638 imports `GradingDeadline` (model doesn't exist)
- `apps/portal/views.py`: Multiple unused imports (check with `pylint` or `flake8`)

**Recommendation**: Run `pylint` or `flake8` to find all unused imports

---

### 8. **Incomplete URL Pattern**
**Location**: `apps/evals/urls.py:45`

**Problem**: Line 45 has incomplete `path(` statement:
```python
path
```

**Fix**: Complete or remove this line

---

### 9. **Placeholder Comments**
**Location**: Multiple files

**Examples**:
- `apps/academics/scheduling.py:415`: `# TODO: Attempt to redistribute`
- Various "no-op" comments for missing `GradingDeadline`

**Recommendation**: Either implement or remove placeholder code

---

### 10. **Unused Template Scripts**
**Location**: `templates/portal/kb_home.html:308`

**Problem**: Only loads `dashboard-layout.js`, not `dashboard-customizer.js`, but KB page doesn't need drag-and-drop

**Recommendation**: Remove if not needed, or add both for consistency

---

## 📊 SUMMARY STATISTICS

### Code Duplication
- **Dashboard context setup**: 5 files, ~20 lines each = 100 lines duplicated
- **Role checking**: 10+ occurrences = ~30 lines duplicated
- **Layout loading**: 2 implementations = ~50 lines duplicated

### Dead Code
- **GradingDeadline references**: 5 files, ~50 lines of non-functional code
- **Incomplete URL**: 1 file, 1 line
- **Unused imports**: Estimated 10-20 across codebase

### Missing Features
- **GradingDeadline model**: Critical feature broken
- **API endpoints**: Many marked as "NEEDED" in `API_COMPLETE_GUIDE.md`
- **Testing**: Many checkboxes unchecked in implementation docs

---

## 🎯 PRIORITY FIXES

### Immediate (This Week)
1. ✅ Fix `GradingDeadline` issue (restore model OR remove all references)
2. ✅ Consolidate dashboard context setup into helper function
3. ✅ Fix incomplete URL pattern in `apps/evals/urls.py`

### Short-term (Next Week)
4. ✅ Merge or remove duplicate drag-and-drop JavaScript
5. ✅ Consolidate layout loading/sanitization functions
6. ✅ Create `get_user_role()` helper function
7. ✅ Remove unused imports (run linter)

### Medium-term (Next Month)
8. ✅ Complete TODO items or remove placeholders
9. ✅ Implement missing API endpoints
10. ✅ Add missing tests

---

## 🔧 QUICK WINS (Easy Fixes)

1. **Create helper function** (5 minutes):
   ```python
   # apps/accounts/utils.py
   def get_user_role(user) -> str:
       return (getattr(user, "role", "") or "").upper()
   ```

2. **Fix incomplete URL** (1 minute):
   ```python
   # apps/evals/urls.py:45 - Remove or complete
   ```

3. **Remove unused import** (1 minute):
   ```python
   # apps/evals/views.py:1638 - Remove GradingDeadline import
   ```

4. **Consolidate dashboard context** (30 minutes):
   - Create `get_dashboard_context()` helper
   - Update 5 view files to use it

---

## 📝 NOTES

- Most redundancies are in dashboard/layout code (recent feature)
- Dead code mostly from deleted `GradingDeadline` model
- No major architectural issues found
- Code quality is generally good, just needs cleanup

---

**Generated**: 2026-01-28  
**Reviewer**: AI Code Analysis  
**Status**: Ready for Action
