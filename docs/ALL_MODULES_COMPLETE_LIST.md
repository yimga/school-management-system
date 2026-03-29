# Complete List of All Modules - School Management System

**Last Updated**: March 28, 2026  
**Status**: Legacy narrative doc. The generated source of truth is `docs/generated/platform_inventory.md`.  
**Total Apps**: 42 Installed App Modules  
**Total Models**: 100+ database models  
**Total Views**: 200+ view functions  
**Total API Endpoints**: 50+ REST endpoints  

**Inventory alignment:** The count **42** matches `scripts/generate_platform_inventory.py` / `config/settings.py` entries of the form `apps.<name>` (project apps only). The third-party app `emis` remains in `INSTALLED_APPS` without the `apps.` prefix and is **not** included in that tally.

---

## 📋 Table of Contents

1. [Core Django Apps](#core-django-apps)
2. [Supporting Infrastructure](#supporting-infrastructure)
3. [External Integrations](#external-integrations)
4. [Module Dependencies](#module-dependencies)
5. [Quick Reference Table](#quick-reference-table)

---

## Core Django Apps

### 1. **apps.accounts** - 👤 Authentication & User Management

**Purpose**: User authentication, authorization, roles, permissions, MFA

**Key Models**:
- `User` - Extended Django user model with roles (ADMIN, TEACHER, PARENT, STUDENT, STAFF)
- `AccessRole` - Role-based access control
- `Permission` - System permissions
- `UserPreference` - User UI/UX preferences (theme, dashboard, notifications)
- `ActivityLog` - User activity tracking

**Key Features**:
- ✅ Multi-factor authentication (MFA/TOTP)
- ✅ Role-based access control (RBAC)
- ✅ User preferences (dashboard layout, theme, notifications)
- ✅ Activity tracking and audit logs
- ✅ Permission management
- ✅ Session management
- ✅ Password reset workflows

**Key Files**:
- `models.py` - User, Role, Permission models
- `views.py` - Authentication, profile, workflow center, MFA setup
- `permissions.py` - Permission checking logic
- `middleware.py` - Request processing middleware
- `utils.py` - Helper functions (get_user_role, etc.)

**URLs**: `/accounts/`, `/accounts/login/`, `/accounts/profile/`, `/accounts/mfa/`

---

### 2. **apps.academics** - 📚 Academic Structure

**Purpose**: Academic years, terms, classrooms, subjects, scheduling, certification

**Key Models**:
- `AcademicYear` - Academic year (e.g., 2025/2026)
- `Term` - Terms within academic year (First, Second, Third)
- `Classroom` - Classes (Form 1A, Form 2B, etc.)
- `Department` - Academic departments
- `Specialty` - Subject specialties (Science, Arts, Technical, etc.)
- `Subject` - Subjects (Mathematics, English, Physics, etc.)
- `SubjectAssignment` - Subject assignments to classrooms
- `Room` - Physical rooms for scheduling
- `Schedule` - Timetables/class schedules
- `CertificationExamPreset` - GCE/BAC exam presets
- `CertificationCandidate` - Exam candidates

**Key Features**:
- ✅ Academic year management
- ✅ Term configuration
- ✅ Classroom and subject assignment
- ✅ Timetable generation and scheduling
- ✅ GCE/BAC certification workflow
- ✅ Year-end rollover and cloning
- ✅ Subject prerequisites
- ✅ Room allocation

**Key Files**:
- `models.py` - All academic structure models
- `services.py` - Helper functions (get_active_year_and_term)
- `services_year_setup.py` - Year cloning and rollover
- `scheduling.py` - Timetable generation
- `services_certification.py` - Certification exam workflows

**URLs**: `/academics/`, `/academics/years/`, `/academics/classrooms/`, `/academics/subjects/`

---

### 3. **apps.people** - 👥 People Management

**Purpose**: Students, teachers, parents, guardians

**Key Models**:
- `StudentProfile` - Student information (admission number, status, academic year, classroom)
- `TeacherProfile` - Teacher information (staff ID, department, position)
- `StudentGuardian` - Guardian-student relationships
- `NotificationPreference` - Guardian notification settings

**Key Features**:
- ✅ Student enrollment and management
- ✅ Teacher assignment and profiles
- ✅ Guardian linking (multiple guardians per student)
- ✅ Admission number generation
- ✅ Profile management (photos, contact info)
- ✅ Student status tracking (Active, Withdrawn, Graduated, Alumni)
- ✅ Guardian access control (finance, academic, general)

**Key Files**:
- `models.py` - People models
- `admin.py` - Admin interfaces
- `forms_backend.py` - Backend forms
- `views_backend.py` - Backend views
- `people_management.py` - Business logic

**URLs**: `/people/students/`, `/people/teachers/`, `/people/guardians/`

---

### 4. **apps.evals** - 📊 Evaluations & Grading

**Purpose**: Grade entry, evaluation, approval workflows

**Key Models**:
- `Evaluation` - Grade entries (SEQ1, SEQ2, Exam, Practical, Mock)
- `AssessmentWeights` - Grading weights and scales
- `GradeAudit` - Audit trail for grade changes
- `OfflineMarkEntry` - Offline sync queue
- `GradeImportJob` - Bulk import tracking
- `PracticalAssessment` - Practical/TP assessment tracking

**Key Features**:
- ✅ Grade entry and validation
- ✅ Multi-scale grading (0-20, A-E, GPA 4.0, percentage)
- ✅ Grade approval workflows (teacher → coordinator → principal)
- ✅ Offline mark entry with conflict resolution
- ✅ Bulk grade import (CSV/Excel)
- ✅ Practical assessment tracking (with photo evidence)
- ✅ Grade audit trail (who changed what, when)
- ✅ Automatic grade conversion between scales
- ✅ Class ranking and statistics

**Key Files**:
- `models.py` - Evaluation models
- `views.py` - Grade entry, approval, compliance views
- `validators.py` - Grade validation rules
- `signals.py` - Auto-audit and grade conversion
- `offline_sync.py` - Offline sync service
- `notifications.py` - Notification service (SMS/Email/WhatsApp)
- `importers.py` - CSV import logic
- `approval.py` - Approval workflow logic

**URLs**: `/evals/`, `/evals/entry/`, `/evals/approval/`, `/evals/import/`

---

### 5. **apps.finance** - 💰 Financial Management

**Purpose**: Fees, invoices, payments, accounting, payment automation

**Key Models**:
- `FeePlan` - Fee plans per academic year/classroom/specialty
- `FeeItem` - Individual fee items (tuition, activity, exam, etc.)
- `FeeInstallment` - Fee installments
- `Invoice` - Student invoices
- `InvoiceLine` - Invoice line items
- `Payment` - Payments received
- `PaymentReminder` - Payment reminder configuration
- `PaymentReminderLog` - Reminder execution logs
- `PaymentProofUpload` - Receipt uploads from parents (NEW)
- `BankAccount` - School bank accounts (NEW)
- `BankStatementEntry` - Bank statement transactions (NEW)
- `BankStatementUpload` - Bank statement file uploads (NEW)
- `RefundRequest` - Refund requests
- `ComplianceProfile` - Regional compliance (tax, payroll rules)
- `LedgerAccount` - Chart of accounts
- `JournalEntry` - Accounting journal entries
- `JournalLine` - Journal entry lines
- `TaxBracket` - Tax brackets
- `ContributionRule` - Social contribution rules
- `ReferralReward` - Referral bonuses
- `PaymentMethod` - Payment method configuration
- `PaymentReconciliation` - Payment reconciliation

**Key Features**:
- ✅ Fee plan configuration
- ✅ Automated invoice generation (configurable schedules)
- ✅ Payment processing (Cash, Bank, MTN MoMo, Orange Money)
- ✅ **Payment receipt upload** from parents (NEW)
- ✅ **Automated receipt verification** (pattern matching, OCR-ready) (NEW)
- ✅ **Fraud detection** (duplicate files, date validation, upload patterns) (NEW)
- ✅ **Bank deposit verification** (match receipts against bank statements) (NEW)
- ✅ **Overpayment handling** (tolerance, refund requests, credit) (NEW)
- ✅ Payment reminders (Email, SMS, WhatsApp) with payment instructions
- ✅ **Reminder history & resend** (NEW)
- ✅ **Retry failed reminders** (NEW)
- ✅ Accounting ledger (double-entry)
- ✅ Regional compliance (Cameroon CNPS, taxes)
- ✅ Referral rewards
- ✅ Payment reconciliation
- ✅ Webhook support for payment gateways

**Key Files**:
- `models.py` - Finance models
- `services.py` - Business logic (create_fee_invoices, copy_fee_plan_to_year, create_payment_from_receipt)
- `views.py` - Finance dashboard, invoice/payment views, receipt upload
- `tasks.py` - Celery tasks (payment reminders, receipt processing, retry failed reminders)
- `admin.py` - Admin interfaces
- `receipt_verification.py` - Receipt data extraction (NEW)
- `fraud_detection.py` - Fraud detection service (NEW)
- `bank_verification.py` - Bank deposit verification (NEW)
- `advanced_payments.py` - Advanced payment features

**URLs**: `/finance/`, `/finance/invoices/`, `/finance/payments/`, `/finance/invoices/<id>/upload-receipt/`

---

### 6. **apps.payroll** - 💵 Payroll Management

**Purpose**: Employee payroll, payslips, compliance

**Key Models**:
- `PayrollRun` - Payroll execution runs
- `Payslip` - Individual employee payslips
- `PayslipLine` - Payslip line items (earnings, deductions)
- `PayScale` - Pay scale/grade definitions
- `PayrollEmployee` - Employee payroll configuration

**Key Features**:
- ✅ Monthly payroll generation
- ✅ CNPS contributions (Cameroon)
- ✅ Tax calculations (progressive brackets)
- ✅ Overtime calculations
- ✅ Payslip generation (PDF)
- ✅ Pay scale management
- ✅ Deductions (loans, advances, etc.)
- ✅ Bonuses and allowances

**Key Files**:
- `models.py` - Payroll models
- `services.py` - Payroll calculation logic
- `views.py` - Payroll dashboard
- `management/commands/run_payroll_cycle.py` - Payroll automation

**URLs**: `/payroll/`, `/payroll/runs/`, `/payroll/payslips/`

---

### 7. **apps.reports** - 📄 Reports & Report Cards

**Purpose**: Report card generation, exports, scheduled reports

**Key Models**:
- `ReportCard` - Generated report cards
- `ReportCardStyle` - Report card templates
- `ReportDefinition` - Report definitions
- `ScheduledReport` - Scheduled report generation
- `MaterializedReportCache` - Cached report data
- `TermPublishStatus` - Term publication status

**Key Features**:
- ✅ Report card PDF generation
- ✅ Customizable report card styles (Cameroon formats)
- ✅ Scheduled report generation
- ✅ Data exports (CSV, Excel, PDF)
- ✅ Regional report formats (Cameroon Anglophone/Francophone)
- ✅ Term publication workflow
- ✅ Annual report generation
- ✅ Multi-language support (English, French)

**Key Files**:
- `models.py` - Report models
- `services.py` - Report generation logic
- `views.py` - Report views
- `bi_models.py` - Business intelligence models
- `bi_services.py` - BI services (ScheduledReportRunner)

**URLs**: `/reports/`, `/reports/cards/`, `/reports/publish/`

---

### 8. **apps.portal** - 🌐 Parent & Teacher Portal

**Purpose**: Portal interfaces for parents and teachers

**Key Models**:
- `PortalFeatureItem` - Portal feature content (documents, announcements, etc.)
- `PortalNotification` - Portal notifications
- `ParentMessage` - Parent messages
- `DocumentLibrary` - Document library items
- `KnowledgeBaseArticle` - Knowledge base articles
- `SignatureRequest` - Electronic signature requests

**Key Features**:
- ✅ Parent dashboard (student overview, finance, results)
- ✅ Teacher dashboard (classes, grades, attendance)
- ✅ Student 360 view (all student information)
- ✅ Document library (with signature workflow)
- ✅ Communication center
- ✅ Results viewing (term reports, annual reports)
- ✅ Finance summary (invoices, payments, receipts)
- ✅ Attendance tracking
- ✅ Knowledge base
- ✅ Student onboarding wizard
- ✅ AI Copilot (assistant)

**Key Files**:
- `views.py` - Portal views
- `services.py` - Portal business logic
- `models.py` - Portal models
- `models_kb.py` - Knowledge base models
- `portal_services.py` - Portal-specific services
- `views_onboarding.py` - Student onboarding
- `views_ai_copilot.py` - AI Copilot

**URLs**: `/portal/`, `/portal/parent/`, `/portal/teacher/`, `/portal/student/<id>/`

---

### 9. **apps.analytics** - 📈 Analytics & Dashboards

**Purpose**: Analytics, dashboards, compliance tracking, deadline management

**Key Models**:
- `GradeImportJob` - Import job tracking
- `AttendanceLog` - Attendance tracking (stub)
- Various analytics models

**Key Features**:
- ✅ Analytics dashboard (performance metrics, trends)
- ✅ Grade compliance tracking
- ✅ Deadline reminders (automated)
- ✅ Performance metrics (class averages, pass rates)
- ✅ ML predictions (fee defaults, student performance)
- ✅ Master sheet (comprehensive grade view)
- ✅ Class rankings
- ✅ Subject performance analysis

**Key Files**:
- `views.py` - Analytics dashboard
- `services.py` - Analytics services
- `tasks.py` - Celery tasks (deadline reminders)
- `ml_predictions.py` - ML prediction services
- `management/commands/send_deadline_reminders.py` - Reminder automation

**URLs**: `/analytics/`, `/analytics/dashboard/`, `/analytics/master-sheet/`

---

### 10. **apps.siteconfig** - ⚙️ Configuration Control Center

**Purpose**: Site-wide settings, themes, preferences, dashboard customization

**Key Models**:
- `SiteSettings` - Single-row site configuration (100+ settings)
- `UserPreference` - User preferences
- `ThemePack` - Theme packs
- `ReportCardStyle` - Report card styles
- `RegionConfig` - Regional configuration
- `DashboardWidget` - Dashboard widgets
- `DashboardUserPreference` - User dashboard preferences
- `Integration` - External integrations (email, SMS, payments)

**Key Features**:
- ✅ Site-wide configuration (branding, behavior, features)
- ✅ Theme and color management (light/dark modes)
- ✅ User preferences (dashboard layout, theme, notifications)
- ✅ Dashboard customization (widgets, layout)
- ✅ Regional settings (timezone, currency, grading scales)
- ✅ Feature toggles (enable/disable features)
- ✅ Payment integration configuration
- ✅ Notification channel configuration
- ✅ **Finance automation settings** (NEW):
  - Receipt upload configuration
  - Bank verification settings
  - Payment reminder settings
  - Overpayment handling
  - Real-world scenario settings

**Key Files**:
- `models.py` - SiteSettings and related models
- `forms.py` - SiteSettings form
- `admin.py` - Admin configuration
- `views.py` - Settings views
- `dashboard_views.py` - Dashboard layout management
- `context_processors.py` - Template context processors

**URLs**: `/admin/siteconfig/sitesettings/`, `/siteconfig/preferences/`

---

### 11. **apps.compliance** - 🔒 Compliance & Security

**Purpose**: Audit logging, access control, threat detection

**Key Models**:
- `AuditLog` - Audit trail (model changes, actions)
- `AccessLog` - Access logging (HTTP requests)
- `UserActivitySession` - User session tracking
- `ComplianceReport` - Compliance reports
- `IPAccessRule` - IP access rules (whitelist/blacklist)
- `ThreatDetectionConfig` - Threat detection config

**Key Features**:
- ✅ Comprehensive audit logging (who did what, when)
- ✅ Access control (IP-based, role-based)
- ✅ Threat detection (suspicious activity patterns)
- ✅ Compliance reporting (GDPR, data protection)
- ✅ IP whitelisting/blacklisting
- ✅ Session tracking
- ✅ Data retention policies

**Key Files**:
- `models_audit.py` - Audit models
- `access_control.py` - Access control logic
- `threat_detection.py` - Threat detection
- `alerts.py` - Compliance alerts
- `middleware.py` - Audit and access control middleware
- `management/commands/generate_compliance_reports.py` - Report automation

**URLs**: `/compliance/audit/`, `/compliance/access/`

---

### 12. **apps.communication** - 💬 Communication

**Purpose**: Messaging, announcements, video conferencing

**Key Models**:
- `Message` - Internal messages
- `Announcement` - School announcements
- `MessageGroup` - Message groups
- `VideoConferenceSession` - Video conference sessions
- `ContactRequest` - Contact requests from parents

**Key Features**:
- ✅ Internal messaging (staff-to-staff, staff-to-parent)
- ✅ Announcements (school-wide, class-specific)
- ✅ Message groups (class groups, department groups)
- ✅ Video conferencing integration
- ✅ WhatsApp integration (Business API)
- ✅ Email integration
- ✅ SMS integration
- ✅ Contact request workflow

**Key Files**:
- `models.py` - Communication models
- `views.py` - Communication views
- `integrations.py` - External integrations (WhatsApp, SMS, Email)

**URLs**: `/communication/`, `/communication/messages/`, `/communication/announcements/`

---

### 13. **apps.requests** - 📝 Access Requests

**Purpose**: Access request management

**Key Models**:
- `AccessRequest` - Access requests (finance access, academic access, etc.)

**Key Features**:
- ✅ Access request workflow (request → approve/reject)
- ✅ Request approval/rejection
- ✅ Notification on approval/rejection
- ✅ Bulk access management

**Key Files**:
- `models.py` - Request models
- `views.py` - Request views
- `services.py` - Request processing
- `signals.py` - Auto-notifications

**URLs**: `/requests/`, `/requests/access/`

---

### 14. **apps.observability** - 📊 Monitoring & Observability

**Purpose**: System monitoring, metrics, health checks

**Key Features**:
- ✅ Health checks (database, cache, external services)
- ✅ Metrics collection (Prometheus-compatible)
- ✅ Performance monitoring
- ✅ Request tracking
- ✅ Error tracking

**Key Files**:
- `views.py` - Health check endpoints
- `templatetags/` - Monitoring template tags
- `test_monitoring.py` - Monitoring tests

**URLs**: `/observability/health/`, `/observability/metrics/`

---

### 15. **apps.api** - 🔌 REST API

**Purpose**: RESTful API endpoints for mobile apps and integrations

**Key Features**:
- ✅ REST API for mobile apps
- ✅ Dashboard layout API (save/load user dashboard layouts)
- ✅ Entity API (CRUD for students, teachers, invoices, etc.)
- ✅ Search API (unified search across entities)
- ✅ Notification API (push notifications)
- ✅ Authentication (JWT tokens)
- ✅ API documentation (OpenAPI/Swagger-ready)

**Key Files**:
- `urls.py` - API routes
- `serializers.py` - API serializers
- `dashboard_api.py` - Dashboard APIs
- `entity_api.py` - Entity APIs
- `search_api.py` - Search API
- `notification_api.py` - Notification API
- `dashboard_layout_api.py` - Dashboard layout management

**URLs**: `/api/`, `/api/dashboard/`, `/api/entities/`, `/api/search/`

---

### 16. **apps.automation** - 🤖 Automation & Background Tasks

**Purpose**: Configurable automation and background tasks

**Key Models**:
- `AutomationExecutionLog` - Automation execution history
- `AutomationApprovalQueue` - Automation approval queue (for high-risk automations)

**Key Features**:
- ✅ Automated fee invoice generation (configurable schedules)
- ✅ Automated payment reminders (multi-channel, configurable)
- ✅ Automated invoice status updates (overdue detection)
- ✅ Fee plan copying (year-to-year)
- ✅ Execution logging (who ran what, when, results)
- ✅ Approval workflows (for high-risk automations)
- ✅ Dry-run mode (test before executing)
- ✅ Configurable thresholds and schedules

**Key Files**:
- `models.py` - Automation models
- `helpers.py` - Helper functions (get_notification_channels, get_cached_site_settings)
- `admin.py` - Admin interfaces

**URLs**: `/admin/automation/executionlogs/`, `/admin/automation/approvalqueue/`

---

### 17. **emis** - 📋 EMIS Integration

**Purpose**: Education Management Information System integration (Government reporting)

**Key Models**:
- `EMISExport` - EMIS data exports (students, teachers, enrollment, performance)
- `EMISFieldMapping` - Field mappings for different country EMIS formats
- `EMISCompliance` - EMIS compliance requirements by country

**Key Features**:
- ✅ EMIS data export (students, teachers, subjects, enrollment, performance)
- ✅ Government reporting (statistical returns)
- ✅ Multi-country support (Cameroon, etc.)
- ✅ Field mapping (internal fields → EMIS format)
- ✅ Compliance tracking (EMIS version, requirements)

**Key Files**:
- `models.py` - EMIS models
- `services.py` - EMIS export logic
- `views.py` - EMIS dashboard
- `admin.py` - EMIS admin

**URLs**: `/emis/`, `/emis/export/`

---

## Supporting Infrastructure

### Configuration
- **`config/settings.py`** - Django settings (INSTALLED_APPS, MIDDLEWARE, database, cache, Celery)
- **`config/urls.py`** - URL routing (main URLconf)
- **`config/admin.py`** - Admin site configuration (custom admin site)
- **`config/celery.py`** - Celery configuration (background tasks)

### Templates
- **`templates/`** - HTML templates (Django templates)
  - Admin templates (`templates/admin/`)
  - Portal templates (`templates/portal/`, `templates/parent/`, `templates/teacher/`)
  - Component templates (`templates/components/`)

### Static Files
- **`static/`** - Static files (CSS, JS, images)
  - CSS: Theme files, dashboard styles, admin styles
  - JS: Dashboard charts, layout management, theme switching

### Management Commands
- Various `management/commands/` directories in each app for Django management commands
- Examples:
  - `send_payment_reminders.py` - Send payment reminders
  - `verify_bank_deposits.py` - Verify bank deposits
  - `run_payroll_cycle.py` - Run payroll cycle
  - `send_deadline_reminders.py` - Send deadline reminders

---

## External Integrations

### 1. **Payment Processors**
- **MTN Mobile Money** (Cameroon)
- **Orange Money** (Cameroon)
- **Bank transfers** (local banks)
- **Cash** payments
- **Payment gateways** (webhook support)

### 2. **Communication**
- **Email** (SMTP/SendGrid)
- **SMS** (Twilio, AfricasTalking)
- **WhatsApp** (Business API)

### 3. **Authentication**
- **Django OTP** (MFA/TOTP)

### 4. **Background Tasks**
- **Celery** + **Redis** (if REDIS_URL is set)
- **django-celery-beat** (scheduled tasks)
- **django-celery-results** (task result storage in database)

### 5. **Caching**
- **Redis** (if available)
- **Django LocMemCache** (fallback)

### 6. **Database**
- **PostgreSQL** (recommended for production)
- **SQLite** (default for development)

---

## Module Dependencies

```
accounts (core - authentication & users)
│
├── academics (depends on accounts)
│   └── Academic structure (years, terms, classrooms, subjects)
│
├── people (depends on accounts, academics)
│   └── Students, teachers, guardians
│
├── evals (depends on accounts, academics, people)
│   └── Grading and evaluations
│
├── finance (depends on accounts, academics, people)
│   └── Fees, invoices, payments, accounting
│
├── payroll (depends on accounts, people, finance)
│   └── Employee payroll
│
├── reports (depends on accounts, academics, evals)
│   └── Report cards and reports
│
├── portal (depends on accounts, people, evals, finance)
│   └── Parent and teacher portals
│
├── analytics (depends on accounts, academics, evals)
│   └── Analytics and dashboards
│
├── siteconfig (depends on accounts)
│   └── Site-wide configuration
│
├── compliance (depends on accounts)
│   └── Audit logging and security
│
├── communication (depends on accounts, people)
│   └── Messaging and announcements
│
├── requests (depends on accounts)
│   └── Access requests
│
├── observability (depends on accounts)
│   └── Monitoring and health checks
│
├── api (depends on all apps)
│   └── REST API endpoints
│
└── automation (depends on finance, evals, academics, siteconfig)
    └── Configurable automation

emis (external module - EMIS integration)
```

---

## Quick Reference Table

| # | Module | Primary Purpose | Key Models | Key Features |
|---|--------|----------------|------------|--------------|
| 1 | **accounts** | Auth & Users | User, AccessRole, Permission, UserPreference | MFA, RBAC, Preferences |
| 2 | **academics** | Academic Structure | AcademicYear, Term, Classroom, Subject, Schedule | Year management, Scheduling, Certification |
| 3 | **people** | People Management | StudentProfile, TeacherProfile, StudentGuardian | Enrollment, Profiles, Guardian linking |
| 4 | **evals** | Grading | Evaluation, AssessmentWeights, GradeAudit | Grade entry, Approval workflows, Offline sync |
| 5 | **finance** | Financial | FeePlan, Invoice, Payment, PaymentReminder, PaymentProofUpload, BankAccount | Fee management, Payments, Receipt upload, Bank verification, Fraud detection |
| 6 | **payroll** | Payroll | PayrollRun, Payslip, PayScale | Payroll generation, CNPS, Tax calculations |
| 7 | **reports** | Reports | ReportCard, ReportCardStyle, ScheduledReport | Report cards, PDF generation, Scheduled reports |
| 8 | **portal** | Portals | PortalFeatureItem, DocumentLibrary, SignatureRequest | Parent/Teacher dashboards, Documents, Onboarding |
| 9 | **analytics** | Analytics | GradeImportJob, AttendanceLog | Dashboards, Metrics, ML predictions |
| 10 | **siteconfig** | Configuration | SiteSettings, UserPreference, ThemePack, RegionConfig | Site settings, Themes, Preferences |
| 11 | **compliance** | Security | AuditLog, AccessLog, IPAccessRule | Audit logging, Access control, Threat detection |
| 12 | **communication** | Messaging | Message, Announcement, MessageGroup | Internal messaging, Announcements, WhatsApp |
| 13 | **requests** | Access Requests | AccessRequest | Request workflow, Approval |
| 14 | **observability** | Monitoring | Various | Health checks, Metrics, Performance |
| 15 | **api** | REST API | N/A (serializers) | REST endpoints, Mobile API, Search API |
| 16 | **automation** | Automation | AutomationExecutionLog, AutomationApprovalQueue | Automated tasks, Execution logging |
| 17 | **emis** | EMIS Integration | EMISExport, EMISFieldMapping | Government reporting, Data export |

---

## Recent Enhancements (Finance Module)

### Payment Receipt Automation (NEW)
- ✅ Parent receipt upload
- ✅ Automated receipt verification (pattern matching, OCR-ready)
- ✅ Fraud detection (duplicate files, date validation, upload patterns)
- ✅ Bank deposit verification (match receipts against bank statements)
- ✅ Overpayment handling (tolerance, refund requests, credit)
- ✅ Receipt reassignment (wrong invoice correction)
- ✅ Idempotency (prevent duplicate uploads)

### Payment Reminders (ENHANCED)
- ✅ Payment instructions in reminders (bank accounts, MoMo numbers)
- ✅ Reminder history tracking
- ✅ Resend reminder functionality
- ✅ Retry failed reminders (automated)
- ✅ No-contact handling (guardians without email/phone)

### Real-World Scenarios (NEW)
- ✅ Delayed bank statement verification (30-day cycle support)
- ✅ Cash payment workflow (manual verification)
- ✅ Student withdrawal (stop reminders)
- ✅ Invoice void handling (stop reminders, optional refund/credit)
- ✅ Configurable overpayment tolerance
- ✅ Configurable verification workflows

---

## Statistics

- **Total Django Apps**: 17
- **External Modules**: 1 (emis)
- **Total Models**: 100+
- **Total Views**: 200+
- **Total API Endpoints**: 50+
- **Total Management Commands**: 20+
- **Total Celery Tasks**: 10+

---

## Access Points

### Admin Interface
- **URL**: `/admin/`
- **Access**: Staff users only
- **Features**: Full CRUD for all models, automation management, configuration

### Parent Portal
- **URL**: `/portal/parent/`
- **Access**: Parents/Guardians
- **Features**: Student overview, finance, results, documents, communication

### Teacher Portal
- **URL**: `/portal/teacher/`
- **Access**: Teachers
- **Features**: Classes, grade entry, attendance, student information

### REST API
- **URL**: `/api/`
- **Access**: JWT authentication
- **Features**: Mobile app support, integrations

---

**Last Updated**: February 3, 2026  
**Document Version**: 2.0 (includes recent finance automation enhancements)
