# .env.example
# NEVER commit actual .env file to git
# Copy this file to .env and fill in real values for development
# Use environment-specific secrets for production

# ============================================================================
# CORE DJANGO SETTINGS
# ============================================================================

# Secret Key (Generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
# Minimum 50 characters, change every 6 months
SECRET_KEY=your-super-secret-key-min-50-chars-here-change-every-6-months

# Debug mode - NEVER True in production
DEBUG=False

# Environment indicator
ENVIRONMENT=production  # Options: development, staging, production

# Allowed hosts (comma-separated)
ALLOWED_HOSTS=school.example.com,www.school.example.com,api.school.example.com

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# PostgreSQL connection string
# Format: postgresql://user:password@host:port/database
DATABASE_URL=postgresql://app_user:secure_password_123@db.example.com:5432/gilead_prod

# Alternative individual settings (if not using DATABASE_URL)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=gilead_prod
DB_USER=app_user
DB_PASSWORD=secure_password_123
DB_HOST=db.example.com
DB_PORT=5432

# Connection pooling
DB_CONN_MAX_AGE=600

# ============================================================================
# SECURITY SETTINGS
# ============================================================================

# SSL/HTTPS
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS=31536000  # 1 year in production
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True

# XSS and clickjacking protection
SECURE_BROWSER_XSS_FILTER=True
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS=SAMEORIGIN

# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

# Email backend
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend

# SMTP server details
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-specific-password  # NOT your Gmail password!

# Default sender email
DEFAULT_FROM_EMAIL=noreply@gileadschool.com

# Admin email for error notifications
ADMIN_EMAIL=admin@gileadschool.com

# ============================================================================
# REDIS & CACHING
# ============================================================================

# Redis URL (optional but recommended for production)
REDIS_URL=redis://cache.example.com:6379/0

# Alternative individual settings
REDIS_HOST=cache.example.com
REDIS_PORT=6379
REDIS_PASSWORD=redis_password_123
REDIS_DB=0

# Cache timeout (in seconds)
CACHE_TIMEOUT=300

# ============================================================================
# MONITORING & ERROR TRACKING
# ============================================================================

# Sentry for error tracking and performance monitoring
SENTRY_DSN=https://examplekey@sentry.io/1234567

# Sentry environment
SENTRY_ENVIRONMENT=production

# Sentry sample rate (0.0-1.0, lower for production to reduce noise)
SENTRY_TRACES_SAMPLE_RATE=0.05

# ============================================================================
# AUTHENTICATION & MFA
# ============================================================================

# JWT Settings
JWT_SECRET_KEY=your-jwt-secret-key-min-50-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_LIFETIME=900  # 15 minutes (in seconds)
JWT_REFRESH_TOKEN_LIFETIME=604800  # 7 days (in seconds)

# OTP/TOTP settings
OTP_ISSUER_NAME=Gilead Tech High

# ============================================================================
# RATE LIMITING & SECURITY
# ============================================================================

# Rate limiting
RATELIMIT_ENABLE=True
RATELIMIT_USE_CACHE=default
RATELIMIT_FAILED_ATTEMPTS_PER_USER=10
RATELIMIT_FAILED_ATTEMPTS_PER_IP=20

# Threat detection
THREAT_DETECTION_ENABLED=True
THREAT_DETECTION_FAILED_LOGIN_WINDOW=3600  # 1 hour
THREAT_DETECTION_AFTER_HOURS_THRESHOLD=5
THREAT_DETECTION_AFTER_HOURS_START=22  # 10 PM
THREAT_DETECTION_AFTER_HOURS_END=6  # 6 AM

# IP/Country access control
IP_COUNTRY_ACCESS_ENABLED=False  # Enable if you want geo-blocking
BLOCKED_COUNTRIES=KP,IR,SY  # North Korea, Iran, Syria (ISO-3166-1 alpha-2)

# ============================================================================
# COMPLIANCE & AUDITING
# ============================================================================

# Enable compliance alerts
COMPLIANCE_ALERTS_ENABLED=True

# Data retention policies (in days)
DATA_RETENTION_AUDIT_LOG_DAYS=365
DATA_RETENTION_ACCESS_LOG_DAYS=180
DATA_RETENTION_SESSION_DAYS=90
DATA_RETENTION_REPORTS_DAYS=365

# Audit log export (optional)
AUDIT_LOG_EXPORT_ENABLED=False
AUDIT_LOG_EXPORT_URL=https://splunk.example.com/api/events

# ============================================================================
# LOGGING
# ============================================================================

# Log level
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# JSON logging (for log aggregation)
LOG_JSON=True

# Log file location
LOG_FILE_PATH=/var/log/gilead_school/app.log

