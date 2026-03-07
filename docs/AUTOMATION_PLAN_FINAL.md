# Automation Plan - Final Decisions & Implementation Guide

**Date**: February 2, 2026  
**Status**: ✅ Approved - Ready for Implementation

---

## Executive Summary

Based on your feedback, here are the **final decisions** and **recommendations** for the automation plan:

1. ✅ **PaymentReminder**: Migrate to JSONField for multiple reminder days (flexible, can always change)
2. ✅ **Dry-Run Mode**: **Recommendation: ALL automation** - Essential for testing and safety
3. ✅ **Admin Approval**: **Recommendation: Optional toggle** - High-risk items can require approval, but don't block automation
4. ✅ **Notification Channels**: **SiteSettings default + UserPreference override** - Already matches existing structure!

**Implementation status**: Admin approval toggles are in Site Settings: `finance_auto_generate_require_approval`, `finance_receipt_require_admin_approval`. Notification channels: `get_notification_channels(user, automation_type)` in `apps/automation/helpers.py` (UserPreference first, then SiteSettings, then `["email"]`). Dry-run is supported on invoice generation, invoice status updates, payment reminders, receipt verification, and retry-failed-reminders.

---

## Final Decisions

### 1. PaymentReminder Structure ✅

**Decision**: Migrate `reminder_days_before` to JSONField to support multiple reminder days.

**Implementation**:
```python
# Migration: apps/finance/migrations/XXXX_payment_reminder_multiple_days.py
class Migration(migrations.Migration):
    operations = [
        migrations.AlterField(
            model_name='paymentreminder',
            name='reminder_days_before',
            field=models.JSONField(
                default=list,
                help_text="List of days before due date to send reminders, e.g., [7, 3, 1]"
            ),
        ),
        # Data migration: Convert existing single integers to lists
        migrations.RunPython(
            code=lambda apps, schema_editor: migrate_single_to_list(apps),
            reverse_code=migrations.RunPython.noop,
        ),
    ]

def migrate_single_to_list(apps):
    PaymentReminder = apps.get_model('finance', 'PaymentReminder')
    for reminder in PaymentReminder.objects.all():
        if isinstance(reminder.reminder_days_before, int):
            reminder.reminder_days_before = [reminder.reminder_days_before]
            reminder.save()
```

**Updated Model**:
```python
class PaymentReminder(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name="reminder")
    reminder_days_before = models.JSONField(
        default=list,
        help_text="List of days before due date to send reminders, e.g., [7, 3, 1]. Falls back to SiteSettings default if empty."
    )
    reminder_channels = models.JSONField(
        default=list,
        help_text="Channels to use: ['email'], ['whatsapp'], ['email', 'sms'], etc. Falls back to SiteSettings default if empty."
    )
    # ... rest of fields
    
    def get_reminder_days(self):
        """Get reminder days, falling back to SiteSettings if empty."""
        if self.reminder_days_before:
            return self.reminder_days_before
        site = SiteSettings.get_solo()
        return site.finance_payment_reminder_default_days or [7, 3, 1]
    
    def get_reminder_channels(self):
        """Get reminder channels, falling back to SiteSettings if empty."""
        if self.reminder_channels:
            return self.reminder_channels
        site = SiteSettings.get_solo()
        return site.finance_payment_reminder_default_channels or ["email"]
    
    def schedule_next(self):
        """Schedule next reminder based on earliest day in reminder_days_before."""
        if not self.invoice.due_date:
            return
        days = self.get_reminder_days()
        if not days:
            return
        # Schedule for the earliest reminder day
        earliest_day = max(days)  # Days before, so max = earliest
        target = datetime.combine(self.invoice.due_date, datetime.min.time())
        remind_at = target - timedelta(days=earliest_day)
        self.next_send_at = timezone.make_aware(remind_at, timezone=timezone.get_current_timezone())
        self.save(update_fields=["next_send_at"])
```

**Benefits**:
- ✅ Flexible: Can change reminder days anytime
- ✅ Per-invoice override: Each reminder can have different days
- ✅ SiteSettings default: Falls back to global default if not set
- ✅ Backward compatible: Migration handles existing data

---

### 2. Dry-Run Mode ✅

**Recommendation**: **ALL automation should have dry-run mode** - This is a best practice.

**Why**:
- **Testing**: Test automation without affecting production data
- **Debugging**: See what would happen before running
- **Confidence**: Admins can verify automation logic before enabling
- **Low Cost**: Easy to implement, high value

