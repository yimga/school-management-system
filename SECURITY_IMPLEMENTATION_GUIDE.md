# 🔐 SECURITY IMPLEMENTATION GUIDE
**Gilead Tech High - Code Changes & Configuration Updates**

---

## PRIORITY 1: Critical Fixes (Implement This Week)

### 1. Fix Hardcoded SECRET_KEY Fallback

**Current Issue (CRITICAL):**
```python
# DANGEROUS - Never do this!
if DEBUG:
    SECRET_KEY = "dev-only-change-in-production"  # ❌ HARDCODED
else:
    raise ImproperlyConfigured("SECRET_KEY must be set")
```

**Fix:**
```python
# config/settings.py
import os
from django.core.management.utils import get_random_secret_key

# Remove ALL fallback keys
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY and os.getenv('DEBUG', 'False') == 'False':
    # Production must have SECRET_KEY
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable not set. "
        "Generate one: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    )

# For development-only, use a temporary key (expires on restart)
if not SECRET_KEY:
    SECRET_KEY = get_random_secret_key()
    print("⚠️  WARNING: Using temporary SECRET_KEY. Set SECRET_KEY in .env for persistence.")
```

---

### 2. Enforce MFA for Admin Roles

**Add to apps/accounts/models.py:**
```python
from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    # ... existing fields ...
    
    # New MFA fields
    mfa_enabled = models.BooleanField(default=False)
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    mfa_methods = models.JSONField(default=list, blank=True)  # ['totp', 'backup_codes']
    
    @property
    def requires_mfa(self):
        """Check if this user's role requires MFA"""
        return self.role in ['ADMIN', 'IT_ADMIN', 'PRINCIPAL']
    
    def has_active_mfa(self):
        """Check if user has MFA enabled and verified"""
        return self.mfa_enabled and self.mfa_verified_at is not None
```

**Add Middleware (apps/compliance/middleware.py):**
```python
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

class MFARequiredMiddleware:
    """Enforce MFA for privileged roles"""
    
    SKIP_PATHS = [
        '/auth/login/',
        '/auth/logout/',
        '/auth/mfa/setup/',
        '/auth/mfa/verify/',
        '/static/',
        '/media/',
        '/health/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip if user not authenticated
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Skip MFA-related paths
        if any(request.path.startswith(path) for path in self.SKIP_PATHS):
            return self.get_response(request)
        
        # Check if user requires MFA
        if request.user.requires_mfa and not request.user.has_active_mfa():
            return redirect('accounts:setup_mfa')
        
        return self.get_response(request)
```

**Add to settings.py MIDDLEWARE:**
```python
MIDDLEWARE = [
    # ... existing middleware ...
    'apps.compliance.middleware.MFARequiredMiddleware',  # Add before auth
]
```

---

### 3. Implement Password Policy

**Add to config/settings.py:**
```python
# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 12,  # Require 12+ characters
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Password expiry policy
PASSWORD_EXPIRY_DAYS = 90  # Require change every 90 days
PASSWORD_HISTORY_COUNT = 5  # Cannot reuse last 5 passwords

# Session security
SESSION_COOKIE_AGE = 3600  # 1 hour for admins
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
```

**Add to apps/accounts/models.py:**
```python
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    # ... existing fields ...
    
    password_changed_at = models.DateTimeField(auto_now=True)
    password_history = models.JSONField(default=list, blank=True)
    
    def password_expired(self):
        """Check if password needs to be changed"""
        expiry_days = 90 if self.role in ['ADMIN', 'IT_ADMIN'] else 180
        age = timezone.now() - self.password_changed_at
        return age > timedelta(days=expiry_days)
    
    def set_password(self, raw_password):
        """Override to track password history"""
        from django.contrib.auth.hashers import make_password
        
        # Check password hasn't been used recently
        hashed = make_password(raw_password)
        if hashed in self.password_history:
            raise ValidationError("Cannot reuse recent passwords")
        
        # Add to history
        self.password_history.append(hashed)
        if len(self.password_history) > 5:
            self.password_history.pop(0)
        
        super().set_password(raw_password)
```

