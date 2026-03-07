# Key Modules Reference - School Management System

**Last Updated**: February 2, 2026  
**Purpose**: Comprehensive list of all key modules, apps, and their primary functions

---

## Feature documentation

| Topic | Document | Description |
|-------|----------|-------------|
| **Report Library & Bulk Letters** | [REPORTS_AND_BULK_LETTERS.md](REPORTS_AND_BULK_LETTERS.md) | Export reports (CSV/Excel/ODS/PDF), bulk ODT/PDF letters per classroom |
| **KB & LibreOffice ODT** | [KB_LIBREOFFICE_ODT_INTEGRATION.md](KB_LIBREOFFICE_ODT_INTEGRATION.md) | Knowledge base ODT/PDF downloads, document conversion |
| **API vs guide** | [API_AUDIT_VS_GUIDE.md](API_AUDIT_VS_GUIDE.md) | API endpoints and RBAC alignment |

---

## Core Django Apps

### 1. **apps.accounts** - Authentication & User Management
**Purpose**: User authentication, authorization, roles, permissions, MFA

**Key Models**:
- `User` - Extended Django user model
- `AccessRole` - Role-based access control
- `Permission` - System permissions
- `UserPreference` - User UI/UX preferences

**Key Features**:
- Multi-factor authentication (MFA)
- Role-based access control (RBAC)
- User preferences (dashboard, notifications, theme)
- Activity tracking
- Permission management

**Key Files**:
- `models.py` - User, Role, Permission models
- `views.py` - Authentication, profile, workflow center
- `permissions.py` - Permission checking logic
- `middleware.py` - Request processing middleware
- `utils.py` - Helper functions (get_user_role, etc.)

---

### 2. **apps.academics** - Academic Structure
**Purpose**: Academic years, terms, classrooms, subjects, scheduling

**Key Models**:
- `AcademicYear` - Academic year (e.g., 2025/2026)
- `Term` - Terms within academic year (First, Second, Third)
- `Classroom` - Classes (Form 1A, Form 2B, etc.)
- `Department` - Academic departments
- `Specialty` - Subject specialties (Science, Arts, etc.)
- `Subject` - Subjects (Mathematics, English, etc.)
- `SubjectAssignment` - Subject assignments to classrooms
- `Room` - Physical rooms for scheduling
- `Schedule` - Timetables
- `CertificationExamPreset` - GCE/BAC exam presets
- `CertificationCandidate` - Exam candidates

**Key Features**:
- Academic year management
- Term configuration
- Classroom and subject assignment
- Timetable generation and scheduling
- GCE/BAC certification workflow
- Year-end rollover and cloning

**Key Files**:
- `models.py` - All academic structure models
- `services.py` - Helper functions (get_active_year_and_term)
- `services_year_setup.py` - Year cloning and rollover
- `scheduling.py` - Timetable generation
- `services_certification.py` - Certification exam workflows

---

### 3. **apps.people** - People Management
**Purpose**: Students, teachers, parents, guardians

**Key Models**:
- `StudentProfile` - Student information
- `TeacherProfile` - Teacher information
- `StudentGuardian` - Guardian-student relationships
- `NotificationPreference` - Guardian notification settings

**Key Features**:
- Student enrollment and management
- Teacher assignment
- Guardian linking
- Admission number generation
- Profile management

**Key Files**:
- `models.py` - People models
- `admin.py` - Admin interfaces
- `forms_backend.py` - Backend forms
- `views_backend.py` - Backend views
- `people_management.py` - Business logic

---

### 4. **apps.evals** - Evaluations & Grading
**Purpose**: Grade entry, evaluation, approval workflows

**Key Models**:
- `Evaluation` - Grade entries
- `AssessmentWeights` - Grading weights and scales
- `GradeAudit` - Audit trail for grade changes
- `OfflineMarkEntry` - Offline sync queue
- `GradeImportJob` - Bulk import tracking

