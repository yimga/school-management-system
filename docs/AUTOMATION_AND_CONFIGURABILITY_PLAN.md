# Full Automation & Configurability Plan

**Goal**: Replace manual processes with configurable automation, eliminate hardcoding, and create a maintainable, flexible system.

**Principle**: Everything should be configurable through Site Settings or admin UI—no magic numbers, hardcoded thresholds, or fixed schedules in business logic.

---

## Executive Summary

### Current State
- ✅ **Partial Automation**: Payment reminders (Celery), deadline reminders (Celery), scheduled reports
- ⚠️ **Manual Processes**: Fee invoice generation, fee plan copying, academic year transitions
- ❌ **Hardcoded Values**: Reminder days, cache TTLs, rate limits, thresholds, message templates
- ⚠️ **Limited Configurability**: Many business rules are in code rather than SiteSettings

### Target State
- ✅ **Full Automation**: All repetitive tasks run automatically on configurable schedules
- ✅ **Zero Hardcoding**: All thresholds, schedules, templates, and rules configurable via admin
- ✅ **Self-Service**: Admins can configure automation without code changes
- ✅ **Long-Term Maintainability**: New features automatically support configuration

---

## Phase 1: Fee & Finance Automation (HIGH PRIORITY)

### 1.1 Automated Fee Invoice Generation
**Current**: Manual trigger via `/finance/generate_fees/` UI  
**Target**: Automatic generation based on configurable schedule

**Implementation**:
- Add to `SiteSettings`:
  ```python
  fee_auto_generate_enabled = BooleanField(default=False)
  fee_auto_generate_schedule = JSONField(default={
      "mode": "academic_year_start",  # or "monthly", "term_start", "custom_date"
      "days_before": 7,  # Generate invoices N days before due date
      "academic_year_start_offset_days": 0,  # Days after year start
      "term_start_offset_days": 0,  # Days after term start
      "custom_date": None,  # ISO date if mode="custom_date"
  })
  fee_auto_generate_due_date_offset_days = PositiveIntegerField(default=30)
  ```
- Create Celery task: `apps/finance/tasks.py::auto_generate_fee_invoices_task()`
- Schedule via django-celery-beat: Runs daily, checks if generation is due
- Admin UI: Toggle in Site Settings → Finance Automation section

**Benefits**:
- Eliminates manual fee generation
- Ensures invoices are created on time
- Configurable per school's calendar

---

### 1.2 Automated Fee Plan Copying (Academic Year Transition)
**Current**: Manual copy via admin action (not yet implemented)  
**Target**: Automatic copying with configurable rules

**Implementation**:
- Add admin action to `FeePlanAdmin`: "Copy to next academic year"
- Add to `SiteSettings`:
  ```python
  fee_plan_auto_copy_enabled = BooleanField(default=False)
  fee_plan_auto_copy_mode = CharField(choices=[
      ("manual", "Manual (admin action only)"),
      ("year_start", "Auto-copy on academic year start"),
      ("year_end", "Auto-copy on previous year end"),
  ], default="manual")
  fee_plan_copy_increase_percentage = DecimalField(
      max_digits=5, decimal_places=2, default=0.00,
      help_text="Percentage increase to apply when copying (e.g., 5.00 for 5% increase)"
  )
  ```
- Create service: `apps/finance/services.py::copy_fee_plan_to_year(source_plan, target_year, increase_pct)`
- Integrate with academic year clone workflow: Auto-copy fee plans when cloning year structure

**Benefits**:
- Saves hours of manual fee plan setup
- Ensures fee plans are ready before new year starts
- Supports annual fee increases automatically

---

### 1.3 Enhanced Payment Reminders (Multi-Channel, Configurable)
**Current**: Email-only, hardcoded reminder days  
**Target**: Multi-channel (Email, SMS, WhatsApp), fully configurable

**Implementation**:
- Extend `PaymentReminder` model:
  ```python
  reminder_channels = JSONField(default=["email"], help_text="List: email, sms, whatsapp")
  reminder_days_before = JSONField(default=[7, 3, 1], help_text="Days before due date")
  message_template_email = TextField(...)
  message_template_sms = TextField(...)
  message_template_whatsapp = TextField(...)
  ```
- Update `SiteSettings`:
  ```python
  payment_reminder_default_channels = JSONField(default=["email"])
  payment_reminder_default_days = JSONField(default=[7, 3, 1])
  payment_reminder_enable_whatsapp = BooleanField(default=False)
  ```
- Update `apps/finance/tasks.py::run_payment_reminders()` to:
  - Check reminder channels per reminder
  - Send via appropriate channel (email/SMS/WhatsApp)
  - Use channel-specific templates
