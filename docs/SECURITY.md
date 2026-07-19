# Security Posture

RunMyCampus security and compliance posture. This is the canonical document for
vendor questionnaires, RFP responses, and customer due-diligence reviews.
Last reviewed: 2026-05-11.

---

## 1. Compliance frameworks

| Framework | Status | Notes |
|---|---|---|
| **GDPR** | In production | DSR pipeline (`apps.compliance.ConsentRequest/Record`, `ExportJob`, `EraseRequest`). Data-residency tagging on tenant config. |
| **FERPA** (US student records) | Partial | Audit log captures access; tenant-admin UI for "who saw this record" is on the Pass 6 roadmap. `FerpaDisclosureLog` model on Pass 7 roadmap. |
| **COPPA** (US students under 13) | Partial | Parental-consent flow exists in `apps.compliance.ConsentRequest`. Age-gate on student record entry pending. |
| **SOC 2 Type II** | Pre-audit | All required logical controls implemented (see §3-§9). External auditor not yet engaged. Target: audit window opens after first paid enterprise tenant. |
| **ISO 27001** | Pre-audit | Same control surface as SOC 2. Statement of Applicability (SoA) draft to be authored alongside SOC 2 engagement. |
| **PCI-DSS** | Out of scope (SAQ A) | We never store, process, or transmit PAN. All card data goes directly to Stripe / Paystack / Flutterwave hosted fields. We are PCI-DSS SAQ-A eligible. |
| **WCAG 2.2 AA / ADA Section 508** | Tracked | See [`ACCESSIBILITY.md`](ACCESSIBILITY.md) and [`ACCESSIBILITY_WCAG.md`](ACCESSIBILITY_WCAG.md). Outstanding items in the Pass 6 roadmap. |
| **KHDA (UAE)** | Roadmap (Pass 7) | Inspection-report writer modelled but not yet implemented. |
| **Ed-Fi / CEDS** (US K-12 SIS interop) | Partial | Adapters exist (`apps/interop/edfi/`, `apps/interop/ceds/`). Pass 5 fixed grade-letter mapping to honor tenant grading scale. Per-state report writer pending. |

## 2. Data classification

| Class | Examples | Encryption at rest | Encryption in transit | Access controls |
|---|---|---|---|---|
| **Tier 0 — Public** | Marketing pages, blog | n/a | TLS 1.2+ | Anonymous |
| **Tier 1 — Internal** | Aggregate metrics, anonymized stats | Database AES-256 (Postgres at rest) | TLS 1.2+ | Authenticated users |
| **Tier 2 — Confidential** | Student names, contact details, attendance, grades | Postgres at rest + tenant schema isolation (django-tenants) | TLS 1.2+ | Tenant-scoped, role-gated |
| **Tier 3 — Sensitive** | Health records, IEPs, financial records, payment data | Postgres at rest + field-level isolation; payment fields tokenized via Stripe / Paystack | TLS 1.2+ | Restricted role + per-record audit |

All tenant data lives in tenant-scoped schemas (django-tenants schema-per-tenant
when `USE_DJANGO_TENANTS=1`, otherwise tenant-scoped row-level via `school_id`
FKs with RLS policies — see `apps/siteconfig/migrations/0129_rls_policy_default_deny.py`).
Cross-tenant query attempts return zero rows by Postgres RLS, not by ORM convention.

## 3. Application security controls

Source-of-truth: `config/settings.py` lines 117, 251-296, 633-707, 1448-1505.

### Transport
- TLS 1.2+ enforced via `SECURE_SSL_REDIRECT=1` in production.
- HSTS: 1 year (`SECURE_HSTS_SECONDS=31536000`) + subdomains + preload.
- `SECURE_PROXY_SSL_HEADER` honors `X-Forwarded-Proto` from the Render edge.

### Cookies
- `SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1`.
- `SESSION_COOKIE_HTTPONLY=1`, `CSRF_COOKIE_HTTPONLY=1`.
- `SESSION_COOKIE_SAMESITE=Lax`, `CSRF_COOKIE_SAMESITE=Lax`.
- Separate cookie names for the manager surface (`rmc_manager_sessionid`, `rmc_manager_csrftoken`) so a compromised tenant session cannot replay against the control plane.

