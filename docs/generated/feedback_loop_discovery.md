# Feedback Loop Discovery

RunMyCampus already had the core primitives needed for a platform-grade feedback loop: tenant isolation through `School`, user role context through `User.Role` and `SchoolMembership`, support/request workflows, customer success health/risk models, operator `/super/` surfaces, and audit-aware middleware.

The new implementation adds `apps/feedback/` as a bounded Voice of Customer domain instead of extending support tickets into product management.

## Reused Primitives

- Tenant: `apps.schools.School`
- User and role: `apps.accounts.User.Role`
- Membership and primary tenant lookup: `apps.schools.SchoolMembership`
- Operator surface: `/super/`
- Existing support/customer success context: `apps.requests`, `apps.siteconfig.GlobalSupportTicket`, `apps.customersuccess`
- Module access enforcement: `apps.accounts.permissions.MODULE_ACCESS_DEFAULTS`

## New App

`apps/feedback/` contains feedback submissions, feature requests, weighted votes, comments, attachments, triage events, roadmap items, release notes, and pulse survey responses.

Tenant routes:

- `/feedback/`
- `/school/feedback/`
- `/teacher/feedback/`
- `/parent/feedback/`
- `/student/feedback/`
- `/school/roadmap/`

Operator routes:

- `/super/voice-of-customer/`
- `/super/product-feedback/`
- `/super/product-roadmap/`

## Integration Path

Feedback is tenant-scoped by default. Parent and student users see only their own feedback. School operators see school-visible feedback. Platform operators see the full Voice of Customer queue.

Feature requests can receive weighted priority signals, but votes do not automatically advance items to roadmap status. Operator action is required to add a request to the roadmap.

## Gaps

Outbound notifications should be connected to the existing notification bus. AI classification and duplicate detection are future service extensions. The older `siteconfig.ProductFeedback` model remains as a legacy public roadmap primitive until it is intentionally migrated.
