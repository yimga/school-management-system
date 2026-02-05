# API Audit: API_COMPLETE_GUIDE.md vs Implemented Endpoints

**Purpose**: Audit implemented API endpoints against the guide; note gaps and permission alignment (Master Plan Phase 5.2).

## Implemented endpoints (from codebase)

### Under `apps/api/urls.py` (prefix `/api/`)

| Guide / Area        | Implemented | Notes |
|---------------------|-------------|--------|
| **Auth**            |             |        |
| JWT token           | ✅ `POST /api/auth/token/` | TokenObtainPairView |
| JWT refresh         | ✅ `POST /api/auth/token/refresh/` | TokenRefreshView |
| Profile             | ✅ `GET /api/auth/profile/` | ProfileView – current user profile for mobile/frontend |
| Session claims      | ✅ `GET /api/session/claims/` | SessionClaimsView |
| **Dashboards**      |             |        |
| Admin dashboard     | ✅ `GET /api/dashboard/admin/` | AdminDashboardOverviewAPI |
| Teacher dashboard   | ✅ `GET /api/dashboard/teacher/` | TeacherDashboardAPI |
| Parent dashboard    | ✅ `GET /api/dashboard/parent/` | ParentDashboardAPI |
| Student dashboard   | ✅ `GET /api/dashboard/student/` | StudentDashboardAPI |
| Financial dashboard | ✅ `GET /api/dashboard/financial/` | FinancialDashboardAPI |
| Academic dashboard  | ✅ `GET /api/dashboard/academic/` | AcademicDashboardAPI |
| Dashboard layout    | ✅ `GET /api/dashboard/layout/<page>/` | DashboardLayoutAPI |
| **Entities**        |             |        |
| Students            | ✅ ViewSet ` /api/entities/students/` | StudentProfileViewSet |
| Teachers            | ✅ ViewSet ` /api/entities/teachers/` | TeacherProfileViewSet |
| Guardians           | ✅ ViewSet ` /api/entities/guardians/` | StudentGuardianViewSet |
| Classrooms          | ✅ ViewSet ` /api/entities/classrooms/` | ClassroomViewSet |
| Teacher roster      | ✅ `GET /api/entities/teacher-roster/` | TeacherRosterView |
| **Mobile / other**  |             |        |
| Devices             | ✅ ViewSet ` /api/devices/` | MobileDeviceViewSet |
| Push notifications  | ✅ ViewSet ` /api/push-notifications/` | PushNotificationViewSet |
| Offline sync        | ✅ ViewSet ` /api/sync/` | OfflineSyncViewSet |
| Notifications       | ✅ ViewSet ` /api/notifications/` | NotificationViewSet |
| **Search**          |             |        |
| Global search       | ✅ `GET /api/search/` | GlobalSearchAPI |
| Search suggestions  | ✅ `GET /api/search/suggestions/` | SearchSuggestionsAPI |

### Under `config/urls.py` (other API paths)

- `GET /api/schema/`, `GET /api/schema/ui/` – schema (RBAC-protected)
- `GET /api/health/`, observability, AI copilot, dashboard charts, etc.

### Finance API base path and parent-scoped endpoints

- **Under `/api/`**: Financial dashboard only – `GET /api/dashboard/financial/` (FinancialDashboardAPI in `apps/api/dashboard_api.py`). RBAC: ADMIN, BURSAR, LEADERSHIP, staff.
- **Finance app** (`apps/finance/`): Web UI and actions are under URL prefix **`/finance/`** (e.g. `/finance/`, `/finance/invoices/`, `/finance/payments/`). See `config/urls.py` and `apps/finance/urls.py`.
- **Finance API module** (`apps/finance/api_views.py`): Defines `InvoiceViewSet`, `PaymentViewSet`, and summary/analytics views. These are **not** currently mounted in the main `/api/` router; they are available for future inclusion (e.g. under `/api/invoices/`, `/api/payments/`) or for internal use. If mounted, ensure Bursar/Admin permission and parent-scoped filtering for guardian access.
- **Parent-scoped endpoints**: `ParentDashboardAPI` and `StudentProfileViewSet` filter by `StudentGuardian` (linked students). Invoice/payment data for parents in the portal is served via finance **views** (e.g. parent finance page), not the finance API ViewSets. Any future parent-facing invoice/payment API must filter by `guardian_finance_student_ids(user)` or equivalent.

## Permission alignment

- **Guardian sees only own students**: Parent/guardian dashboard and entity APIs should filter by linked students (e.g. via `StudentGuardian`). Verify `ParentDashboardAPI`, `StudentProfileViewSet`, and any invoice/payment endpoints used by parents apply this filter.
- **Role-based access**: Dashboard and entity ViewSets should use DRF permission classes (e.g. `IsAuthenticated`, custom role/permission) consistent with portal permissions.
- **API schema access**: Already gated by `_is_schema_allowed` (staff/superuser or ADMIN/IT_ADMIN/LEADERSHIP).

## Gaps (guide vs implemented)

1. **Profile API**: Addressed – `GET /api/auth/profile/` is implemented (ProfileView in `apps/api/entity_api.py`).
2. **Finance under /api/**: If the guide’s invoice/payment endpoints are intended as part of the main REST API, register them under `apps/api/urls.py` or document that they live under a different prefix (e.g. finance app).
3. **API documentation dashboard**: Guide marks “API Documentation Dashboard” as missing; `/api/schema/ui/` provides schema UI; a dedicated “documentation” dashboard is optional.

## Recommendation

- Parent/guardian-facing endpoints: continue to filter by linked students; tests added for dashboard RBAC and financial API access.
- If invoice/payment ViewSets from `apps/finance/api_views.py` are mounted under `/api/`, add them to this audit and enforce Bursar/Admin + parent-scoped filtering for guardians.

**Reference**: `API_COMPLETE_GUIDE.md`, `apps/api/urls.py`, `config/urls.py`, `apps/api/entity_api.py`, `apps/api/dashboard_api.py`.
