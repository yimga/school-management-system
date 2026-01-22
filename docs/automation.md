# Phase 7 Automation Playbook

## Commands to run regularly
- `python manage.py check` & `python manage.py test` — baseline verification for every push.
- `python manage.py run_attendance_cycle` — refresh attendance/alert datasets before dashboard snapshots.
- `python manage.py run_payroll_cycle` — enforce payroll automation and keep dashboards aligned with the latest payslips.
- `python manage.py run_payment_reminders` — send fee reminders; review logs via `PaymentReminderLog`.
- `python manage.py collectstatic --noinput` — rebuild static assets before deployments.

## Custom Phase 7 command
We added `python manage.py run_phase7_checks` (see `apps/siteconfig/management/commands/run_phase7_checks.py`) to group together:
1. `check`
2. `test`
3. `run_payment_reminders`
4. `run_attendance_cycle`
4. `python manage.py send_payment_reminders` (if needed)
5. `check_integrations` (verifies required keys for enabled providers)
6. `check_roles` (reports empty roles, unused permissions, and users without roles)

Use `--require-automation` to fail if optional automation commands are missing:
```
python manage.py run_phase7_checks --require-automation
```

## Scheduled workflows
- Set Render cron to execute `python manage.py run_phase7_checks` nightly.
- Hook accessibility audits (axe/pa11y) into CI, writing results to `docs/qa-reports/`.

## Cleanup & Maintenance
- **Cleanup expired IP rules**: `python manage.py cleanup_expired_rules [--dry-run]`
	- Deactivates IPAccessRule records with `expires_at` <= now
	- Run weekly/daily depending on how often you create temporary rules
	- Example cron: `0 2 * * * python manage.py cleanup_expired_rules` (daily at 2 AM)
- **Archive old audit logs**: `python manage.py archive_old_audits [--dry-run] [--days=DAYS]`
	- Deletes AuditLog, AccessLog, UserActivitySession records older than retention policy
	- Default retention: AuditLog=90 days, AccessLog=30 days, UserActivitySession=60 days
	- Override with env vars: `AUDIT_LOG_RETENTION_DAYS`, `ACCESS_LOG_RETENTION_DAYS`, `ACTIVITY_SESSION_RETENTION_DAYS`
	- Example cron: `0 3 * * 0 python manage.py archive_old_audits` (weekly on Sunday at 3 AM)
	- Use `--days=X` to override all retention periods at once
- Always test with `--dry-run` first to preview what will be deleted/deactivated

## Threat detection and incident response
- Env vars (defaults):
	- `THREAT_WINDOW_MINUTES=60` (lookback window in minutes)
	- `THREAT_FAILED_PER_USER=10` and `THREAT_FAILED_PER_IP=20` (failed attempts before alert)
	- `THREAT_AFTER_HOURS_START=22`, `THREAT_AFTER_HOURS_END=6`, `THREAT_AFTER_HOURS_THRESHOLD=5` (off-hours band and threshold)
	- `THREAT_MUTE_MINUTES=0` (set >0 to temporarily suppress alerts)
	- `ONCALL_EMAILS=` comma-separated emails for escalations
	- `INCIDENT_TICKET_WEBHOOK=` URL to create tickets/incidents
	- `INCIDENT_PLAYBOOK_URL=https://runbooks.gileadschool.com/security/incident-response`
- Manual run:
	- `python manage.py detect_threats` (uses defaults)
	- `python manage.py detect_threats --window 30` (custom lookback)
	- Add `--no-alert` to dry-run without sending notifications
- Scheduling guidance:
	- Run every 15 minutes for near-real-time detection: `*/15 * * * * python manage.py detect_threats`
	- On Render cron, add a 15m job; on Windows Task Scheduler use an Action pointing to `python manage.py detect_threats` with a 15m trigger.
	- Keep Sentry DSN configured so errors in the command bubble to monitoring.

## Alert digest mode
- Batches LOW/MEDIUM severity alerts to reduce notification noise
- HIGH/CRITICAL alerts still sent immediately
- Alert digests stored in AlertDigest model until sent
- **Send digests**: `python manage.py send_digest_alerts [--frequency=hourly|daily] [--dry-run]`
	- Hourly: aggregates alerts from last hour, sends batch email
	- Daily: aggregates alerts from last 24 hours
	- Use `--dry-run` to preview what would be sent
- Recommended cron schedules:
	- Hourly: `0 * * * * python manage.py send_digest_alerts --frequency=hourly` (every hour on the hour)
	- Daily: `0 8 * * * python manage.py send_digest_alerts --frequency=daily` (8 AM daily)
- Digest email includes:
	- Total alert count by type and severity
	- Full list of alerts with timestamps and details
	- Requires `send_email_alert` function in alerts.py (uses COMPLIANCE_ALERTS settings)

## Rate limiting
- Protects endpoints from abuse and brute-force attacks
- Uses `django-ratelimit` library with Django cache backend
- **Settings** (config/settings.py):
	- `RATELIMIT_ENABLE=1` (set to 0 to disable globally)
	- `RATELIMIT_USE_CACHE=default` (Django cache backend)
	- `RATELIMIT_VIEW=apps.compliance.views_ratelimit.ratelimit_error` (custom 429 handler)
- **Protected endpoints**:
	- Login: `5/m` (5 attempts per minute per IP) - prevents brute-force
	- Compliance API endpoints: `30/m` (30 requests per minute per user)
	- Mute threats API: `10/m` (10 requests per minute per admin user)
- **Response when rate limit exceeded**:
	- Web requests: Custom 429.html template with 60s wait message
	- API requests: JSON response with `{"error": "Rate limit exceeded", "retry_after": "60s"}`
- **Testing**: Repeatedly refresh login page or API endpoint to trigger rate limit
- **Production tips**:
	- Use Redis cache backend for better performance: `pip install django-redis`
	- Set `CACHES['default'] = {'BACKEND': 'django_redis.cache.RedisCache', 'LOCATION': 'redis://127.0.0.1:6379/1'}`
	- Monitor rate limit hits via AccessLog model (status=429)
