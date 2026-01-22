# Mark Sheet & Report Card Tool - Quick Start Guide

## Current Status

✅ **PHASE 1-3 COMPLETE** - All core features implemented and committed to `marksheet_reportcard_tool` branch

**Last 4 commits:**
```
e4b6e14 - Documentation (IMPLEMENTATION_STATUS.md)
7ebe418 - PHASE 3a: Frontend templates (4 templates created)
c1bb9e5 - PHASE 2: Backend services (6 views, 2 management commands, analytics)
d428f99 - PHASE 1: Database models (5 new models, 4 migrations)
```

**Ops note (Threat detection):**
- Configure detection env vars: `THREAT_WINDOW_MINUTES`, `THREAT_FAILED_PER_USER`, `THREAT_FAILED_PER_IP`, `THREAT_AFTER_HOURS_START`, `THREAT_AFTER_HOURS_END`, `THREAT_AFTER_HOURS_THRESHOLD`, `THREAT_MUTE_MINUTES`, `ONCALL_EMAILS`, `INCIDENT_TICKET_WEBHOOK`, `INCIDENT_PLAYBOOK_URL`.
- Run detection manually with `python manage.py detect_threats --window 60` (add `--no-alert` to dry-run); schedule every 15 minutes in cron/Task Scheduler for ongoing coverage.

---

## What's Implemented

### ✅ Models (Database Layer)
- `Evaluation` - Extended with letter grades, clock hours, practical tracking
- `AssessmentWeights` - Multi-scale grading (0-20, A-E, GPA, percentage) with region support
- `GradeAudit` - Immutable audit trail for all grade changes
- `OfflineMarkEntry` - Offline sync queue with conflict resolution
- `NotificationPreference` - Guardian communication settings
- `GradeImportJob` - Bulk import tracking
- `SiteSettings` - 15+ new configuration fields

### ✅ Services (Business Logic)
- `validators.py` - 6 validation rules (range, outliers, jumps, duplicates)
- `signals.py` - Auto-audit trail, grade conversion, sync tracking
- `offline_sync.py` - 3-mode conflict resolution (reject/auto-merge/show-both)
- `notifications.py` - SMS/Email delivery (Twilio, AfricasTalking, Console)
- `importers.py` - CSV validation + database persistence
- `analytics/services.py` - Compliance reporting, audit trail, import tracking

### ✅ Views (API & Web Endpoints)
- `/evals/compliance/dashboard/` - Teacher compliance status with KPIs
- `/evals/compliance/deadline/<id>/extend/` - Extend deadline UI
- `/evals/api/grade-import/preview/` - CSV import validation (POST)
- `/evals/api/grade-import/apply/` - Apply validated grades (POST)
- `/evals/audit-trail/<id>/` - Grade change history timeline
- `/evals/offline-conflict/<id>/resolve/` - Manual conflict resolution

### ✅ Templates (Frontend)
- `compliance_dashboard.html` - KPI cards, filters, compliance table, deadline modals
- `audit_trail.html` - Timeline view of all grade changes
- `resolve_offline_conflict.html` - Side-by-side conflict resolution
- `extend_deadline.html` - Deadline extension form

### ✅ Commands (Automation)
- `python manage.py send_deadline_reminders` - Send reminder notifications to teachers

---

## How to Use

### 1. **Access Compliance Dashboard**
```
URL: http://localhost:8000/evals/compliance/dashboard/
Requirements: Staff/Admin user
Features:
  - View all teachers' grading status
  - Filter by status (compliant/at_risk/overdue)
  - View deadline details per subject
  - Extend deadlines with reason
```

### 2. **View Grade Audit Trail**
```
URL: http://localhost:8000/evals/audit-trail/<evaluation_id>/
Shows:
  - All changes to a student's grade
  - Before/after scores
  - Who changed it and when
  - Validation errors (if any)
  - Offline sync conflicts (if applicable)
```

### 3. **Upload & Validate Grades**
```
Method: POST to /evals/api/grade-import/preview/
Payload: CSV file with columns:
  - student_code
  - subject_assignment_id
  - term_id
  - teacher_username
  - seq1, seq2, exam, mock, practical
  - remarks (optional)

Response: Preview with validation results
  - is_valid (bool per row)
  - errors[] (validation failures)
  - warnings[] (non-blocking issues)
  - Total counts (valid/invalid)
```

### 4. **Apply Validated Grades**
```
Method: POST to /evals/api/grade-import/apply/
Payload: Same CSV file
Response: Import job status
  - created_count, updated_count, failed_count
  - job_id for tracking
  - duration_seconds
```

### 5. **Send Deadline Reminders**
```bash
# Send reminders for grades due in 7, 3, 1 days
python manage.py send_deadline_reminders --days 7,3,1

# Add --dry-run to preview without sending
python manage.py send_deadline_reminders --days 7 --dry-run
```

### 6. **Resolve Offline Conflicts**
```
When: Offline entry conflicts with online entry
URL: http://localhost:8000/evals/offline-conflict/<offline_entry_id>/resolve/
Action: Choose which version to keep (offline/online)
Result: Marked as synced, logged in audit trail
```

---

## Key Features

### 📊 Compliance Dashboard
- Real-time completion tracking
- Status indicators (Compliant/At-Risk/Overdue)
- Deadline countdown
- Quick deadline extensions
- Per-teacher subject breakdown

