# Deployment Verification Checklist

## ✅ Code Verification (All Present on `main`)

### 1. Messaging Groups & Department Threads
- ✅ `apps/communication/views_groups.py` - Group management views
- ✅ `apps/communication/forms_groups.py` - Group creation/update forms
- ✅ `apps/communication/urls.py` - URL routing (included in `config/urls.py`)
- ✅ `templates/communication/group_*.html` - All 6 templates present
- ✅ `apps/people/signals.py` - Auto-sync department threads
- ✅ `apps/people/apps.py` - Signals registered

**Expected URLs:**
- `/communication/groups/` - List all groups
- `/communication/groups/create/` - Create new group
- `/communication/groups/<id>/` - View group chat
- `/communication/groups/<id>/manage/` - Manage group

### 2. Contact Requests (Parent → Staff)
- ✅ `apps/communication/models.py` - `ContactRequest` model
- ✅ `apps/portal/views_contact_requests.py` - Parent & staff views
- ✅ `apps/portal/forms_contact_requests.py` - Contact request forms
- ✅ `templates/parent/contact_school.html` - Parent form
- ✅ `templates/staff/contact_requests_*.html` - Staff triage views

**Expected URLs:**
- `/portal/parent/contact-school/` - Parent contact form
- `/portal/staff/contact-requests/` - Staff list view
- `/portal/staff/contact-requests/<uuid>/` - Staff detail view

### 3. Dashboard Improvements
- ✅ `apps/accounts/utils.py` - `get_dashboard_context()` helper
- ✅ `apps/portal/views.py` - Uses `get_dashboard_context` for parent dashboard
- ✅ `apps/evals/views.py` - Uses `get_dashboard_context` for teacher dashboard
- ✅ `templates/teacher/dashboard.html` - Department thread links integrated

**Expected Features:**
- Drag-and-drop dashboard widgets (Sortable.js)
- Department chat quick action buttons on teacher dashboard
- Department announcement creation link

### 4. Grade Approval Bypass
- ✅ `apps/evals/models.py` - Bypass fields added to `GradeApprovalRequest`
- ✅ `apps/evals/forms.py` - `GradeApprovalBypassForm`
- ✅ `apps/evals/migrations/0018_*.py` - Migration present
- ✅ `templates/evals/grade_approval_detail.html` - Bypass UI

### 5. OCR Improvements
- ✅ `apps/evals/ocr.py` - Enhanced with preprocessing & confidence scores
- ✅ `apps/evals/views.py` - Delta mode & interactive review UI
- ✅ `templates/teacher/marks_entry.html` - OCR review interface

### 6. Report Cards
- ✅ `apps/reports/services.py` - Specialty rankings implemented
- ✅ `templates/reports/term_report_cameroon.html` - Cameroon-style template
- ✅ `templates/reports/annual_report_cameroon.html` - Annual template
- ✅ `apps/siteconfig/models.py` - `ReportCardStyle` with editable labels

## 🔍 Deployment Issues to Check

### 1. Migrations
**Run on server:**
```bash
python manage.py migrate
```

**Verify migrations applied:**
```bash
python manage.py showmigrations communication evals
```
Should show `[X]` for:
- `communication.0004_contactrequest_contactrequestattachment_and_more`
- `evals.0018_gradeapprovalrequest_bypass_fields`

### 2. Static Files
**If using static file collection:**
```bash
python manage.py collectstatic --noinput
```

**Check if static files are served:**
- `/static/js/dashboard-layout.js` - Should load
- `/static/css/dashboard-layout-controls.css` - Should load

### 3. App Registration
**Verify in `config/settings.py`:**
```python
INSTALLED_APPS = [
    # ...
    "apps.communication",  # ✅ Should be present
    # ...
]
```

### 4. URL Configuration
**Verify in `config/urls.py`:**
```python
urlpatterns = [
    # ...
    path('communication/', include(('apps.communication.urls', 'communication'), namespace='communication')),
    # ...
]
```

### 5. Signal Registration
**Verify `apps/people/apps.py` has:**
```python
def ready(self):
    import apps.people.signals  # noqa
```

### 6. Database State
**Check if department threads exist:**
```python
# In Django shell
from apps.communication.models import MessageThread
MessageThread.objects.filter(scope='DEPARTMENT').count()
```

**If zero, run backfill command:**
```bash
python manage.py sync_department_threads
```

## 🧪 Testing Checklist

### Teacher Dashboard
1. Login as teacher with department assigned
2. Check for "Department Chat" button in quick actions
3. Check for "Dept Announcement" button
4. Verify department thread appears in "Class & Department Chats" section

### Parent Portal
1. Login as parent
2. Navigate to `/portal/parent/contact-school/`
3. Fill out contact form and submit
4. Verify form submission works

### Staff Triage
1. Login as staff with `SECRETARY`, `EXECUTIVE_ASSISTANT`, or `VIRTUAL_ASSISTANT` role
2. Navigate to `/portal/staff/contact-requests/`
3. Verify contact requests list appears
4. Click on a request to view details

### Messaging Groups
1. Login as teacher/admin
2. Navigate to `/communication/groups/`
3. Verify groups list appears
4. Click "Create Group" - verify form loads
5. Create a group and verify it appears in list

### Grade Approval Bypass
1. Login as staff with approval permissions
2. Navigate to a grade approval request
3. Verify "Bypass Approval" section appears
4. Fill bypass form and submit
5. Verify bypass fields are recorded

## 🐛 Common Issues

### Issue: "No module named 'apps.communication'"
**Solution:** Verify `apps.communication` is in `INSTALLED_APPS`

### Issue: "TemplateDoesNotExist: communication/group_list.html"
**Solution:** 
- Check `TEMPLATES` setting includes app directories
- Verify templates are in `templates/communication/`

### Issue: Department threads not appearing
**Solution:**
- Run `python manage.py sync_department_threads`
- Check teacher has `department` assigned in profile
- Verify signal is registered in `apps/people/apps.py`

### Issue: URLs return 404
**Solution:**
- Verify `config/urls.py` includes communication URLs
- Check `apps/communication/urls.py` exists
- Restart Django server after URL changes

### Issue: Static files not loading
**Solution:**
- Run `python manage.py collectstatic`
- Check `STATIC_URL` and `STATIC_ROOT` settings
- Verify web server serves static files correctly

## 📝 Next Steps

1. **Run migrations** on production server
2. **Collect static files** if needed
3. **Run backfill command** for department threads
4. **Test each feature** using the checklist above
5. **Check server logs** for any errors