### Response headers
- `X-Frame-Options: DENY`.
- `Referrer-Policy: strict-origin-when-cross-origin`.
- `Cross-Origin-Opener-Policy: same-origin`.
- `Cross-Origin-Resource-Policy: same-site`.
- `X-Content-Type-Options: nosniff`.
- **Content-Security-Policy**: served by `apps.security.csp_middleware.ContentSecurityPolicyMiddleware`. **Enforce mode by default** (`CSP_ENFORCE=1`); set `CSP_ENFORCE=0` to fall back to Report-Only. Per-request nonces are emitted on both `script-src` and `style-src`. Violations post to `/security/csp-report/`. `/admin/`, `/static/`, and `/media/` bypass CSP.

### Authentication
- Password hashing: **Argon2** (`argon2-cffi>=23.1.0`) — preferred over PBKDF2 for new accounts; PBKDF2 fallback verifies legacy hashes and rehashes to Argon2 on next login.
- **MFA**: TOTP via `django-otp>=1.7.0`, WebAuthn/passkeys via `webauthn>=2.0.0`.
- MFA enforcement: per-tenant via `SecurityConfig` (require_mfa_all_staff or role-based).
- Session expiry: `SESSION_COOKIE_AGE` honored; absolute session cap configurable.

### Authorization
- Role-based access via `User.Role` TextChoices enum (`SUPERADMIN`, `ADMIN`, `TEACHER`, `IT_ADMIN`, `PARENT`, `STUDENT`, `STAFF`).
- Tenant scoping enforced at three layers: middleware (`apps.compliance.middleware.AccessControlMiddleware`), ORM querysets (mandatory `school=` filter), and Postgres RLS (`0129_rls_policy_default_deny`).
- Impersonation tracked in `ImpersonationLog` (`apps.siteconfig.migrations.0111`) with reason + ticket + actor.

### Input safety
- All HTML output through Django auto-escape; rendered HTML (announcements, lesson notes) sanitized via `bleach>=6.0.0` allow-list.
- File uploads: tenant-scoped `upload_to=` callables; mime-type and size validation before storage.
- SQL: ORM-only; no raw SQL outside well-reviewed migration data ops.

### Rate limiting
- `django-ratelimit>=4.1.0` decorators on auth endpoints, password reset, magic-link claim, MFA verification, public webhook ingress.
- Per-tenant AI gateway budget (`AI_GATEWAY_BUDGET_REQUESTS_PER_TENANT_DAY`).

### Network / geo controls
- `apps.compliance.middleware.IPCountryAccessMiddleware` blocks requests from blacklisted country codes per `SecurityConfig`.
- Optional `IPWhitelist` model gates admin surfaces by source IP.

## 4. Operational security

### Logging & monitoring (see also: [`OBSERVABILITY.md`](OBSERVABILITY.md))
- **Sentry** wired (`sentry-sdk>=1.40.0`) with tenant-tagging middleware so every error carries `school_id` and `request_id`.
- **Prometheus** request metrics via `apps.observability.middleware.ObservabilityMiddleware`.
- **Structured JSON logs** via `python-json-logger>=2.0.7` — request_id, tenant_id, user_id propagated on every log line.
- **Audit logging middleware** (`apps.compliance.middleware.AuditLoggingMiddleware`) records every HTTP request with status, latency, tenant, user.

### Retention (configurable via env)
| Data | Default retention | Env var |
|---|---|---|
| Audit log | 365 days | `RETENTION_AUDIT_DAYS` |
| Access log | 180 days | `RETENTION_ACCESS_DAYS` |
| Session records | 90 days | `RETENTION_SESSION_DAYS` |
| Report PDFs | 365 days | `RETENTION_REPORT_DAYS` |

### Backups
- Daily Postgres logical dumps + 7-day rolling retention (Render-managed). Cross-region copy to be added before SOC 2 audit window.
- RPO target: 24 hours. RTO target: 4 hours.

### Threat detection
- `THREAT_DETECTION` config block (`config/settings.py:1480-`) defines sliding-window failure thresholds for: failed logins, MFA failures, password resets, suspicious geo-jumps.
- Alerts route to Sentry + optional email/Slack via `apps.security` notifier.

## 5. Vulnerability management

- **SCA**: `pip-audit` run via CI on every PR; `requirements.txt` pinned to upper bounds (e.g. `Django>=5.0,<6.0`).
- **SAST**: `ruff>=0.6.0` (configurable to run security-focused lint rules like `S` series).
- **Pen testing**: To be scheduled annually with an external firm prior to SOC 2 Type II audit window. No engagement yet.
- **Bug bounty**: To launch on HackerOne or Intigriti after first SOC 2 cycle.

