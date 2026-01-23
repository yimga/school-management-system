# 🔐 SECURITY QUICK REFERENCE CARD
**Gilead Tech High - One-Page Cheat Sheet**

---

## ⚡ CRITICAL ACTIONS (TODAY)

### 1️⃣ Fix SECRET_KEY in `config/settings.py`
```python
# ❌ REMOVE THIS:
if DEBUG:
    SECRET_KEY = "dev-only-change-in-production"

# ✅ ADD THIS:
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured("Set SECRET_KEY in .env")
```

### 2️⃣ Check `.env` File
```bash
# ✅ Should contain:
SECRET_KEY=<50+ random chars>
DEBUG=False
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# ✅ Should NOT be in git:
echo ".env" >> .gitignore
```

### 3️⃣ Run Django Security Check
```bash
python manage.py check --deploy
```

---

## 🔑 Essential Security Settings

| Setting | Value | Production |
|---------|-------|------------|
| `DEBUG` | False | 🔴 CRITICAL |
| `SECURE_SSL_REDIRECT` | True | 🔴 CRITICAL |
| `SESSION_COOKIE_SECURE` | True | 🔴 CRITICAL |
| `CSRF_COOKIE_SECURE` | True | 🔴 CRITICAL |
| `SECURE_HSTS_SECONDS` | 31536000 | ✅ Set |
| `SECURE_HSTS_PRELOAD` | True | ✅ Set |
| `SECRET_KEY` | Random 50+ | 🔴 CRITICAL |
| `ALLOWED_HOSTS` | Your domains | 🔴 CRITICAL |

---

## 🚨 Top 5 Security Fixes (Priority Order)

1. **Remove Hardcoded SECRET_KEY** → Account compromise risk 🔴
2. **Enforce MFA for Admins** → Unauthorized access risk 🔴
3. **Add Password Policy** → Weak passwords risk 🟠
4. **Implement Account Lockout** → Brute force risk 🟠
5. **Add CSP Headers** → XSS vulnerability risk 🟠

---

## 🔍 Security Validation Checklist

```bash
# ✅ SSL Certificate
openssl s_client -connect school.example.com:443 | grep "Verify return code"

# ✅ Security Headers
curl -I https://school.example.com | grep -i "strict-transport-security\|x-content-type"

# ✅ Dependency Vulnerabilities
pip install safety && safety check

# ✅ Django Deployment
python manage.py check --deploy

# ✅ Rate Limiting (test with 20+ requests)
for i in {1..25}; do curl -X POST https://school.example.com/api/login; done
```

---

## 📋 File Upload Validation Quick Code

```python
# In your form
def clean_file(self):
    file = self.cleaned_data.get('file')
    
    # Check size (10MB max)
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("File too large")
    
    # Check extension (not enough! Use MIME type)
    allowed = ['pdf', 'jpg', 'png', 'txt']
    if file.name.split('.')[-1].lower() not in allowed:
        raise ValidationError("File type not allowed")
    
    return file
```

---

## 🔒 Password Policy Requirements

Enforce in settings:
```python
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
```

**Password Requirements:**
- ✅ Minimum 12 characters
- ✅ Mix of upper & lowercase
- ✅ Include numbers
- ✅ Include special characters
- ✅ No common passwords
- ✅ Not similar to username/email
- ✅ Expire every 90 days (admin)

---

## 🎯 MFA Setup for Admins

```python
# In User model
@property
def requires_mfa(self):
    return self.role in ['ADMIN', 'IT_ADMIN', 'PRINCIPAL']

# In middleware
if user.requires_mfa and not user.mfa_enabled:
    return redirect('setup_mfa')
```

---

## 📊 Rate Limiting Configuration

```python
# In settings.py
RATELIMIT_ENABLE = True
RATELIMIT_FAILED_ATTEMPTS_PER_USER = 10  # Lock after 10 failures
RATELIMIT_FAILED_ATTEMPTS_PER_IP = 20    # Lock IP after 20 failures
RATELIMIT_LOCKOUT_DURATION = 1800         # 30 minutes
```

---

## 🗂️ Audit Logging Quick Start

```python
# All requests automatically logged via middleware
from apps.compliance.models import AccessLog

# View recent activity
AccessLog.objects.filter(status__gte=400).order_by('-timestamp')[:10]

# Alert on suspicious patterns
AccessLog.objects.filter(
    user_id=user_id,
    timestamp__gte=timezone.now() - timedelta(hours=1),
    status__gte=400
).count()  # > 5 is suspicious
```

