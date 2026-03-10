# Bounded contexts and domain ownership

**Purpose:** Define the 11 formal bounded contexts for RunMyCampus. Cross-context coordination must go through service layers or application services; no ad hoc model imports across context boundaries. CI enforces control-plane boundary (see `apps.tenancy.tests.test_control_plane_boundary`); bounded-context import matrix is enforced by `scripts/lint_bounded_context_imports.py` when `BOUNDED_CONTEXT_STRICT=1`.

---

## 1. Identity & Access

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `accounts` |
| **Source-of-truth models** | User, Role, MFA, SecurityAuditLog, ImpersonationLog (siteconfig) |
| **Service boundary** | Authentication, authorization, RBAC, impersonation (audit-only from tenant) |
| **Event contracts** | user_created, user_updated, login, logout, mfa_enabled |
| **APIs exposed** | Auth endpoints, permission checks (`can`, `has_perm`), get_effective_policy for capabilities |

**Allowed to import from:** Runtime & Metadata (policies, platform_runtime for resolution only), Compliance (access_control).

---

## 2. People & Relationships

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `people` |
| **Source-of-truth models** | StudentProfile, TeacherProfile, GuardianProfile, Applicant, EmployerProfile |
| **Service boundary** | CRUD for person entities; admission number generation; relationship resolution |
| **Event contracts** | student_created, teacher_created, guardian_created, applicant_submitted, applicant_admitted |
| **APIs exposed** | People API, backend lists/forms; uses get_effective_policy for admissions/terminology |

**Allowed to import from:** Identity & Access (permissions), Academics (Classroom, Enrollment for links), Runtime & Metadata (policy), Events (emit_event).

---

## 3. Academics

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `academics` |
| **Source-of-truth models** | AcademicYear, Classroom, Course, Section, Enrollment, Attendance, Syllabus, HolidayCalendar, ReportCardStyleAssignment, RolloverProposal |
| **Service boundary** | Academic structure, enrollment, attendance, rollover; grading uses evals |
| **Event contracts** | enrollment_created, attendance_recorded, section_created, rollover_started |
| **APIs exposed** | Academics API, schedule, attendance; uses policy for grading scale/calendar |

**Allowed to import from:** People (StudentProfile, TeacherProfile), Identity (permissions), Evals (grades where needed), Runtime & Metadata, Events.

---

## 4. Admissions

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `people` (applicants), `schools` (signup, onboarding) |
| **Source-of-truth models** | Applicant, ApplicationStage; signup flow state |
| **Service boundary** | Application lifecycle, stages, decision; signup and onboarding wizards |
| **Event contracts** | applicant_submitted, applicant_admitted, applicant_rejected, onboarding_started |
| **APIs exposed** | Admissions API, backend applicant list; uses policy for admission_number and labels |

**Allowed to import from:** People, Identity, Runtime & Metadata, Events.

---

## 5. Finance

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `finance`, `billing` |
| **Source-of-truth models** | Invoice, Payment, FeeItem, LedgerAccount, PlatformLedgerEntry; billing Plan, Subscription |
| **Service boundary** | Invoicing, payments, ledger, payment processors; billing and entitlements |
| **Event contracts** | invoice_created, payment_received, refund_created |
| **APIs exposed** | Finance API, parent finance portal; uses policy for currency, reminders, labels |

**Allowed to import from:** People (guardians, students), Identity, Runtime & Metadata, Marketplace (entitlements via billing), Events.

---

## 6. Communications

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `communication` |
| **Source-of-truth models** | Message, Announcement, Channel, NotificationPreference |
| **Service boundary** | Send/receive messages, announcements, channels; notify guardians |
| **Event contracts** | message_sent, announcement_published, parent_notified |
| **APIs exposed** | Communication API, portal messaging; uses policy for templates and channels |

**Allowed to import from:** People, Identity, Runtime & Metadata, Events.

---

## 7. Runtime & Metadata

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `platform_runtime`, `policies`, `siteconfig`, `metadata`, `policies_rules` |
| **Source-of-truth** | TenantRuntime, get_effective_policy, TenantBlueprint, PolicyBundle, SiteSettings, WorkflowConfig, DashboardConfig, EntityCatalogEntry, FieldCatalogEntry, BusinessGlossaryEntry, MetadataChangeLog |
| **Service boundary** | Resolve runtime, policy, branding, workflows, dashboards, metadata catalog; no tenant business logic |
| **Event contracts** | blueprint_applied, workflow_activated, policy_updated |
| **APIs exposed** | Resolver APIs, config consoles, runtime inspector; consumed by all other contexts |