**Implementation Pattern**:
```python
@shared_task(bind=True, name="finance.auto_generate_fee_invoices")
def auto_generate_fee_invoices_task(self, dry_run: bool = False):
    """
    Automatically generate fee invoices based on schedule.
    
    Args:
        dry_run: If True, log what would be done but don't execute.
    """
    site = SiteSettings.get_solo()
    if not site.finance_auto_generate_invoices_enabled:
        logger.info("Fee auto-generation disabled in SiteSettings")
        return {"status": "disabled"}
    
    if dry_run:
        logger.info("[DRY RUN] Fee invoice generation check")
        # Calculate what would be generated
        plans = FeePlan.objects.filter(is_active=True)
        would_generate = []
        for plan in plans:
            students = _student_for_plan(plan)
            would_generate.append({
                "plan": plan.name,
                "students": len(students),
                "would_create_invoices": len(students)
            })
        return {
            "dry_run": True,
            "would_generate": would_generate,
            "total_invoices": sum(w["would_create_invoices"] for w in would_generate)
        }
    
    # Actual execution
    invoices = []
    # ... generation logic
    return {"status": "success", "invoices_created": len(invoices)}
```

**Admin UI**: Add "Test Run" button next to each automation toggle in Site Settings.

---

### 3. Admin Approval ✅

**Recommendation**: **Optional toggle in SiteSettings** - High-risk automation can require approval, but don't block automation entirely.

**Why This Approach**:
- **Flexibility**: Schools can choose if they want approval workflow
- **Not Blocking**: Automation still runs, but creates "pending approval" records
- **Audit Trail**: All automation actions are logged regardless
- **Gradual Adoption**: Schools can start without approval, add it later

**Implementation**:
```python
# SiteSettings fields
finance_auto_generate_require_approval = models.BooleanField(
    default=False,
    help_text="If enabled, fee invoice generation creates 'pending approval' records that must be approved before invoices are issued."
)

# New model for approval queue
class AutomationApprovalQueue(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Approval"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
    
    automation_type = CharField(...)  # e.g., "fee_invoice_generation"
    execution_summary = JSONField(...)  # What would be done
    requested_by = ForeignKey(User, null=True)  # System or admin
    approved_by = ForeignKey(User, null=True)
    status = CharField(choices=Status.choices, default=Status.PENDING)
    created_at = DateTimeField(auto_now_add=True)
    approved_at = DateTimeField(null=True)
    
    def execute(self):
        """Execute the automation after approval."""
        if self.status != Status.APPROVED:
            raise ValueError("Cannot execute non-approved automation")
        # Call actual automation task
        # ...

# Updated automation task
@shared_task(bind=True)
def auto_generate_fee_invoices_task(self, dry_run: bool = False):
    site = SiteSettings.get_solo()
    
    # Calculate what would be generated
    execution_summary = _calculate_fee_generation_summary()
    
    if site.finance_auto_generate_require_approval and not dry_run:
        # Create approval queue entry
        queue_entry = AutomationApprovalQueue.objects.create(
            automation_type="fee_invoice_generation",
            execution_summary=execution_summary,
            status=AutomationApprovalQueue.Status.PENDING
        )
        # Notify admins
        _notify_admins_of_pending_approval(queue_entry)
        return {"status": "pending_approval", "queue_id": queue_entry.id}
    
    # Direct execution (no approval required)
    # ... actual generation logic
```

**Admin UI**: 
- Toggle: "Require approval for fee generation" in Site Settings
- Approval queue page: `/admin/automation/approvalqueue/` to review and approve/reject

**Which Automations Should Have Approval?**
- ✅ **Fee Invoice Generation** (high-risk: creates financial records)
- ✅ **Academic Year Transitions** (high-risk: structural changes)
- ⚠️ **Payment Reminders** (low-risk: just sends messages)
- ⚠️ **Invoice Status Updates** (low-risk: read-only status changes)

---

### 4. Notification Channels ✅

**Decision**: **SiteSettings default + UserPreference override** - Perfect! This already matches your existing structure.

**Current Structure** (Already Perfect!):
```python
# SiteSettings (default)
finance_payment_reminder_default_channels = JSONField(default=["email"])

# UserPreference (user override)
notification_channels = JSONField(default=list)  # e.g., ["email", "whatsapp"]
```

**Implementation Pattern**:
```python
def get_notification_channels(user, automation_type: str) -> List[str]:
    """
    Get notification channels for a user, respecting hierarchy:
    1. UserPreference (if set)
    2. SiteSettings default
    3. System default
    """
    # Check user preference first
    try:
        user_pref = user.preferences
        if user_pref.notification_channels:
            return user_pref.notification_channels
    except UserPreference.DoesNotExist:
        pass
    
    # Fall back to SiteSettings
    site = SiteSettings.get_solo()
    if automation_type == "payment_reminder":
        return site.finance_payment_reminder_default_channels or ["email"]
    elif automation_type == "deadline_reminder":
        return site.deadline_reminder_channels or ["email"]
    
    # System default
    return ["email"]
```

**Benefits**:
- ✅ **Default for all**: SiteSettings provides sensible defaults
- ✅ **Per-user flexibility**: Users can override in their preferences
- ✅ **Already implemented**: Matches existing `UserPreference` structure
- ✅ **No breaking changes**: Works with current codebase

---

## Updated Implementation Checklist

### Phase 1.1: Automated Fee Invoice Generation