**Key Features**:
- Grade entry and validation
- Multi-scale grading (0-20, A-E, GPA, percentage)
- Grade approval workflows
- Offline mark entry with conflict resolution
- Bulk grade import
- Practical assessment tracking
- Grade audit trail

**Key Files**:
- `models.py` - Evaluation models
- `views.py` - Grade entry, approval, compliance views
- `validators.py` - Grade validation rules
- `signals.py` - Auto-audit and grade conversion
- `offline_sync.py` - Offline sync service
- `notifications.py` - Notification service (SMS/Email/WhatsApp)
- `importers.py` - CSV import logic
- `approval.py` - Approval workflow logic

---

### 5. **apps.finance** - Financial Management
**Purpose**: Fees, invoices, payments, accounting

**Key Models**:
- `FeePlan` - Fee plans per academic year/classroom/specialty
- `FeeItem` - Individual fee items (tuition, activity, etc.)
- `FeeInstallment` - Fee installments
- `Invoice` - Student invoices
- `InvoiceLine` - Invoice line items
- `Payment` - Payments received
- `PaymentReminder` - Payment reminder configuration
- `PaymentReminderLog` - Reminder execution logs
- `ComplianceProfile` - Regional compliance (tax, payroll rules)
- `LedgerAccount` - Chart of accounts
- `JournalEntry` - Accounting journal entries
- `JournalLine` - Journal entry lines
- `TaxBracket` - Tax brackets
- `ContributionRule` - Social contribution rules
- `ReferralReward` - Referral bonuses

**Key Features**:
- Fee plan configuration
- Invoice generation
- Payment processing (Cash, Bank, MTN MoMo, Orange Money)
- Payment reminders (Email, SMS, WhatsApp)
- Accounting ledger
- Regional compliance (Cameroon CNPS, taxes)
- Referral rewards

**Key Files**:
- `models.py` - Finance models
- `services.py` - Business logic (create_fee_invoices, copy_fee_plan_to_year)
- `views.py` - Finance dashboard, invoice/payment views
- `tasks.py` - Celery tasks (payment reminders)
- `admin.py` - Admin interfaces
- `advanced_payments.py` - Advanced payment features

---

### 6. **apps.payroll** - Payroll Management
**Purpose**: Employee payroll, payslips, compliance

**Key Models**:
- `PayrollRun` - Payroll execution runs
- `Payslip` - Individual employee payslips
- `PayslipLine` - Payslip line items

**Key Features**:
- Monthly payroll generation
- CNPS contributions (Cameroon)
- Tax calculations
- Overtime calculations
- Payslip generation

**Key Files**:
- `models.py` - Payroll models
- `services.py` - Payroll calculation logic
- `views.py` - Payroll dashboard
- `management/commands/run_payroll_cycle.py` - Payroll automation

---

### 7. **apps.reports** - Reports & Report Cards
**Purpose**: Report card generation, exports, scheduled reports

**Key Models**:
- `ReportCardStyle` - Report card templates
- `ReportDefinition` - Report definitions
- `ScheduledReport` - Scheduled report generation
- `MaterializedReportCache` - Cached report data

**Key Features**:
- Report card PDF generation
- Customizable report card styles
- Scheduled report generation
- Data exports (CSV, Excel, PDF)
- Regional report formats (Cameroon)

**Key Files**:
- `models.py` - Report models
- `services.py` - Report generation logic
- `views.py` - Report views
- `bi_models.py` - Business intelligence models
- `bi_services.py` - BI services (ScheduledReportRunner)

---

### 8. **apps.portal** - Parent & Teacher Portal
**Purpose**: Portal interfaces for parents and teachers

**Key Models**:
- `PortalFeatureItem` - Portal feature content
- Various portal-specific models

**Key Features**:
- Parent dashboard
- Teacher dashboard
- Student 360 view
- Document library
- Communication center
- Results viewing
- Finance summary
- Attendance tracking