---

### 4. Add Account Lockout Policy

**Create new model (apps/accounts/models.py):**
```python
from django.utils import timezone
from datetime import timedelta

class LoginAttempt(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='login_attempt')
    failed_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_attempt = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'accounts_login_attempt'
    
    def is_locked(self):
        """Check if account is currently locked"""
        if not self.locked_until:
            return False
        
        if timezone.now() < self.locked_until:
            return True
        
        # Unlock if lockout period expired
        self.failed_attempts = 0
        self.locked_until = None
        self.save()
        return False
    
    def record_failed_attempt(self):
        """Record a failed login attempt"""
        self.failed_attempts += 1
        self.last_failed_attempt = timezone.now()
        
        # Lock account after 5 failed attempts for 30 minutes
        if self.failed_attempts >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=30)
            # Alert security team
            self._send_lockout_alert()
        
        self.save()
    
    def reset_attempts(self):
        """Reset failed attempts on successful login"""
        self.failed_attempts = 0
        self.locked_until = None
        self.last_failed_attempt = None
        self.save()
    
    def _send_lockout_alert(self):
        """Notify security team of account lockout"""
        from django.core.mail import send_mail
        
        send_mail(
            f'Account Locked: {self.user.username}',
            f'User {self.user.username} exceeded login attempts.',
            'security@gileadschool.com',
            ['admin@gileadschool.com'],
        )
```

**Add to authentication view (apps/accounts/views.py):**
```python
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from apps.accounts.models import LoginAttempt

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(username=username)
            attempt = LoginAttempt.objects.get_or_create(user=user)[0]
            
            # Check if account is locked
            if attempt.is_locked():
                return render(request, 'accounts/account_locked.html', {
                    'locked_until': attempt.locked_until
                })
            
            # Attempt authentication
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                attempt.reset_attempts()  # Reset on successful login
                return redirect('portal:dashboard')
            else:
                attempt.record_failed_attempt()
                
                # Alert on repeated failures
                if attempt.failed_attempts >= 3:
                    send_alert(f"Failed login attempts for {username}")
                
                return render(request, 'accounts/login.html', {
                    'error': 'Invalid credentials',
                    'attempts_remaining': 5 - attempt.failed_attempts
                })
        
        except User.DoesNotExist:
            # Generic message to prevent username enumeration
            return render(request, 'accounts/login.html', {
                'error': 'Invalid credentials'
            })
    
    return render(request, 'accounts/login.html')
```

---

## PRIORITY 2: Important Additions (Implement This Month)

### 5. Add Content Security Policy (CSP)

**Install:**
```bash
pip install django-csp
```

**Add to config/settings.py:**
```python
INSTALLED_APPS = [
    # ... existing apps ...
    'csp',
]

MIDDLEWARE = [
    # ... other middleware ...
    'csp.middleware.CSPMiddleware',
]

# Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net")  # Consider removing unsafe-inline
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net", "fonts.googleapis.com")
CSP_IMG_SRC = ("'self'", "data:", "https:", "cdn.jsdelivr.net")
CSP_FONT_SRC = ("'self'", "fonts.gstatic.com", "cdnjs.cloudflare.com")
CSP_CONNECT_SRC = ("'self'", "sentry.io")
CSP_REPORT_URI = ("/api/csp-report/",)
CSP_REPORT_ONLY = False  # Set to True to test without enforcing

# Additional security headers
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_PERMISSIONS_POLICY = {
    'geolocation': '()',
    'microphone': '()',
    'camera': '()',
    'payment': '()',
}
```

---

### 6. Add Audit Log Signing (Tamper Detection)

