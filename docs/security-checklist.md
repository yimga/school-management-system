# Security & Penetration Testing Checklist

**Doc status: Closed.** Unchecked items are reference for audits; no open doc work. Deferred or optional items in **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**.

## Overview
This document provides a comprehensive security checklist for Phase 7 of the Gilead School Management System. Use this checklist for regular security audits and before production deployments.

---

## Authentication & Authorization

### Password Security
- [ ] Minimum password length: 8 characters
- [ ] Password complexity requirements enabled
- [ ] Password history: prevent reuse of last 5 passwords
- [ ] Account lockout after 5 failed attempts
- [ ] Password reset requires email verification
- [ ] Session timeout: 30 minutes of inactivity
- [ ] Force logout on password change

### Multi-Factor Authentication (MFA)
- [ ] django-otp installed and configured
- [ ] OTPMiddleware added to MIDDLEWARE
- [ ] MFA setup page accessible at `/authentication/mfa/setup/`
- [ ] QR code generation works correctly
- [ ] TOTP verification tested with Google Authenticator
- [ ] MFA can be disabled by user with confirmation
- [ ] Admin users encouraged/required to use MFA
- [ ] Backup codes available for account recovery

### Session Management
- [ ] SESSION_COOKIE_SECURE = True (production)
- [ ] SESSION_COOKIE_HTTPONLY = True
- [ ] SESSION_COOKIE_SAMESITE = 'Lax'
- [ ] CSRF_COOKIE_SECURE = True (production)
- [ ] CSRF_COOKIE_HTTPONLY = True

### Access Control
- [ ] Role-Based Access Control (RBAC) implemented
- [ ] Permissions checked on all sensitive views
- [ ] API endpoints require authentication
- [ ] File uploads restricted by user role
- [ ] Direct object references protected (IDOR prevention)

---

## Input Validation & Sanitization

### SQL Injection Prevention
- [ ] All database queries use Django ORM (parameterized)
- [ ] No raw SQL queries with string concatenation
- [ ] User input never directly interpolated into SQL
- [ ] Test: Try SQL injection in search/filter fields

### Cross-Site Scripting (XSS) Prevention
- [ ] All user input escaped in templates ({{ }}, not {% raw %})
- [ ] Rich text fields use bleach for sanitization
- [ ] JavaScript safely handles user data (no innerHTML with untrusted data)
- [ ] Content-Security-Policy header configured
- [ ] Test: Try `<script>alert('XSS')</script>` in input fields

### Command Injection Prevention
- [ ] No shell commands with user input
- [ ] File operations use safe path joining (os.path.join)
- [ ] subprocess calls avoid shell=True
- [ ] Test: Try `; rm -rf /` in filename inputs

### Path Traversal Prevention
- [ ] File downloads validate path stays within MEDIA_ROOT
- [ ] No direct file access via URL parameters
- [ ] File upload paths sanitized
- [ ] Test: Try `../../etc/passwd` in file paths

---

## Data Protection

### Sensitive Data Storage
- [ ] Passwords hashed with PBKDF2/Argon2 (Django default)
- [ ] API keys stored in environment variables (.env)
- [ ] No hardcoded secrets in code
- [ ] Database backups encrypted
- [ ] Personal data (PII) identified and protected

### Data Transmission
- [ ] HTTPS enforced (SECURE_SSL_REDIRECT = True)
- [ ] HSTS header enabled (SECURE_HSTS_SECONDS = 31536000)
- [ ] TLS 1.2+ only (no SSL, TLS 1.0/1.1)
- [ ] API calls to external services use HTTPS
- [ ] Sensitive data not logged

### Data Access Logging
- [ ] Login attempts logged (success & failure)
- [ ] Admin actions logged (AuditLog model)
- [ ] File downloads logged
- [ ] API access logged
- [ ] Sensitive data access tracked

---

## Network & Infrastructure

### Firewall & Network
- [ ] Only necessary ports open (80, 443)
- [ ] Database not directly accessible from internet
- [ ] SSH keys used instead of passwords
- [ ] IP whitelisting for admin panel (if applicable)
- [ ] DDoS protection enabled (Cloudflare, AWS Shield)

### Rate Limiting
- [ ] django-ratelimit configured
- [ ] Login endpoint: 5 attempts per minute per IP
- [ ] API endpoints: 30 requests per minute per user
- [ ] Public APIs: 100 requests per hour per IP
- [ ] Test: Rapid-fire requests trigger 429 error

### Server Configuration
- [ ] DEBUG = False in production
- [ ] SECRET_KEY is strong and unique
- [ ] ALLOWED_HOSTS properly configured
- [ ] X-Frame-Options: DENY
- [ ] X-Content-Type-Options: nosniff
- [ ] Referrer-Policy: same-origin

---

## Application Logic

### Business Logic Vulnerabilities
- [ ] Payment amounts cannot be manipulated client-side
- [ ] Grade changes require proper authorization
- [ ] File size limits enforced (max 10MB)
- [ ] Concurrent transaction handling tested
- [ ] Race conditions prevented (select_for_update)

