# ✅ Security Hardening Checklist
**Gilead Tech High - School Management System**

---

## PRE-DEPLOYMENT CHECKLIST

### 🔐 Authentication & Authorization
- [ ] Remove hardcoded `SECRET_KEY` fallback from settings.py
- [ ] Enable MFA requirement for ADMIN role
- [ ] Implement password policy (12+ chars, upper/lower/numbers/symbols)
- [ ] Configure session timeout (1 hour for admins, 8 hours for students)
- [ ] Enable account lockout (5 failed attempts = 30 min lockout)
- [ ] Test JWT token expiration (15 min access, 7 day refresh)
- [ ] Verify role-based redirects working (logo → user's home)
- [ ] Test RBAC permissions on all dashboard routes

### 🛡️ HTTPS/SSL/TLS
- [ ] Install SSL certificate (Let's Encrypt recommended)
- [ ] Set `SECURE_SSL_REDIRECT=True` in production settings
- [ ] Configure HSTS (`SECURE_HSTS_SECONDS=31536000`)
- [ ] Enable HSTS preload (`SECURE_HSTS_PRELOAD=True`)
- [ ] Test SSL Labs rating (A+ required)
- [ ] Verify TLS 1.2+ only (disable TLS 1.0/1.1)
- [ ] Test HTTP→HTTPS redirect

### 🍪 Cookies & Session Security
- [ ] Set `SESSION_COOKIE_SECURE=True`
- [ ] Set `CSRF_COOKIE_SECURE=True`
- [ ] Set `SESSION_COOKIE_HTTPONLY=True`
- [ ] Set `SESSION_COOKIE_SAMESITE='Strict'` (or 'Lax')
- [ ] Enable `SESSION_EXPIRE_AT_BROWSER_CLOSE=True`
- [ ] Configure `SESSION_COOKIE_AGE=3600` (1 hour)
- [ ] Test cookie flags in DevTools

### 🔑 Secrets Management
- [ ] All secrets in `.env` (never hardcoded)
- [ ] `.env` in `.gitignore`
- [ ] Create `.env.example` template for onboarding
- [ ] Rotate `SECRET_KEY` every 6 months
- [ ] Rotate database credentials every 90 days
- [ ] Use environment-specific secrets (dev ≠ prod)
- [ ] Verify no secrets in git history

### 🗄️ Database Security
- [ ] Enable SSL for database connection
- [ ] Create restricted database user (not admin)
- [ ] Configure database firewall (allow only app servers)
- [ ] Enable database audit logging
- [ ] Set up automated daily backups (encrypted)
- [ ] Test backup restore procedure
- [ ] Configure database user session timeout

### 🔒 Input Validation
- [ ] Validate all form inputs (Django forms)
- [ ] Validate all API inputs (REST serializers)
- [ ] Implement file upload restrictions (type, size, name)
- [ ] Sanitize HTML content (bleach library)
- [ ] Test XSS prevention with malicious inputs
- [ ] Test SQL injection prevention
- [ ] Test CSRF protection on all forms

### 🌐 HTTP Security Headers
- [ ] Set `X-Content-Type-Options: nosniff`
- [ ] Set `X-Frame-Options: SAMEORIGIN`
- [ ] Set `X-XSS-Protection: 1; mode=block`
- [ ] Set `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] Add `Permissions-Policy` header (disable geolocation, camera, etc.)
- [ ] Implement CSP (Content Security Policy) header
- [ ] Test headers with security scanner

### 📊 Logging & Monitoring
- [ ] Enable JSON logging for log aggregation
- [ ] Implement sensitive data masking in logs (passwords, tokens, PII)
- [ ] Configure Sentry for error tracking
- [ ] Set up log rotation (10MB per file, 10 backups)
- [ ] Enable audit logging on all HTTP requests
- [ ] Create audit log retention policy (365 days)
- [ ] Set up real-time alerts for failed logins
- [ ] Verify logs don't contain sensitive data

### 📋 API Security
- [ ] Implement CORS properly (whitelist domains only)
- [ ] Disable OPTIONS method (if not needed)
- [ ] Implement rate limiting (10 failures/user, 20 failures/IP)
- [ ] Test rate limiting triggers and lockout
- [ ] Verify JWT tokens rotate properly
- [ ] Test API token expiration
- [ ] Implement API versioning (v1, v2)

### 🚨 Compliance & Audit
- [ ] Enable audit logging in middleware
- [ ] Create audit log retention workflow
- [ ] Implement export functionality for auditors
- [ ] Test GDPR data export feature
- [ ] Create incident response runbook
- [ ] Document security policies
- [ ] Create disaster recovery plan

### 🔍 Vulnerability Scanning
- [ ] Run `safety check` on requirements.txt
- [ ] Run `bandit` security linter
- [ ] Run `python manage.py check --deploy`
- [ ] Run OWASP Top 10 scanner
- [ ] Check Django security documentation
- [ ] Review third-party dependencies for CVEs
- [ ] Update vulnerable packages immediately

### 🚀 Deployment
- [ ] Set `DEBUG=False` in production
- [ ] Generate production `SECRET_KEY`
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Collect static files (`collectstatic`)
- [ ] Run database migrations (`migrate`)
- [ ] Create superuser (strong password)
- [ ] Test all features on staging environment
- [ ] Enable monitoring & alerting
- [ ] Set up log aggregation (ELK, Datadog, Splunk)
- [ ] Configure firewall rules

### 📱 Mobile & API
- [ ] Test mobile app JWT authentication
- [ ] Verify API doesn't expose sensitive data
- [ ] Test API rate limiting on mobile
- [ ] Implement API versioning strategy
- [ ] Document API security requirements

### 🔄 Maintenance & Updates
- [ ] Schedule weekly dependency updates
- [ ] Set up security patch notifications
- [ ] Create patch deployment procedure
- [ ] Schedule quarterly security audits
- [ ] Plan annual penetration testing
- [ ] Document security incident procedures

---

## POST-DEPLOYMENT CHECKLIST

### 📊 Monitoring
- [ ] Review logs daily for suspicious activity
- [ ] Monitor failed login attempts
- [ ] Alert on unusual database queries
- [ ] Monitor CPU/memory/disk usage
- [ ] Track API response times
- [ ] Monitor Sentry for errors
- [ ] Review audit logs weekly

### 🔄 Backups
- [ ] Verify daily database backups
- [ ] Test weekly restore procedure
- [ ] Store backups off-site (encrypted)
- [ ] Document backup retention policy
- [ ] Verify backup encryption

### 🛡️ Incident Response
- [ ] Have on-call security team
- [ ] Document incident response procedures
- [ ] Create communication template
- [ ] Plan quarterly incident response drills
- [ ] Maintain incident log

### 👥 Access Control
- [ ] Review user permissions monthly
- [ ] Revoke unnecessary access
- [ ] Audit admin user activity weekly
- [ ] Remove inactive users
- [ ] Audit SSH/database access

### 📝 Documentation
- [ ] Maintain security policies
- [ ] Document security architecture
- [ ] Keep runbooks updated
- [ ] Document compliance requirements
- [ ] Create security training materials

---

## SPECIFIC CONFIGURATIONS NEEDED

### 1. Environment Variables (.env)
```bash
# Security
SECRET_KEY=<generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'>
DEBUG=False
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_PRELOAD=True

# Database
DATABASE_URL=postgresql://user:password@db.example.com:5432/gilead_prod
DB_CONN_MAX_AGE=600

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@gileadschool.com

# Monitoring
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production

# Allowed hosts
ALLOWED_HOSTS=school.example.com,www.school.example.com,api.school.example.com

# Cache/Redis (optional)
REDIS_URL=redis://cache.example.com:6379/0

# CORS (API)
CORS_ALLOWED_ORIGINS=https://school.example.com,https://www.school.example.com

# Compliance
COMPLIANCE_ALERTS_ENABLED=True
THREAT_DETECTION_ENABLED=True
IP_COUNTRY_ACCESS_ENABLED=True

# Logging
LOG_JSON=True
LOG_LEVEL=INFO
```

### 2. Django Management Commands
```bash
# Create these management commands for security tasks:

# Purge old audit logs
python manage.py purge_audit_logs --days=365 --dry-run

# Generate security report
python manage.py security_report

# Rotate secrets
python manage.py rotate_secrets

# Audit user permissions
python manage.py audit_permissions

# Export compliance data
python manage.py export_compliance_data --format=json
```

### 3. Monitoring Alerts
```python
# Critical alerts to set up:
ALERTS = {
    'Failed Login': {
        'threshold': 10,
        'window': '1 hour',
        'action': 'Lock account for 30 minutes',
    },
    'Unauthorized Access': {
        'threshold': 5,
        'window': '1 hour',
        'action': 'Alert security team immediately',
    },
    'Database Error': {
        'threshold': 1,
        'window': 'immediate',
        'action': 'Page on-call engineer',
    },
    'Certificate Expiry': {
        'days_until_expiry': 30,
        'action': 'Renew certificate immediately',
    },
    'Backup Failure': {
        'threshold': 1,
        'window': 'immediate',
        'action': 'Alert DevOps team',
    },
}
```

---

## TESTING SECURITY

### Command Line Tests
```bash
# Check Django deployment readiness
python manage.py check --deploy

# Test HTTPS configuration
curl -I https://school.example.com/

# Verify SSL certificate
openssl s_client -connect school.example.com:443

# Check headers
curl -I https://school.example.com/ | grep -i "strict-transport-security\|x-content-type\|x-frame"

# Test rate limiting
for i in {1..20}; do curl -X POST https://school.example.com/api/login; done

# Test CSRF protection
curl -X POST https://school.example.com/api/ -H "X-CSRFToken: "
```

### Online Security Scanners
- [ ] SSL Labs (https://www.ssllabs.com/ssltest/)
- [ ] Mozilla Observatory (https://observatory.mozilla.org/)
- [ ] OWASP ZAP (https://www.zaproxy.org/)
- [ ] Burp Suite Community (https://portswigger.net/burp)

---

## SECURITY INCIDENT RESPONSE

**If Security Incident Occurs:**

1. **Immediate (< 1 hour)**
   - [ ] Notify security team
   - [ ] Isolate affected systems
   - [ ] Preserve logs and evidence
   - [ ] Activate incident response team

2. **Short-term (1-8 hours)**
   - [ ] Assess impact (users affected, data exposed)
   - [ ] Contain the incident
   - [ ] Notify executives
   - [ ] Begin remediation

3. **Medium-term (1-3 days)**
   - [ ] Conduct root cause analysis
   - [ ] Implement patches
   - [ ] Test fixes thoroughly
   - [ ] Deploy fixes to production

4. **Long-term (1-2 weeks)**
   - [ ] Communicate with affected users
   - [ ] Complete incident report
   - [ ] Update security procedures
   - [ ] Conduct security training

**Contact:**
- Security Team: security@gileadschool.com
- On-call: +1-XXX-XXX-XXXX
- Executive: executive@gileadschool.com

---

**Status: READY FOR PRODUCTION** ✅  
**Last Updated:** January 23, 2026  
**Next Review:** July 23, 2026