**Add to apps/compliance/models.py:**
```python
import hmac
import hashlib
from django.db import models
from django.conf import settings

class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    resource = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)
    signature = models.CharField(max_length=256, blank=True)
    
    class Meta:
        db_table = 'compliance_audit_log'
        indexes = [
            models.Index(fields=['timestamp', 'user']),
            models.Index(fields=['action']),
        ]
    
    def sign(self):
        """Create HMAC signature to detect tampering"""
        message = f"{self.user_id}{self.action}{self.resource}{self.timestamp.isoformat()}"
        self.signature = hmac.new(
            settings.SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def verify_signature(self):
        """Verify HMAC signature hasn't been tampered"""
        if not self.signature:
            return False
        
        message = f"{self.user_id}{self.action}{self.resource}{self.timestamp.isoformat()}"
        expected = hmac.new(
            settings.SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(self.signature, expected)
    
    def save(self, *args, **kwargs):
        if not self.signature:
            self.sign()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"
```

---

### 7. Export Audit Logs to SIEM

**Add to apps/compliance/tasks.py (using Celery):**
```python
from celery import shared_task
import requests
import json
from apps.compliance.models import AuditLog
from django.conf import settings

@shared_task
def export_audit_logs_to_siem():
    """Export audit logs to SIEM system (Splunk, ELK, Datadog)"""
    
    siem_webhook = settings.AUDIT_LOG_EXPORT_URL
    if not siem_webhook:
        return
    
    # Get logs from last 5 minutes
    from django.utils import timezone
    from datetime import timedelta
    
    cutoff = timezone.now() - timedelta(minutes=5)
    logs = AuditLog.objects.filter(timestamp__gte=cutoff, exported=False)
    
    for log in logs:
        payload = {
            'timestamp': log.timestamp.isoformat(),
            'user': log.user.username if log.user else 'system',
            'user_id': log.user_id,
            'action': log.action,
            'resource': log.resource,
            'details': log.details,
            'signature': log.signature,
        }
        
        try:
            response = requests.post(
                siem_webhook,
                json=payload,
                headers={
                    'Authorization': f'Bearer {settings.SIEM_API_KEY}',
                    'Content-Type': 'application/json',
                },
                timeout=10,
            )
            
            if response.status_code == 200:
                log.exported = True
                log.save()
        except Exception as e:
            # Log failure but don't stop processing
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to export audit log {log.id}: {str(e)}")
```

---

### 8. Implement File Upload Validation

**Create apps/compliance/validators.py:**
```python
import re
import magic
from django.core.exceptions import ValidationError

class FileUploadValidator:
    """Validate file uploads for security"""
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_MIMES = [
        'application/pdf',
        'image/jpeg',
        'image/png',
        'text/plain',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ]
    
    @staticmethod
    def validate(file):
        """Validate uploaded file"""
        
        # Check file size
        if file.size > FileUploadValidator.MAX_FILE_SIZE:
            raise ValidationError(
                f"File too large (max {FileUploadValidator.MAX_FILE_SIZE / 1024 / 1024:.0f}MB)"
            )
        
        # Check file type by magic bytes (not extension)
        try:
            mime = magic.from_buffer(file.read(1024), mime=True)
            file.seek(0)  # Reset file pointer
            
            if mime not in FileUploadValidator.ALLOWED_MIMES:
                raise ValidationError(
                    f"File type {mime} not allowed. "
                    f"Allowed types: {', '.join(FileUploadValidator.ALLOWED_MIMES)}"
                )
        except Exception as e:
            raise ValidationError(f"Could not verify file type: {str(e)}")
        
        # Check filename
        if not re.match(r'^[a-zA-Z0-9._\-\s]+$', file.name):
            raise ValidationError("Invalid filename characters. Use only letters, numbers, dots, hyphens, underscores, and spaces.")
        
        # Prevent directory traversal
        if '..' in file.name or file.name.startswith('/'):
            raise ValidationError("Invalid filename")
        
        return True
```