---

## 🛡️ Essential Security Headers

Add to your response middleware:
```python
response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
response['X-Content-Type-Options'] = 'nosniff'
response['X-Frame-Options'] = 'SAMEORIGIN'
response['X-XSS-Protection'] = '1; mode=block'
response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
response['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'"
```

---

## 🚀 Pre-Production Deployment Checklist

- [ ] `DEBUG=False` in production
- [ ] `SECRET_KEY` is strong and from environment
- [ ] SSL certificate installed and valid
- [ ] `ALLOWED_HOSTS` configured correctly
- [ ] Database user has minimal permissions
- [ ] Backups configured and tested
- [ ] Monitoring (Sentry) configured
- [ ] Email alerts working
- [ ] Firewall rules in place
- [ ] Rate limiting tested
- [ ] All security headers present
- [ ] Admin MFA enabled
- [ ] Password policy enforced
- [ ] Logs not containing sensitive data

---

## 🆘 Emergency Security Procedures

**If Compromised:**
1. Take site offline immediately
2. Rotate all secrets (SECRET_KEY, database password, API keys)
3. Reset all admin passwords
4. Review audit logs for unauthorized access
5. Change all credentials
6. Scan for malware/backdoors
7. Notify all users
8. Deploy security patches

**Contact:**
- Security Team: security@gileadschool.com
- On-Call: +1-XXX-XXX-XXXX
- Executive: executive@gileadschool.com

---

## 📚 Documentation Links

| Document | Purpose |
|----------|---------|
| [SECURITY_AUDIT_REPORT.md](#) | Detailed audit findings |
| [SECURITY_HARDENING_CHECKLIST.md](#) | 60+ action items |
| [ENV_PRODUCTION_TEMPLATE.md](#) | Environment variables |
| [SECURITY_IMPLEMENTATION_GUIDE.md](#) | Code examples & how-tos |
| [SECURITY_SUMMARY_AND_ROADMAP.md](#) | Executive summary |

---

## 🎓 Quick Security Tips

1. **Never commit secrets to git** → Use `.env` instead
2. **Always use HTTPS** → No HTTP in production
3. **Rotate secrets regularly** → Every 6 months minimum
4. **Log everything** → Helps with incident response
5. **Test backups** → Restore at least monthly
6. **Keep dependencies updated** → Run `pip install -U` weekly
7. **Use strong passwords** → 12+ chars with mixed case/numbers
8. **Enable MFA everywhere** → Especially for admins
9. **Monitor logs daily** → Watch for failed logins
10. **Have an incident plan** → Practice quarterly

---

## ⏱️ Time Estimates

| Task | Effort | Timeline |
|------|--------|----------|
| Fix SECRET_KEY | 15 min | Today |
| Enforce MFA | 2-3 hours | This week |
| Password policy | 2-3 hours | This week |
| CSP headers | 2-3 hours | This week |
| Account lockout | 3-4 hours | This week |
| Audit log signing | 3-4 hours | This month |
| File upload validation | 2-3 hours | This month |
| SIEM integration | 4-6 hours | This month |
| Full testing | 8-12 hours | This month |

**Total: ~30 hours over 4 weeks** = ~2 hours/day

---

## 🏆 Security Maturity Levels

**Current:** 3.5/5 (Managed)  
**Target:** 4.5/5 (Optimized)  

| Level | Description |
|-------|-------------|
| 1 | Ad hoc (no formal processes) |
| 2 | Repeatable (basic controls) |
| 3 | Defined (documented standards) | ← **YOU ARE HERE** |
| 4 | Managed (metrics & monitoring) |
| 5 | Optimized (continuous improvement) |

---

## 📞 Support

**Questions on these security recommendations?**
- Review: [SECURITY_AUDIT_REPORT.md](#)
- Implementation: [SECURITY_IMPLEMENTATION_GUIDE.md](#)
- Reference: Django Security Docs (https://docs.djangoproject.com/en/5.2/topics/security/)

---

**Last Updated:** January 23, 2026  
**Valid Until:** July 23, 2026  
**Status:** ✅ Production Ready (with recommendations above)

*"Security is not a destination, it's a journey." - OWASP*