**Allowed to import from:** Control Plane (for registry/blueprint data), Identity (for audit), Marketplace (installed apps). Tenant apps must not import Runtime & Metadata models directly for tenant-varying behavior—use get_effective_policy, tenant_runtime, helpers only.

---

## 8. Marketplace

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `marketplace` |
| **Source-of-truth models** | MarketplaceApp, AppScope, AppInstallation, AppAuditLog, ScopeGrant, AppBillingLedger |
| **Service boundary** | App install/uninstall, scope grants, widget resolution; control-plane only for ORM |
| **Event contracts** | app_installed, app_uninstalled, scope_granted |
| **APIs exposed** | Install/uninstall services; get_installed_widgets(school); tenant code uses services only |

**Allowed to import from:** Runtime & Metadata, Billing, Control Plane. Tenant apps must not import marketplace.models (enforced by test_control_plane_boundary).

---

## 9. Migration Cloud

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `automation` |
| **Source-of-truth models** | MigrationProfile, MigrationRun, AutomationExecutionLog, AutomationApprovalQueue |
| **Service boundary** | Migration runs, profiles, dry-run, scorecard, rollback; operator-facing |
| **Event contracts** | migration_started, migration_completed, migration_failed |
| **APIs exposed** | Migration cloud UI at /super/migration/; migration wizard; uses migration services |

**Allowed to import from:** Control Plane, Schools (super_views), Academics/People/Finance (for mapping and import), Events.

---

## 10. Analytics & Intelligence

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `analytics`, `observability`, `reports` |
| **Source-of-truth** | Analytics models, SLOs, report definitions; read-only aggregation over other contexts |
| **Service boundary** | Dashboards, risk scores, report generation; no direct write to core domains |
| **Event contracts** | report_generated, alert_raised |
| **APIs exposed** | Analytics API, report runner, observability endpoints; uses policy for labels |

**Allowed to import from:** All tenant contexts (read-only for aggregation), Runtime & Metadata, Identity (for scoping).

---

## 11. Control Plane

| Attribute | Value |
|-----------|--------|
| **Owning app(s)** | `schools` (super_views, control plane), `tenancy`, `customers` (django-tenants) |
| **Source-of-truth** | School, Client, Domain, tenant lifecycle; super admin UI |
| **Service boundary** | Tenant provisioning, health, usage, migration cloud UI; no tenant business logic |
| **Event contracts** | tenant_created, tenant_suspended |
| **APIs exposed** | Manager URLs /super/*; tenant-facing code must not import control-plane ORM |

**Allowed to import from:** All apps for control-plane operations only (manager host). Tenant apps must not import control-plane models (enforced by test_control_plane_boundary).

---

## Cross-context rules

- **No ad hoc model grabbing across domains.** Use application services or published events.
- **Cross-context coordination:** Service layer or event emission (emit_event); then consumer in the other context.
- **Document allowed imports:** See "Allowed to import from" per context above. CI: `scripts/lint_bounded_context_imports.py` (with BOUNDED_CONTEXT_STRICT=1) and `apps.tenancy.tests.test_control_plane_boundary`.

---

## App-to-context mapping (reference)

| App label | Primary bounded context |
|-----------|--------------------------|
| accounts | Identity & Access |
| people | People & Relationships, Admissions (applicants) |
| academics | Academics |
| schools | Control Plane, Admissions (signup/onboarding) |
| finance | Finance |
| billing | Finance (entitlements, plans) |
| communication | Communications |
| platform_runtime | Runtime & Metadata |
| policies | Runtime & Metadata |
| siteconfig | Runtime & Metadata |
| metadata | Runtime & Metadata |
| policies_rules | Runtime & Metadata |
| marketplace | Marketplace |
| automation | Migration Cloud |
| analytics | Analytics & Intelligence |
| observability | Analytics & Intelligence |
| reports | Analytics & Intelligence |
| evals | Academics (grading) / Runtime (policy) |
| portal | Tenant plane shell; uses all via runtime/policy |
| tenancy | Control Plane / infrastructure |
| customers | Control Plane |