- Admin UI: Per-invoice reminder configuration override

**Benefits**:
- Supports schools preferring WhatsApp/SMS
- Configurable reminder cadence
- Reduces payment delays

---

### 1.4 Automated Invoice Status Updates
**Current**: Manual status updates  
**Target**: Automatic overdue detection and status transitions

**Implementation**:
- Create Celery task: `apps/finance/tasks.py::update_invoice_statuses_task()`
- Runs daily, checks:
  - `due_date < today` AND `status != PAID` → Set `OVERDUE`
  - `balance_amount == 0` AND `status != PAID` → Set `PAID`
- Add to `SiteSettings`:
  ```python
  invoice_auto_status_updates_enabled = BooleanField(default=True)
  invoice_overdue_grace_period_days = PositiveIntegerField(default=0)
  ```

**Benefits**:
- Accurate invoice status without manual checks
- Automatic overdue flagging for reporting

---

## Phase 2: Academic & Evaluation Automation

### 2.1 Automated Grade Approval Workflows
**Current**: Manual approval, hardcoded deadline days  
**Target**: Configurable approval rules and auto-escalation

**Implementation**:
- Extend `SiteSettings` (already has some fields, expand):
  ```python
  grade_approval_auto_escalate_enabled = BooleanField(default=False)
  grade_approval_escalation_hours = PositiveIntegerField(default=48)
  grade_approval_auto_validate_rules = JSONField(default={
      "check_missing_scores": True,
      "check_anomalous_scores": True,
      "anomaly_threshold_std_dev": 2.0,
  })
  ```
- Create Celery task: `apps/evals/tasks.py::check_grade_approval_deadlines_task()`
- Auto-escalate if deadline passed without approval
- Send notifications to approvers and administrators

**Benefits**:
- Ensures timely grade approvals
- Reduces bottlenecks in grade publication

---

### 2.2 Automated Academic Year Transitions
**Current**: Manual clone and rollover  
**Target**: Scheduled year-end automation

**Implementation**:
- Add to `SiteSettings`:
  ```python
  academic_year_auto_transition_enabled = BooleanField(default=False)
  academic_year_transition_schedule = JSONField(default={
      "clone_days_before_year_end": 30,
      "rollover_days_after_year_end": 7,
      "auto_lock_previous_year": True,
      "copy_fee_plans": True,
      "copy_subject_assignments": True,
  })
  ```
- Create Celery task: `apps/academics/tasks.py::process_academic_year_transition_task()`
- Runs on configurable schedule (e.g., June 1st annually)
- Automatically:
  1. Creates next academic year if missing
  2. Clones structure (terms, classrooms, subjects)
  3. Copies fee plans (with optional increase)
  4. Sends notification to admins for student rollover (manual step)

**Benefits**:
- Reduces manual year setup work
- Ensures consistency across years

---

### 2.3 Automated Deadline Reminders (Enhanced)
**Current**: Configurable days, but hardcoded message templates  
**Target**: Fully configurable templates and channels

**Implementation**:
- Extend `SiteSettings`:
  ```python
  deadline_reminder_channels = JSONField(default=["email"])
  deadline_reminder_message_templates = JSONField(default={
      "email": "Dear {teacher}, please submit grades for {subject} by {deadline}.",
      "sms": "Reminder: Submit {subject} grades by {deadline}.",
      "whatsapp": "Hi {teacher}! 👋 Please submit grades for *{subject}* by *{deadline}*.",
  })
  ```
- Update `apps/analytics/tasks.py::run_deadline_reminders()` to use templates from SiteSettings

**Benefits**:
- Customizable messages per school
- Multi-channel support

---

## Phase 3: Reporting & Analytics Automation

### 3.1 Enhanced Scheduled Reports
**Current**: Basic scheduled reports exist  
**Target**: Rich scheduling with filters and multi-recipient delivery

**Implementation**:
- Extend `ScheduledReport` model:
  ```python
  schedule_frequency_advanced = JSONField(default={
      "type": "daily",  # daily, weekly, monthly, custom_cron
      "time": "08:00",
      "day_of_week": None,  # 0-6 for weekly
      "day_of_month": None,  # 1-31 for monthly
      "cron_expression": None,  # For custom
  })
  report_filters = JSONField(default={})  # Store filter parameters
  recipients = JSONField(default=[])  # List of email addresses or user IDs
  delivery_channels = JSONField(default=["email"])  # email, whatsapp, sms
  ```
- Enhance `apps/reports/bi_services.py::ScheduledReportRunner` to:
  - Support advanced scheduling
  - Apply filters dynamically
  - Deliver via multiple channels

