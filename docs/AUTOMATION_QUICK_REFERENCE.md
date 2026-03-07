# Automation Quick Reference

## Current Automation Status

| Area | Current State | Automation Level |
|------|---------------|------------------|
| **Fee Invoice Generation** | Manual UI trigger | ❌ None |
| **Payment Reminders** | Celery task (email only) | ⚠️ Partial |
| **Fee Plan Copying** | Not implemented | ❌ None |
| **Invoice Status Updates** | Manual | ❌ None |
| **Grade Approval** | Manual with hardcoded deadlines | ⚠️ Partial |
| **Academic Year Transitions** | Manual clone/rollover | ❌ None |
| **Deadline Reminders** | Celery task (configurable days) | ✅ Good |
| **Scheduled Reports** | Basic scheduling | ⚠️ Partial |
| **Notifications** | Scattered logic | ⚠️ Partial |

---

## Key Automation Opportunities

### 🔴 High Priority (Immediate Value)

1. **Automated Fee Invoice Generation**
   - **Why**: Saves hours of manual work each term
   - **How**: Celery task runs daily, checks if generation is due based on academic calendar
   - **Config**: Site Settings → Finance Automation

2. **Fee Plan Copying (Academic Year Transition)**
   - **Why**: Essential for year-end setup
   - **How**: Admin action + optional auto-copy on year start
   - **Config**: Site Settings → Fee Plan Auto-Copy

3. **Enhanced Payment Reminders (Multi-Channel)**
   - **Why**: WhatsApp/SMS more effective than email in Cameroon
   - **How**: Extend existing Celery task to support WhatsApp/SMS
   - **Config**: Site Settings → Payment Reminders

### 🟡 Medium Priority (High Value)

4. **Automated Invoice Status Updates**
   - **Why**: Ensures accurate reporting without manual checks
   - **How**: Daily Celery task updates overdue/paid statuses
   - **Config**: Site Settings → Invoice Automation

5. **Automated Academic Year Transitions**
   - **Why**: Reduces manual year setup work
   - **How**: Scheduled task clones structure and copies fee plans
   - **Config**: Site Settings → Academic Year Automation

6. **Unified Notification Service**
   - **Why**: Consistent, multi-channel communication
   - **How**: Centralize notification logic, support user preferences
   - **Config**: Site Settings → Notifications

### 🟢 Low Priority (Nice to Have)

7. **Enhanced Scheduled Reports**
   - **Why**: Flexible report delivery
   - **How**: Advanced scheduling, multi-recipient, multi-channel
   - **Config**: Report admin → Scheduling options

8. **Automated Communication Workflows**
   - **Why**: Consistent welcome messages, report sharing
   - **How**: Event-driven workflows
   - **Config**: Site Settings → Communication Workflows

---

## Hardcoding Elimination Checklist

### Values to Move to SiteSettings

- [ ] Cache TTLs (currently hardcoded `300`, `600`, etc.)
- [ ] Rate limit windows (deduplication TTLs)
- [ ] Grade thresholds (A/B/C/D/E minimums)
- [ ] Payment thresholds (late fee percentages)
- [ ] Attendance thresholds (minimum %)
- [ ] Message templates (all hardcoded strings)
- [ ] Reminder days (some hardcoded, some configurable)
- [ ] Default notification channels

### Pattern to Follow

```python
# ❌ Before (hardcoded):
CACHE_TTL = 300

# ✅ After (configurable):
site = SiteSettings.get_solo()
cache_ttl = site.cache_ttls.get("default", 300)
```

---

## Configuration Best Practices

### 1. Always Provide Sensible Defaults
- New `SiteSettings` fields should have defaults that match current behavior
- Ensures backward compatibility

### 2. Validate Configuration
- Add validation for numeric ranges (e.g., cache TTL > 0)
- Show warnings in admin UI for invalid config

### 3. Document Configuration Options
- Add help text to all `SiteSettings` fields
- Create admin docs explaining automation options

### 4. Make Configuration Discoverable
- Group related settings in fieldsets
- Use clear labels and descriptions
- Provide examples in help text

---

## Long-Term Vision: Plugin-Style Automation

**Goal**: Non-developers can create automation rules without code changes.

**Example Rule**:
- **Trigger**: Invoice created
- **Condition**: Amount > 50,000 XAF
- **Action**: Send WhatsApp notification to parent
- **Schedule**: Immediately

**Implementation**: `AutomationRule` model with JSON config for triggers/actions.

---

## Quick Wins (Start Here)

1. **Add Fee Plan Copy Admin Action** (1-2 hours)
   - Add action to `FeePlanAdmin`
   - Create service function to copy plan
   - Test with real data

2. **Extend Payment Reminders to WhatsApp** (2-3 hours)
   - Update `run_payment_reminders()` to check WhatsApp config
   - Use existing `NotificationService.send_whatsapp()`
   - Test end-to-end

3. **Move Cache TTLs to SiteSettings** (1 hour)
   - Add `cache_ttls` JSONField
   - Update code to read from SiteSettings
   - Test cache behavior

---

## Monitoring & Observability

### What to Monitor

1. **Automation Task Execution**
   - Success/failure rates
   - Execution time
   - Error logs

2. **Configuration Usage**
   - Which automation rules are active
   - Which channels are used most
   - Configuration change frequency

3. **Business Impact**
   - Invoices generated automatically
   - Reminders sent
   - Time saved

### Tools

- Celery monitoring: Flower or custom dashboard
- Logging: Structured logs for all automation tasks
- Metrics: Prometheus metrics for task execution

---

## Questions to Answer Before Implementation

1. **Scheduling**: Use django-celery-beat or cron?
   - **Recommendation**: django-celery-beat (more flexible, admin UI)

2. **Error Handling**: How to handle automation failures?
   - **Recommendation**: Log errors, send admin notification, retry with exponential backoff

3. **Testing**: How to test automation without affecting production?
   - **Recommendation**: Use `dry_run` flags, test in staging environment

4. **Rollback**: How to disable automation if issues arise?
   - **Recommendation**: Toggle flags in SiteSettings, immediate effect

---

## Related Documentation

- [Full Automation Plan](./AUTOMATION_AND_CONFIGURABILITY_PLAN.md)
- [API Services Requirements](./API_SERVICES_REQUIREMENTS.md)
- [Cameroon/Buea Setup Guide](./CAMEROON_BUEA_SETUP_GUIDE.md)
- [Finance Workflow](./WORKFLOW_FINANCE.md)