**Use in forms (apps/documents/forms.py):**
```python
from django import forms
from apps.compliance.validators import FileUploadValidator

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['file', 'title']
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            FileUploadValidator.validate(file)
        return file
```

---

## PRIORITY 3: Enhanced Security (Implement This Quarter)

### 9. JSON Request/Response Logging with Sensitive Data Masking

**Create apps/compliance/logging_filters.py:**
```python
import logging
import re
import json

class SensitiveDataFilter(logging.Filter):
    """Mask sensitive data in logs"""
    
    PATTERNS = {
        'password': r'[\"\']?password[\"\']?\s*[:=]\s*[\"\']?([^,\"\'}\s]+)',
        'token': r'[\"\']?token[\"\']?\s*[:=]\s*[\"\']?([^,\"\'}\s]{20,})',
        'api_key': r'[\"\']?api[_-]?key[\"\']?\s*[:=]\s*[\"\']?([^,\"\'}\s]{20,})',
        'secret': r'[\"\']?secret[\"\']?\s*[:=]\s*[\"\']?([^,\"\'}\s]{20,})',
        'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        'ssn': r'\b\d{3}[-]?\d{2}[-]?\d{4}\b',
        'email': r'[\w\.-]+@[\w\.-]+\.\w+',
    }
    
    def filter(self, record):
        message = record.getMessage()
        
        for name, pattern in self.PATTERNS.items():
            message = re.sub(
                pattern,
                f'[REDACTED_{name.upper()}]',
                message,
                flags=re.IGNORECASE
            )
        
        # Try to parse as JSON and mask there too
        try:
            data = json.loads(message)
            message = json.dumps(self._mask_dict(data))
        except (json.JSONDecodeError, TypeError):
            pass
        
        record.msg = message
        return True
    
    @staticmethod
    def _mask_dict(obj):
        """Recursively mask sensitive fields in dict"""
        if isinstance(obj, dict):
            return {
                k: '[REDACTED]' if k.lower() in ['password', 'token', 'secret', 'api_key'] else SensitiveDataFilter._mask_dict(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [SensitiveDataFilter._mask_dict(item) for item in obj]
        return obj
```

**Update config/settings.py logging:**
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'mask_sensitive': {
            '()': 'apps.compliance.logging_filters.SensitiveDataFilter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['mask_sensitive'],
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/gilead/app.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
            'filters': ['mask_sensitive'],
            'formatter': 'json' if os.getenv('LOG_JSON') else 'verbose',
        },
    },
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {message}',
            'style': '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(timestamp)s %(level)s %(name)s %(message)s',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if os.getenv('DEBUG') else 'INFO',
            'propagate': False,
        },
    },
}
```

---

## Testing Security Changes

### Run Django Security Checks:
```bash
python manage.py check --deploy
```

### Scan Dependencies:
```bash
pip install safety bandit
safety check requirements.txt
bandit -r apps/ --skip B101  # Skip assert_used checks for tests
```

### Run Tests:
```bash
python manage.py test apps.accounts.tests.AccountSecurityTestCase
python manage.py test apps.compliance.tests.AuditLoggingTestCase
```

---

## Deployment Steps

1. **Update requirements.txt**
   ```bash
   pip freeze > requirements.txt
   ```

2. **Create database migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

3. **Collect static files**
   ```bash
   python manage.py collectstatic --noinput
   ```

4. **Test locally**
   ```bash
   DEBUG=True python manage.py runserver
   ```

5. **Deploy to staging**
   ```bash
   git push origin security-hardening
   # Run CI/CD pipeline
   ```

6. **Deploy to production**
   ```bash
   git merge security-hardening main
   # Follow production deployment checklist
   ```

---

**Status:** 🟢 Ready to Implement  
**Estimated Time:** 3-4 weeks for full implementation  
**Review Date:** July 23, 2026