**Benefits**:
- Flexible report scheduling
- Automated delivery to stakeholders

---

### 3.2 Automated Dashboard Data Refresh
**Current**: Manual refresh or on-demand  
**Target**: Configurable auto-refresh intervals

**Implementation**:
- Add to `SiteSettings`:
  ```python
  dashboard_auto_refresh_enabled = BooleanField(default=True)
  dashboard_refresh_intervals = JSONField(default={
      "finance": 300,  # seconds
      "analytics": 600,
      "attendance": 180,
      "payroll": 3600,
  })
  ```
- Create Celery task: `apps/analytics/tasks.py::refresh_dashboard_cache_task()`
- Pre-compute dashboard data and cache results

**Benefits**:
- Faster dashboard load times
- Always up-to-date data

---

## Phase 4: Notification & Communication Automation

### 4.1 Unified Notification Service
**Current**: Scattered notification logic  
**Target**: Centralized, channel-agnostic service

**Implementation**:
- Enhance `apps/evals/notifications.py::NotificationService`:
  ```python
  class NotificationService:
      def send(
          self,
          user_or_phone: Any,
          template_key: str,
          context: Dict[str, Any],
          channels: List[str] = None,  # Override default channels
          priority: str = "normal",  # normal, high, urgent
      ) -> Dict[str, Any]:
          # Check user preferences
          # Check SiteSettings defaults
          # Send via appropriate channels
          # Log delivery status
  ```
- Add to `SiteSettings`:
  ```python
  notification_default_channels = JSONField(default=["email"])
  notification_priority_rules = JSONField(default={
      "urgent": ["email", "sms", "whatsapp"],
      "high": ["email", "whatsapp"],
      "normal": ["email"],
  })
  ```

**Benefits**:
- Consistent notification delivery
- User preference support
- Multi-channel fallback

---

### 4.2 Automated Communication Workflows
**Current**: Manual messaging  
**Target**: Automated workflows (e.g., welcome messages, report sharing)

**Implementation**:
- Create `apps/communication/workflows.py`:
  ```python
  class CommunicationWorkflow:
      WELCOME_STUDENT = "welcome_student"
      WELCOME_PARENT = "welcome_parent"
      REPORT_CARD_READY = "report_card_ready"
      INVOICE_ISSUED = "invoice_issued"
      PAYMENT_RECEIVED = "payment_received"
      
      def trigger(self, workflow_type: str, context: Dict):
          # Load workflow config from SiteSettings
          # Send messages via NotificationService
  ```
- Add to `SiteSettings`:
  ```python
  communication_workflows_enabled = JSONField(default={
      "welcome_student": True,
      "welcome_parent": True,
      "report_card_ready": True,
      "invoice_issued": True,
  })
  communication_workflow_templates = JSONField(default={...})
  ```

**Benefits**:
- Consistent communication
- Reduces manual messaging
- Improves parent engagement

---

## Phase 5: Configuration & Hardcoding Elimination

### 5.1 Move All Hardcoded Values to SiteSettings
**Current**: Many thresholds, TTLs, and rules hardcoded  
**Target**: All configurable via admin

**Audit & Migration**:
1. **Cache TTLs**: Move to `SiteSettings.cache_ttls` (JSONField)
2. **Rate Limits**: Move to `SiteSettings.rate_limits` (JSONField)
3. **Deduplication Windows**: Move to `SiteSettings.dedupe_windows` (JSONField)
4. **Thresholds**: Move to `SiteSettings.thresholds` (JSONField)
   - Grade thresholds (A/B/C/D/E minimums)
   - Payment thresholds (late fee percentages)
   - Attendance thresholds (minimum attendance %)
5. **Message Templates**: Move all hardcoded templates to `SiteSettings.message_templates` (JSONField)

**Implementation Pattern**:
```python
# Before (hardcoded):
CACHE_TTL = 300  # seconds

# After (configurable):
site = SiteSettings.get_solo()
cache_ttl = site.cache_ttls.get("default", 300)
```

---

### 5.2 Configuration Validation & Defaults
**Implementation**:
- Create `apps/siteconfig/validators.py`:
  ```python
  def validate_site_settings(site: SiteSettings) -> List[str]:
      """Returns list of validation errors."""
      errors = []
      # Validate cache TTLs are positive
      # Validate reminder days are reasonable
      # Validate thresholds are within bounds
      return errors
  ```
- Add admin action: "Validate Configuration"
- Show warnings/errors in Site Settings UI

**Benefits**:
- Prevents misconfiguration
- Clear feedback to admins

---

## Phase 6: Long-Term Architectural Improvements

### 6.1 Plugin-Style Automation System
**Target**: Extensible automation without code changes

