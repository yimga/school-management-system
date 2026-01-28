# Frontend vs Backend - Quick Action Items

**Date:** January 28, 2026  
**Branch:** `backend_vs_frontend`

---

## 🎯 IMMEDIATE PRIORITIES

### 1. ❌ CRITICAL: React Components Not Integrated
**Problem:** React components exist in `/frontend/components/` but are NOT used in Django templates.

**Files to Check:**
- `frontend/components/StudentCrudForm.jsx` ✅ Created
- `frontend/components/TeacherCrudForm.jsx` ✅ Created
- `frontend/components/GroupManagementUI.jsx` ✅ Created

**Action Required:**
- [ ] Set up React build process (webpack/vite)
- [ ] Create React app entry point
- [ ] Integrate into `templates/accounts/backend_dashboard.html`
- [ ] Replace Django forms with React components

**Impact:** HIGH - Frontend orchestration cannot work without this

---

### 2. ❌ CRITICAL: No State Management
**Problem:** Only local `useState`, no centralized state.

**Action Required:**
- [ ] Install `@tanstack/react-query`
- [ ] Create query hooks:
  - `frontend/hooks/useStudents.js`
  - `frontend/hooks/useTeachers.js`
  - `frontend/hooks/useSessionClaims.js`
- [ ] Implement caching and optimistic updates

**Impact:** HIGH - No data caching, multiple unnecessary API calls

---

### 3. ❌ CRITICAL: Real-Time Sync Not Connected
**Problem:** WebSocket components exist but use placeholder URLs.

**Files:**
- `frontend/components/StudentRealtimeSync.jsx` (line 10: `wss://your-backend-domain/ws/`)
- `frontend/components/ClassroomRealtimeSync.jsx` (line 10: `wss://your-backend-domain/ws/`)

**Action Required:**
- [ ] Install Django Channels
- [ ] Create WebSocket consumers (`apps/api/consumers.py`)
- [ ] Set up routing (`config/routing.py`)
- [ ] Update WebSocket URLs in React components

**Impact:** MEDIUM - No real-time updates when data changes

---

### 4. ❌ HIGH: Teacher Onboarding Missing
**Problem:** Teachers created only via Django admin.

**Action Required:**
- [ ] Create `templates/teacher/onboarding_wizard.html` (similar to parent wizard)
- [ ] Create `apps/portal/forms.py` → `TeacherOnboardingForm`
- [ ] Add view: `apps/portal/views.py` → `teacher_onboarding_wizard()`
- [ ] Add URL: `apps/portal/urls.py`

**Impact:** HIGH - Teachers cannot self-register

---

### 5. ❌ HIGH: Student Onboarding Missing
**Problem:** Students created only via Django admin.

**Action Required:**
- [ ] Create `templates/student/onboarding_wizard.html`
- [ ] Create `apps/portal/forms.py` → `StudentOnboardingForm`
- [ ] Add view: `apps/portal/views.py` → `student_onboarding_wizard()`
- [ ] Integrate payment APIs
- [ ] Add document upload

**Impact:** HIGH - Students cannot pre-register

---

## ✅ WHAT'S WORKING WELL

### Backend Dashboard ✅
- System statistics display
- Admin operations accessible
- API endpoints functional
- **Location:** `/admin/dashboard/`

### Frontend Dashboard ✅
- Parent dashboard functional
- Teacher dashboard functional
- Parent onboarding wizard ✅ COMPLETE
- Mobile-responsive design ✅

### API Layer ✅
- Entity CRUD endpoints (`/api/entities/students/`, etc.)
- RBAC implemented
- Bulk operations available
- Session claims API

---

## 🔧 QUICK WINS (Can Do Now)

### 1. Add Field Metadata API
**File:** `apps/api/config_api.py` (create new)
```python
class EntityFieldConfigAPI(APIView):
    def get(self, request, entity_type):
        # Return field metadata for dynamic forms
        return Response({...})
```
**URL:** `/api/config/entities/<entity_type>/fields/`

### 2. Create Dynamic Form Component
**File:** `frontend/components/DynamicForm.jsx` (create new)
- Fetches field config from API
- Renders form dynamically
- Uses Zod for validation

### 3. Add Mobile Money to Parent Wizard
**File:** `templates/parent/link_child_wizard.html`
- Add payment step (Step 4)
- Integrate existing payment APIs
- Add verification step

---

## 📋 TESTING CHECKLIST

### Parent Onboarding ✅
- [x] Wizard works end-to-end
- [x] Mobile-friendly
- [x] Session persistence
- [ ] Payment integration (missing)
- [ ] Document upload (missing)

### Teacher Onboarding ❌
- [ ] Wizard exists (NO)
- [ ] Self-service registration (NO)
- [ ] Subject assignment (NO)

### Student Onboarding ❌
- [ ] Pre-registration portal (NO)
- [ ] Document upload (NO)
- [ ] Payment integration (NO)

---

## 🚀 RECOMMENDED NEXT STEPS

1. **Start with React Integration** (Highest Impact)
   - Set up build process
   - Integrate one component (e.g., StudentCrudForm)
   - Test end-to-end

2. **Add State Management** (High Impact)
   - Install TanStack Query
   - Create one hook (e.g., useStudents)
   - Replace fetch calls with hooks

3. **Create Teacher Onboarding** (High Priority)
   - Copy parent wizard structure
   - Adapt for teacher fields
   - Test workflow

4. **Create Student Onboarding** (High Priority)
   - Create pre-registration portal
   - Add payment step
   - Add document upload

---

## 📊 IMPLEMENTATION STATUS

| Feature | Status | Priority | Effort |
|---------|--------|----------|--------|
| React Integration | ❌ Missing | CRITICAL | High |
| State Management | ❌ Missing | CRITICAL | Medium |
| Real-Time Sync | ❌ Missing | MEDIUM | High |
| Teacher Onboarding | ❌ Missing | HIGH | Medium |
| Student Onboarding | ❌ Missing | HIGH | High |
| Dynamic Forms | ❌ Missing | MEDIUM | Medium |
| Mobile Money Integration | ⚠️ Partial | MEDIUM | Low |
| Offline Support | ❌ Missing | LOW | High |

---

**Ready to proceed with implementation?** Start with React Integration or Teacher Onboarding based on your priorities.