### 🔍 Grade Validation
- **Score Range:** Ensures 0-100 or 0-20 depending on scale
- **Outlier Detection:** Statistical detection (>2σ from mean)
- **Jump Detection:** Flags >50% change from previous term
- **Duplicate Remarks:** Alerts if same remark for 3+ students
- **Missing Components:** Validates required fields per configuration

### 💾 Offline Sync
- Marks entered offline are queued for sync
- Conflict resolution on next online connection
- Three modes:
  - **REJECT:** Keep online, discard offline
  - **AUTO_MERGE:** Auto keep latest timestamp
  - **SHOW_BOTH:** Manual resolution UI (current)

### 📧 Notifications
- **Email:** Grade publication + deadline reminders
- **SMS:** Twilio / AfricasTalking integration
- **Configurable:** Frequency (immediate/digest) + methods

### 🛠 Audit Trail
- Every grade change is immutable record
- Tracks: who, what, when, before/after
- Used for rollback, compliance, data integrity

---

## Configuration

### In Django Admin > Site Settings

**Grading:**
```
Default Grading Scale: NUMERIC_0_20 | LETTER_A_E | GPA_4_0 | PERCENTAGE
Default Region: CAMEROON_ANGLOPHONE | CAMEROON_FRANCOPHONE | GLOBAL
```

**Notifications:**
```
SMS Provider: twilio | africastalking | console
SMS API Key: [Your API key]
SMS Sender ID: [Your sender ID]
Email From Address: noreply@gilead.school
```

**Deadlines:**
```
Teacher Deadline Reminder Days: [7, 3, 1, 0.5]  # JSON array
Teacher Reminder Time: 09:00 AM
```

**Offline Mode:**
```
Enable Offline Mode: true/false
Conflict Resolution Mode: show_both | auto_merge | reject
```

---

## Testing Checklist

✅ Django system check passed (0 issues)
✅ All 4 migrations applied successfully
✅ Signal handlers registered
✅ 6 new URL routes working
✅ Admin interfaces displaying correctly
✅ Import validation pipeline functional

### Quick Test Commands
```bash
# Verify system health
python manage.py check

# List compliance for active term
python manage.py shell
>>> from apps.analytics.services import get_teacher_compliance
>>> from apps.academics.services import get_active_year_and_term
>>> year, term = get_active_year_and_term()
>>> data = get_teacher_compliance(year.id, term.id)
>>> len(data)  # Number of teachers

# Test import validation
>>> from apps.evals.importers import preview_import_with_validation
>>> rows, errors = preview_import_with_validation([...])
>>> rows[0].is_valid
```

---

## Next Steps (PHASE 4)

### Immediate (this week)
- [ ] Create bulk upload UI template with file dropzone
- [ ] Integrate SMS provider (test API keys)
- [ ] Set up Celery for background imports
- [ ] Add role-based access controls

### Coming soon
- [ ] Offline mode sync implementation (PWA or mobile app)
- [ ] Photo evidence upload for practical assessments
- [ ] Parent portal for grade viewing
- [ ] Report card PDF generation
- [ ] Multi-year grade trend analysis

---

## Important Notes

### ⚠️ Database Changes
All 4 migrations have been applied:
- `evals.0005_*` - Added 7 fields to Evaluation, 6 to AssessmentWeights, + 2 new models
- `people.0009_*` - Added NotificationPreference model
- `analytics.0002_*` - Added GradeImportJob model
- `siteconfig.0014_*` - Added 15 settings fields

### 🔐 Permissions
- `/compliance/dashboard/` → Staff only
- `/api/grade-import/*` → Staff only
- `/audit-trail/` → Staff/Teacher (own grades)
- `/offline-conflict/resolve/` → Staff only

### 📱 SMS Providers
To use SMS, configure in Site Settings:
1. **Twilio:** Set SMS API Key, enable in settings, add phone numbers
2. **AfricasTalking:** Set API key and sender ID, test in console mode first
3. **Console:** Safe for development/testing (prints to stdout)

---

## File Locations

- **Models:** `apps/evals/models.py`, `apps/people/models.py`, `apps/analytics/models.py`, `apps/siteconfig/models.py`
- **Services:** `apps/evals/validators.py`, `apps/evals/notifications.py`, `apps/analytics/services.py`
- **Views:** `apps/evals/views.py` (last 200 lines)
- **Templates:** `templates/evals/*.html`
- **Commands:** `apps/analytics/management/commands/send_deadline_reminders.py`
- **Documentation:** `IMPLEMENTATION_STATUS.md`

---

## Support & Troubleshooting

**Issue:** "No active academic year or term"
- **Fix:** Create an academic year in Django admin, set `is_active=True`

**Issue:** SMS not sending
- **Fix:** Check Site Settings SMS provider configuration, test with `console` mode first

**Issue:** Import file validation fails
- **Fix:** Verify CSV headers match expected columns, run preview first to see errors

**Issue:** Offline entry conflicts
- **Fix:** Use `/evals/offline-conflict/<id>/resolve/` to manually choose version

---

**Branch:** `marksheet_reportcard_tool`
**Last Updated:** [Current date]
**Status:** PHASE 3 IN PROGRESS - Core features complete, ready for testing