**Implementation**:
- Create `apps/automation/` app:
  ```python
  class AutomationRule(models.Model):
      name = CharField(...)
      trigger_type = CharField(choices=[
          ("schedule", "Scheduled"),
          ("event", "Event-based"),
          ("condition", "Condition-based"),
      ])
      trigger_config = JSONField(...)  # Schedule, event type, conditions
      action_type = CharField(choices=[
          ("send_notification", "Send Notification"),
          ("generate_report", "Generate Report"),
          ("update_status", "Update Status"),
          ("run_script", "Run Custom Script"),
      ])
      action_config = JSONField(...)
      is_active = BooleanField(default=True)
  ```
- Create automation engine: `apps/automation/engine.py`
- Admin UI: Visual rule builder

**Benefits**:
- Non-developers can create automation
- Highly flexible
- Future-proof

---

### 6.2 Event-Driven Architecture
**Target**: Decouple automation from direct code coupling

**Implementation**:
- Create event system: `apps/automation/events.py`
  ```python
  class EventEmitter:
      def emit(self, event_type: str, payload: Dict):
          # Emit event
          # Trigger matching AutomationRules
  ```
- Emit events for:
  - Invoice created/paid
  - Student enrolled
  - Grade submitted
  - Payment received
  - Academic year started
- Automation rules listen to events

**Benefits**:
- Loose coupling
- Easy to add new automation
- Testable

---

### 6.3 Configuration Versioning & Rollback
**Target**: Track configuration changes and allow rollback

**Implementation**:
- Use Django's `django-reversion` or custom versioning:
  ```python
  class SiteSettingsVersion(models.Model):
      site_settings = ForeignKey(SiteSettings)
      version = PositiveIntegerField()
      config_snapshot = JSONField()
      created_at = DateTimeField()
      created_by = ForeignKey(User)
  ```
- Admin UI: "View History" and "Restore Version"

**Benefits**:
- Safety net for configuration changes
- Audit trail

---

## Implementation Priority & Timeline

### Immediate (Week 1-2)
1. ✅ Phase 1.1: Automated Fee Invoice Generation
2. ✅ Phase 1.2: Fee Plan Copying Admin Action
3. ✅ Phase 1.3: Enhanced Payment Reminders (multi-channel)

### Short-Term (Week 3-4)
4. ✅ Phase 1.4: Automated Invoice Status Updates
5. ✅ Phase 2.1: Enhanced Grade Approval Workflows
6. ✅ Phase 5.1: Move Hardcoded Values to SiteSettings (start with cache TTLs, thresholds)

### Medium-Term (Month 2)
7. ✅ Phase 2.2: Automated Academic Year Transitions
8. ✅ Phase 3.1: Enhanced Scheduled Reports
9. ✅ Phase 4.1: Unified Notification Service
10. ✅ Phase 5.1: Complete hardcoding elimination

### Long-Term (Month 3+)
11. ✅ Phase 4.2: Automated Communication Workflows
12. ✅ Phase 6.1: Plugin-Style Automation System
13. ✅ Phase 6.2: Event-Driven Architecture
14. ✅ Phase 6.3: Configuration Versioning

---

## Testing Strategy

### Unit Tests
- Test each automation task independently
- Test configuration loading and defaults
- Test edge cases (missing config, invalid values)

### Integration Tests
- Test full automation workflows end-to-end
- Test multi-channel notifications
- Test academic year transitions

### Manual Testing
- Admin UI: Configure automation in Site Settings
- Verify automation runs on schedule
- Verify notifications are sent correctly

---

## Migration Strategy

### Backward Compatibility
- All new `SiteSettings` fields have sensible defaults
- Existing automation continues to work
- Gradual migration: Old code paths deprecated, new ones preferred

### Data Migration
- Create migrations for new `SiteSettings` fields
- Populate defaults from existing hardcoded values
- Document migration steps

---

## Success Metrics

1. **Automation Coverage**: % of manual processes automated
2. **Configuration Coverage**: % of hardcoded values moved to config
3. **Time Saved**: Hours saved per month from automation
4. **Error Reduction**: Fewer manual errors (missed invoices, late reminders)
5. **Admin Satisfaction**: Ease of configuring automation

---

## Notes

- **Celery Setup**: Ensure `REDIS_URL` is configured for production
- **Monitoring**: Add logging/metrics for all automation tasks
- **Error Handling**: All automation should fail gracefully and notify admins
- **Documentation**: Update admin docs with automation configuration guides

---

## Next Steps

1. Review and approve this plan
2. Start with Phase 1.1 (Automated Fee Invoice Generation)
3. Create initial todo list for Phase 1 tasks
4. Begin implementation