# ============================================================================
# CORS & API SETTINGS
# ============================================================================

# CORS allowed origins (comma-separated)
CORS_ALLOWED_ORIGINS=https://school.example.com,https://www.school.example.com

# API rate limiting
API_RATE_LIMIT=1000/hour

# ============================================================================
# THIRD-PARTY INTEGRATIONS
# ============================================================================

# Slack notifications (for alerts)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Slack for compliance alerts
SLACK_COMPLIANCE_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/COMPLIANCE/WEBHOOK

# ============================================================================
# PAYMENT GATEWAY (if applicable)
# ============================================================================

# Stripe (if using for payments)
STRIPE_PUBLIC_KEY=pk_live_xxxxx
STRIPE_SECRET_KEY=sk_live_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx

# ============================================================================
# EXTERNAL SERVICES
# ============================================================================

# SMS provider (for OTP)
SMS_PROVIDER=twilio  # Options: twilio, vonage, etc.
SMS_ACCOUNT_SID=AC...
SMS_AUTH_TOKEN=your_token_here
SMS_FROM_NUMBER=+1234567890

# ============================================================================
# FEATURE FLAGS
# ============================================================================

# Enable/disable features
FEATURE_MFA_ENABLED=True
FEATURE_API_ENABLED=True
FEATURE_REPORT_EXPORT_ENABLED=True
FEATURE_BULK_OPERATIONS_ENABLED=True

# ============================================================================
# BACKUP & DISASTER RECOVERY
# ============================================================================

# S3 bucket for backup storage
S3_BUCKET_NAME=gilead-school-backups
S3_ACCESS_KEY_ID=your_aws_access_key
S3_SECRET_ACCESS_KEY=your_aws_secret_key
S3_REGION=us-east-1

# Backup frequency (in hours)
BACKUP_FREQUENCY=24

# ============================================================================
# ADMIN PANEL
# ============================================================================

# Django admin path (security through obscurity - optional)
ADMIN_URL=admin/  # Change to something like: /security/admin/ or /panel/

# ============================================================================
# GUNICORN SETTINGS (if using Gunicorn)
# ============================================================================

GUNICORN_WORKERS=4
GUNICORN_TIMEOUT=30
GUNICORN_BIND=127.0.0.1:8000

# ============================================================================
# TIMEZONE & LOCALIZATION
# ============================================================================

TIME_ZONE=UTC
LANGUAGE_CODE=en-us

# ============================================================================
# SESSION & COOKIE SETTINGS
# ============================================================================

# Session cookie settings
SESSION_ENGINE=django.contrib.sessions.backends.db
SESSION_COOKIE_AGE=3600  # 1 hour (in seconds)
SESSION_EXPIRE_AT_BROWSER_CLOSE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax  # Options: Lax, Strict

# CSRF cookie settings
CSRF_COOKIE_AGE=31449600  # 1 year
CSRF_COOKIE_HTTPONLY=False  # JavaScript needs to read for AJAX
CSRF_COOKIE_SAMESITE=Lax

# ============================================================================
# PRODUCTION DEPLOYMENT CHECKLIST
# ============================================================================

# Before deploying, verify:
# ✅ DEBUG=False
# ✅ SECRET_KEY is set and strong
# ✅ DATABASE_URL is configured
# ✅ SECURE_SSL_REDIRECT=True
# ✅ EMAIL_HOST_PASSWORD uses app-specific password (not Gmail password)
# ✅ SENTRY_DSN is configured
# ✅ ALLOWED_HOSTS includes your domain
# ✅ All password fields use strong values (min 20 characters)
# ✅ Redis is configured and running
# ✅ SSL certificate is installed
# ✅ Backups are configured and tested
# ✅ Monitoring and alerts are set up
# ✅ Log rotation is configured
# ✅ Firewall rules are in place

# ============================================================================
# NOTES
# ============================================================================

# Security Best Practices:
# 1. Never commit .env file to version control
# 2. Use different secrets for dev, staging, and production
# 3. Rotate secrets regularly (every 6 months minimum)
# 4. Use strong passwords (min 20 characters with mixed case, numbers, symbols)
# 5. Store backup copies of secrets securely (password manager, vault)
# 6. Enable MFA on all accounts that manage these secrets
# 7. Audit who has access to these secrets
# 8. Use environment-specific secret management (AWS Secrets Manager, HashiCorp Vault)
# 9. Never share secrets via email or chat
# 10. Immediately rotate secrets if exposed

# For AWS Secrets Manager:
# aws secretsmanager create-secret --name gilead/prod/env --secret-string file:/.env

# For HashiCorp Vault:
# vault kv put secret/gilead/prod @.env