## 6. Incident response

- 24/7 on-call rotation TBD (currently founder + lead engineer; will scale with team).
- **Runbook** [`INCIDENT_RESPONSE.md`](INCIDENT_RESPONSE.md) (to be authored; covers detection, triage, customer-comms templates, regulator notification thresholds).
- **Notification SLAs**:
  - GDPR personal-data breach: 72 hours to supervisory authority.
  - Contractual: customer notification within 24 hours of confirmed breach.
- **Forensic preservation**: audit log retention + Sentry retention + Postgres PITR cover post-incident reconstruction.

## 7. Vendor / sub-processor inventory

| Sub-processor | Purpose | Data class | Region |
|---|---|---|---|
| Render | Application hosting, Postgres | Tier 0-3 | Oregon (US) by default; EU region on request |
| Sentry | Error monitoring | Tier 1 (no PII; `send_default_pii=False`) | US |
| Stripe | Card payments | Tier 3 (tokenized; we never see PAN) | Global |
| Paystack | African card/bank/mobile-money payments | Tier 3 (tokenized) | Nigeria/UK |
| Flutterwave | African card/bank/mobile-money payments | Tier 3 (tokenized) | Nigeria |
| MTN Mobile Money | Mobile-money rails (Cameroon, Ghana, etc.) | Tier 3 (tokenized) | Per-country |
| Orange Money | Mobile-money rails (Cameroon, Senegal, etc.) | Tier 3 (tokenized) | Per-country |
| Twilio | SMS, WhatsApp Business | Tier 2 (phone numbers, message bodies) | US |
| Anthropic | AI inference (Claude family) | Per AI Gateway policy (Tier 2 with PII redaction) | US |
| Ollama (self-hosted) | AI inference (local fallback) | Tier 0-2 | Same region as application |

Full DPA + sub-processor list at https://runmycampus.com/legal/sub-processors.

## 8. Data subject rights (GDPR Articles 15-22)

- **Article 15 — Access**: Parents and students can request a full data export via `/portal/privacy/export/`. Generates a signed ZIP within 30 days (target: same-day).
- **Article 16 — Rectification**: Inline edit on student/parent profile pages; tenant admin can edit any field.
- **Article 17 — Erasure**: `EraseRequest` model (`apps.compliance`). Erasure preserves audit trail (hash-only, no content) per GDPR Article 17(3)(b).
- **Article 18 — Restriction**: `is_active=False` on user / student preserves data while preventing further processing.
- **Article 20 — Portability**: Same export pipeline as Article 15 emits JSON + CSV in well-documented schemas.
- **Article 21 — Objection**: Marketing/analytics opt-out via UserPreferences; school-required processing has no opt-out (necessary for legitimate interest in educational service delivery).

## 9. Encryption

- **At rest**: Postgres-managed AES-256 on Render Postgres instances (default).
- **In transit**: TLS 1.2+ (TLS 1.3 preferred) on all customer-facing endpoints. Internal service-to-service (Celery → Redis, Celery → Postgres) encrypted via VPC TLS.
- **Application-level field encryption**: not currently in use; `django-cryptography` available if a future control matrix requires column-level encryption for PII columns (e.g. SSN, Social Insurance Number). Track per data-class above.

## 10. Open items / known gaps

Tracked publicly to give prospects an honest posture. These do not represent
non-compliance; they represent capabilities not yet enabled.

- [ ] **SOC 2 Type II external audit** — pre-audit; control surface ready, auditor engagement pending first enterprise customer.
- [ ] **Penetration test** — pre-audit; annual cadence planned.
- [ ] **Bug bounty** — pre-launch.
- [ ] **FERPA disclosure log UI** — backend audit captures access; tenant-admin UI on Pass 6 roadmap.
- [ ] **Cross-region backup** — currently single-region; cross-region copy before SOC 2 audit.
- [ ] **WCAG 2.2 AA full pass** — see `ACCESSIBILITY_WCAG.md` for current state and Pass 6 roadmap.
- [ ] **CSP enforce mode** — currently report-only; flip after inline-script footprint reduced.

## 11. Contact

- Security disclosure: security@runmycampus.com (PGP key at https://runmycampus.com/.well-known/security.txt).
- DPO: dpo@runmycampus.com.
- Customer security questions: security@runmycampus.com.