- [ ] Add `finance_auto_generate_invoices_enabled` to `SiteSettings`
- [ ] Add `finance_auto_generate_schedule` JSONField to `SiteSettings`
- [ ] Add `finance_auto_generate_require_approval` BooleanField to `SiteSettings`
- [ ] Create `get_current_academic_year()` helper
- [ ] Create `get_current_term()` helper
- [ ] Create `AutomationApprovalQueue` model (if approval enabled)
- [ ] Create Celery task: `auto_generate_fee_invoices_task(dry_run=False)`
- [ ] Add retry logic and error handling
- [ ] Add dry-run mode
- [ ] Create PeriodicTask via django-celery-beat (daily schedule)
- [ ] Add admin UI toggles in Site Settings
- [ ] Add "Test Run" button (calls task with `dry_run=True`)
- [ ] Add approval queue admin page (if approval enabled)
- [ ] Write unit tests (including dry-run)
- [ ] Write integration tests

### Phase 1.2: Fee Plan Copying

- [ ] Add admin action to `FeePlanAdmin`: "Copy to next academic year"
- [ ] Create service: `copy_fee_plan_to_year(source_plan, target_year, increase_pct)`
- [ ] Add `finance_fee_plan_auto_copy_enabled` to `SiteSettings`
- [ ] Add `finance_fee_plan_copy_increase_percentage` to `SiteSettings`
- [ ] Integrate with academic year clone workflow
- [ ] Add admin UI in Site Settings
- [ ] Write tests

### Phase 1.3: Enhanced Payment Reminders

- [ ] **Create migration**: Convert `PaymentReminder.reminder_days_before` to JSONField
- [ ] **Update model**: Add `reminder_channels` JSONField
- [ ] **Update model**: Add `get_reminder_days()` and `get_reminder_channels()` methods
- [ ] **Update model**: Modify `schedule_next()` to handle multiple days
- [ ] Add `finance_payment_reminder_default_channels` to `SiteSettings`
- [ ] Add `finance_payment_reminder_default_days` to `SiteSettings`
- [ ] Update `run_payment_reminders()` to:
  - Support multiple reminder days
  - Support WhatsApp/SMS channels
  - Use channel-specific templates
  - Respect UserPreference overrides
- [ ] Update `NotificationService` to handle multi-channel
- [ ] Add admin UI for per-invoice reminder configuration
- [ ] Write tests (including multi-day, multi-channel)

### Phase 1.4: Automated Invoice Status Updates

- [ ] Create Celery task: `update_invoice_statuses_task(dry_run=False)`
- [ ] Add `finance_invoice_auto_status_updates_enabled` to `SiteSettings`
- [ ] Add `finance_invoice_overdue_grace_period_days` to `SiteSettings`
- [ ] Add retry logic and error handling
- [ ] Add dry-run mode
- [ ] Create PeriodicTask (daily schedule)
- [ ] Write tests

### Cross-Phase: Error Handling & Logging

- [ ] Create `AutomationExecutionLog` model
- [ ] Add retry decorators to all automation tasks
- [ ] Add error notification to admins
- [ ] Create admin UI for viewing execution logs
- [ ] Add monitoring/metrics

---

## SiteSettings Fields Summary

### Finance Automation
```python
# Fee Invoice Generation
finance_auto_generate_invoices_enabled = BooleanField(default=False)
finance_auto_generate_schedule = JSONField(default={
    "mode": "academic_year_start",
    "days_before": 7,
    "academic_year_start_offset_days": 0,
    "term_start_offset_days": 0,
})
finance_auto_generate_due_date_offset_days = PositiveIntegerField(default=30)
finance_auto_generate_require_approval = BooleanField(default=False)

# Fee Plan Copying
finance_fee_plan_auto_copy_enabled = BooleanField(default=False)
finance_fee_plan_auto_copy_mode = CharField(choices=[...], default="manual")
finance_fee_plan_copy_increase_percentage = DecimalField(default=0.00)

# Payment Reminders
finance_payment_reminder_default_channels = JSONField(default=["email"])
finance_payment_reminder_default_days = JSONField(default=[7, 3, 1])
finance_payment_reminder_enable_whatsapp = BooleanField(default=False)

# Invoice Status Updates
finance_invoice_auto_status_updates_enabled = BooleanField(default=True)
finance_invoice_overdue_grace_period_days = PositiveIntegerField(default=0)
```

---

## Next Steps

1. ✅ **Review this final plan**
2. ⏳ **Start Implementation**:
   - Begin with Phase 1.2 (Fee Plan Copying) - Quick win, low risk
   - Then Phase 1.3 (Payment Reminders) - High value, requires migration
   - Then Phase 1.1 (Fee Generation) - Biggest impact, requires approval system
   - Finally Phase 1.4 (Status Updates) - Simple, high value

3. ⏳ **Create Initial Migration**: PaymentReminder structure change

---

**Status**: ✅ **READY FOR IMPLEMENTATION**  
**All decisions finalized**: Yes  
**Technical corrections addressed**: Yes