**Key Files**:
- `views.py` - Portal views
- `services.py` - Portal business logic
- `models_kb.py` - Knowledge base models
- `portal_services.py` - Portal-specific services

---

### 9. **apps.analytics** - Analytics & Dashboards
**Purpose**: Analytics, dashboards, compliance tracking

**Key Models**:
- `GradeImportJob` - Import job tracking
- Various analytics models

**Key Features**:
- Analytics dashboard
- Grade compliance tracking
- Deadline reminders
- Performance metrics
- ML predictions (fee defaults, etc.)

**Key Files**:
- `views.py` - Analytics dashboard
- `services.py` - Analytics services
- `tasks.py` - Celery tasks (deadline reminders)
- `ml_predictions.py` - ML prediction services
- `management/commands/send_deadline_reminders.py` - Reminder automation

---

### 10. **apps.siteconfig** - Site Configuration
**Purpose**: Site-wide settings, themes, preferences

**Key Models**:
- `SiteSettings` - Single-row site configuration
- `UserPreference` - User preferences
- `ThemePack` - Theme packs
- `ReportCardStyle` - Report card styles
- `RegionConfig` - Regional configuration
- `DashboardWidget` - Dashboard widgets
- `DashboardUserPreference` - User dashboard preferences

**Key Features**:
- Site-wide configuration
- Theme and color management
- User preferences
- Dashboard customization
- Regional settings (timezone, currency, grading scales)
- Feature toggles
- **Report Library** — export reports as CSV, Excel, ODS, or PDF (see [REPORTS_AND_BULK_LETTERS.md](REPORTS_AND_BULK_LETTERS.md))
- **Bulk Letters** — generate ODT/PDF letters per classroom (Pandoc/LibreOffice)

**Key Files**:
- `models.py` - SiteSettings and related models
- `forms.py` - SiteSettings form
- `admin.py` - Admin configuration
- `views.py` - Settings views
- `dashboard_views.py` - Dashboard layout management
- `context_processors.py` - Template context processors

---

### 11. **apps.compliance** - Compliance & Security
**Purpose**: Audit logging, access control, threat detection

**Key Models**:
- `AuditLog` - Audit trail
- `AccessLog` - Access logging
- `UserActivitySession` - User session tracking
- `ComplianceReport` - Compliance reports
- `IPAccessRule` - IP access rules
- `ThreatDetectionConfig` - Threat detection config

**Key Features**:
- Comprehensive audit logging
- Access control
- Threat detection
- Compliance reporting
- IP whitelisting/blacklisting

**Key Files**:
- `models_audit.py` - Audit models
- `access_control.py` - Access control logic
- `threat_detection.py` - Threat detection
- `alerts.py` - Compliance alerts
- `management/commands/generate_compliance_reports.py` - Report automation

---

### 12. **apps.communication** - Communication
**Purpose**: Messaging, announcements, video conferencing

**Key Models**:
- `Message` - Internal messages
- `Announcement` - School announcements
- `MessageGroup` - Message groups
- `VideoConferenceSession` - Video conference sessions

**Key Features**:
- Internal messaging
- Announcements
- Message groups
- Video conferencing integration
- WhatsApp integration

**Key Files**:
- `models.py` - Communication models
- `views.py` - Communication views
- `integrations.py` - External integrations

---

### 13. **apps.requests** - Access Requests
**Purpose**: Access request management

**Key Models**:
- `AccessRequest` - Access requests

**Key Features**:
- Access request workflow
- Request approval/rejection

**Key Files**:
- `models.py` - Request models
- `views.py` - Request views
- `services.py` - Request processing

---

### 14. **apps.observability** - Monitoring & Observability
**Purpose**: System monitoring, metrics, health checks

**Key Features**:
- Health checks
- Metrics collection
- Performance monitoring

**Key Files**:
- Various monitoring utilities

---

### 15. **apps.api** - REST API
**Purpose**: RESTful API endpoints

