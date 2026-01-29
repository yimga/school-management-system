# Dashboard Certification Integration & Workflow Improvements

## Overview
Comprehensive integration of the Certification/GCE workflow across all dashboards, ensuring consistent alignment, visibility, and ease of use when switching between dashboard views.

## Changes Made

### 1. Backend Dashboard (`/backend`)
**Added:**
- **Certification Stats Widget**: Shows active sessions, total candidates, draft/verified counts
- **Quick Action Button**: "Certification & Exams" button in quick actions section
- **Certification Overview Card**: Full widget with session links and quick access buttons
- **Sidebar Link**: Added "Certification & Exams" to available sidebar items (when GCE enabled)

**Location**: `templates/accounts/backend_dashboard.html`, `apps/accounts/views.py`

### 2. Teacher Dashboard (`/teacher`)
**Added:**
- **Certification Widget**: Shows exam candidates in teacher's classes
- **Stats Display**: Draft/verified counts for candidates in assigned classrooms
- **Session Links**: Quick access to active exam sessions
- **Conditional Display**: Only shows if GCE enabled and teacher has exam candidates

**Location**: `templates/teacher/dashboard.html`, `apps/evals/views.py`

### 3. Parent Dashboard (`/parent`)
**Added:**
- **Certification Status in Child Cards**: Shows exam registration status per child
- **Certification Widget Section**: Overview of all children's exam registrations
- **Status Badges**: Visual indicators (Draft/Submitted/Verified) with color coding
- **Quick Access**: Link to certification center from child cards

**Location**: `templates/parent/dashboard.html`, `apps/portal/views.py`

### 4. Workflow Center
**Enhanced:**
- Added "Certification Center" link as first item in certification section
- Added "Presets & Templates" link for exam configuration
- Improved organization of certification workflow steps

**Location**: `apps/accounts/views.py` (workflow_center function)

### 5. Dashboard View Options
**Added:**
- **New Dashboard View**: `CERTIFICATION` option in `DashboardView` enum
- **Widget Mapping**: Certification view shows certification, performance, tasks, links, events widgets
- **Widget Option**: Added "certification" to `DASHBOARD_WIDGET_OPTIONS`
- **Admin Defaults**: Added certification widget to ADMIN role defaults

**Location**: `apps/siteconfig/models.py`

### 6. Consistent Alignment & Styling
**Added:**
- **CSS Alignment Rules**: Consistent column layout across all dashboards
- **Responsive Behavior**: Proper stacking on mobile, side-by-side on desktop
- **Widget Spacing**: Uniform gaps and padding when switching views
- **Sticky Sidebar**: Secondary column stays visible when scrolling (desktop)

**Location**: `static/css/dashboard-layout-controls.css`

## Technical Details

### Backend Dashboard Stats
```python
certification_stats = {
    "active_sessions": int,
    "total_candidates": int,
    "draft_candidates": int,
    "verified_candidates": int,
    "sessions": QuerySet[CertificationExamSession],  # Recent 3
}
```

### Teacher Dashboard Stats
- Only shows if teacher's classrooms have candidates
- Filters by teacher's assigned classrooms
- Shows counts per status (Draft/Verified)

### Parent Dashboard Stats
- Shows per-child certification status
- Includes `candidates_by_student` mapping for quick lookup
- Displays session name and status badge

### Dashboard View Switching
When users switch dashboard views (Overview → Finance → Certification → etc.):
1. Widgets are filtered based on view mapping
2. Layout persists via `DashboardUserPreference`
3. Alignment remains consistent via CSS rules
4. Certification widgets appear/disappear based on GCE enablement

## User Experience Improvements

### For Administrators
- **One-click access** to Certification Center from backend dashboard
- **At-a-glance stats** for active sessions and candidate counts
- **Quick actions** to create sessions, bulk add candidates
- **Workflow integration** in Workflow Center

### For Teachers
- **Visibility** into which students are exam candidates
- **Status tracking** for draft vs verified registrations
- **Quick links** to exam sessions for their classes

### For Parents
- **Per-child status** directly on child cards
- **Visual badges** showing registration progress
- **Quick access** to detailed certification information
- **Summary widget** showing overall exam registration status

## Alignment & Responsiveness

### Desktop (≥992px)
- Main column: Flexible width, takes remaining space
- Secondary column: Fixed 320px width, sticky positioning
- Widgets: Consistent spacing (1.5rem gap)

### Tablet (768px-991px)
- Columns stack vertically
- Secondary column: Full width
- Widgets: Maintain spacing

### Mobile (<768px)
- Single column layout
- All widgets full width
- Reduced padding for space efficiency

## Migration Required
- `apps/siteconfig/migrations/0045_alter_sitesettings_admission_number_pattern_and_more.py`
  - Adds `CERTIFICATION` to `DashboardView` choices
  - Updates widget defaults

## Testing Checklist
- [ ] Backend dashboard shows certification widget when GCE enabled
- [ ] Teacher dashboard shows certification widget for exam classes
- [ ] Parent dashboard shows certification status on child cards
- [ ] Switching dashboard views maintains alignment
- [ ] Mobile view stacks widgets properly
- [ ] All certification links work correctly
- [ ] Widgets persist layout when dragging/reordering

## Future Enhancements
- Add certification widget to analytics dashboard
- Create dedicated certification dashboard page
- Add certification notifications/alerts
- Integrate certification deadlines into calendar widgets