### API Security
- [ ] API authentication required (Token/Session)
- [ ] API rate limiting per endpoint
- [ ] API responses don't leak sensitive data
- [ ] CORS properly configured (no wildcard *)
- [ ] API versioning implemented

---

## Third-Party Integrations

### SMS/WhatsApp APIs
- [ ] API health check command works: `python manage.py check_api_health`
- [ ] Webhooks verify signature/token
- [ ] Webhook retry logic tested (exponential backoff)
- [ ] API credentials rotated quarterly
- [ ] Test: Send test SMS/WhatsApp message

### Payment Gateways
- [ ] Webhook signatures verified
- [ ] No payment data stored (PCI-DSS compliance)
- [ ] Payment status validated server-side
- [ ] Refund process requires admin approval

### GeoIP2 Database
- [ ] MaxMind license key configured
- [ ] Database auto-updates weekly
- [ ] Country-based blocking tested
- [ ] Fallback behavior defined (block or allow)

---

## Error Handling & Logging

### Error Messages
- [ ] Generic error messages to users (no stack traces)
- [ ] Detailed errors logged server-side only
- [ ] 404/500 pages don't reveal system info
- [ ] Logs don't contain passwords or tokens

### Monitoring & Alerting
- [ ] Failed login attempts trigger alerts
- [ ] Multiple 500 errors trigger alerts
- [ ] Slack webhook for security events
- [ ] Log rotation configured (max 100MB per file)

---

## Compliance & Privacy

### GDPR/Data Privacy
- [ ] Privacy policy published
- [ ] User consent for data collection
- [ ] Data export functionality (user can download data)
- [ ] Data deletion process (right to be forgotten)
- [ ] Data retention policy documented

### Audit Trail
- [ ] All admin actions logged
- [ ] Logs immutable (append-only)
- [ ] Audit logs retained for 1 year
- [ ] Regular audit log reviews scheduled

---

## Testing & Validation

### Security Testing Tools
- [ ] Run: `python manage.py check --deploy`
- [ ] Run: `bandit -r apps/` (Python security linter)
- [ ] Run: `safety check` (dependency vulnerability scan)
- [ ] Run OWASP ZAP scan on staging
- [ ] Run regression tests: `python manage.py test_core_workflows`

### Manual Testing
- [ ] Try SQL injection in all input fields
- [ ] Try XSS in all input fields
- [ ] Try CSRF attack (remove csrf_token)
- [ ] Try accessing other users' data (IDOR)
- [ ] Try uploading malicious files (.php, .exe)
- [ ] Try brute-force login attack
- [ ] Try session hijacking (steal cookie)

### Penetration Testing
- [ ] Quarterly penetration test scheduled
- [ ] Findings documented and prioritized
- [ ] Critical vulnerabilities patched within 24 hours
- [ ] High vulnerabilities patched within 1 week

---

## Deployment Security

### Pre-Deployment
- [ ] All dependencies up to date: `pip list --outdated`
- [ ] No DEBUG = True in production code
- [ ] Environment variables properly set (.env loaded)
- [ ] Database migrations tested on staging
- [ ] Backup and restore tested

### Post-Deployment
- [ ] SSL certificate valid and auto-renews
- [ ] Health checks passing: `python manage.py check_api_health`
- [ ] Monitor logs for first 24 hours
- [ ] Rollback plan documented and tested

---

## Incident Response

### Preparation
- [ ] Security incident response plan documented
- [ ] Contact list for security team
- [ ] Escalation procedures defined
- [ ] Backup restoration tested

### Detection
- [ ] Real-time monitoring enabled
- [ ] Alerting configured (Slack, email)
- [ ] Log analysis automated (ELK, Splunk)

### Response
- [ ] Incident response playbook available
- [ ] Communication templates prepared
- [ ] Forensics tools ready (logs, snapshots)

---

## Checklist Summary

**Pass Criteria**: All items checked ✓  
**Review Frequency**: Quarterly (or before major releases)  
**Responsible Team**: DevOps + Security Team  
**Last Review**: [DATE]  
**Next Review**: [DATE + 3 months]

---

## Tools & Resources

### Security Testing Tools
- **Bandit**: Python security linter
  ```bash
  pip install bandit
  bandit -r apps/ -f html -o security-report.html
  ```

- **Safety**: Dependency vulnerability scanner
  ```bash
  pip install safety
  safety check --json
  ```

- **OWASP ZAP**: Web application security scanner
  - Download: https://www.zaproxy.org/

### Reference Documentation
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- Django Security: https://docs.djangoproject.com/en/stable/topics/security/
- CWE Top 25: https://cwe.mitre.org/top25/

---

**Document Version**: 1.0  
**Phase**: 7 (Security & MFA)  
**Status**: Active  
**Last Updated**: 2025-01-19