**Key Features**:
- REST API for mobile apps
- Dashboard layout API
- Entity API
- Search API
- Notification API

**Key Files**:
- `urls.py` - API routes
- `serializers.py` - API serializers
- `dashboard_api.py` - Dashboard APIs
- `entity_api.py` - Entity APIs
- `search_api.py` - Search API
- `notification_api.py` - Notification API

---

### 16. **apps.automation** - Automation (NEW)
**Purpose**: Configurable automation and background tasks

**Key Models**:
- `AutomationExecutionLog` - Automation execution history
- `AutomationApprovalQueue` - Automation approval queue

**Key Features**:
- Automated fee invoice generation
- Automated payment reminders
- Automated invoice status updates
- Fee plan copying
- Execution logging
- Approval workflows

**Key Files**:
- `models.py` - Automation models
- `helpers.py` - Helper functions
- `admin.py` - Admin interfaces

---

### 17. **emis** - EMIS Integration
**Purpose**: Education Management Information System integration

**Key Features**:
- EMIS data export
- Government reporting
- Statistical returns

---

## Supporting Infrastructure

### Configuration
- `config/settings.py` - Django settings
- `config/urls.py` - URL routing
- `config/admin.py` - Admin site configuration
- `config/celery.py` - Celery configuration

### Templates
- `templates/` - HTML templates
- `static/` - Static files (CSS, JS, images)

### Management Commands
- Various `management/commands/` directories for Django management commands

---

## Key External Integrations

1. **Payment Processors**:
   - MTN Mobile Money
   - Orange Money
   - Bank transfers
   - Cash

2. **Communication**:
   - Email (SMTP)
   - SMS (Twilio, AfricasTalking)
   - WhatsApp (Business API)

3. **Authentication**:
   - Django OTP (MFA)

4. **Background Tasks**:
   - Celery + Redis
   - django-celery-beat (scheduled tasks)

5. **Caching**:
   - Redis (if available)
   - Django LocMemCache (fallback)

---

## Module Dependencies

```
accounts (core)
├── academics (depends on accounts)
├── people (depends on accounts, academics)
├── evals (depends on accounts, academics, people)
├── finance (depends on accounts, academics, people)
├── payroll (depends on accounts, people, finance)
├── reports (depends on accounts, academics, evals)
├── portal (depends on accounts, people, evals, finance)
├── analytics (depends on accounts, academics, evals)
├── siteconfig (depends on accounts)
├── compliance (depends on accounts)
├── communication (depends on accounts, people)
├── requests (depends on accounts)
├── observability (depends on accounts)
├── api (depends on all apps)
└── automation (depends on finance, evals, academics, siteconfig)
```

---

## Quick Reference

| Module | Primary Purpose | Key Models |
|--------|----------------|------------|
| accounts | Auth & Users | User, AccessRole, Permission |
| academics | Academic Structure | AcademicYear, Term, Classroom, Subject |
| people | People Management | StudentProfile, TeacherProfile |
| evals | Grading | Evaluation, AssessmentWeights, GradeAudit |
| finance | Financial | FeePlan, Invoice, Payment, PaymentReminder |
| payroll | Payroll | PayrollRun, Payslip |
| reports | Reports | ReportCardStyle, ScheduledReport |
| portal | Portals | PortalFeatureItem |
| analytics | Analytics | GradeImportJob |
| siteconfig | Configuration | SiteSettings, UserPreference |
| compliance | Security | AuditLog, AccessLog |
| communication | Messaging | Message, Announcement |
| requests | Access Requests | AccessRequest |
| observability | Monitoring | Various |
| api | REST API | N/A (serializers) |
| automation | Automation | AutomationExecutionLog, AutomationApprovalQueue |

---

**Total Apps**: 17 Django apps + 1 external module (emis)  
**Total Models**: 100+ database models  
**Total Views**: 200+ view functions  
**Total API Endpoints**: 50+ REST endpoints
