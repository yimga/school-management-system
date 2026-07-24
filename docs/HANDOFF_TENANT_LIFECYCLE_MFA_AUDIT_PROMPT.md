# RunMyCampus tenant lifecycle, identity, MFA, and day-2 audit prompt

Use this prompt from the repository root. Treat every named production mutation
as fail-closed: verify the exact environment, school UUID, slug, hostname, and
database before writing anything.

---

You are the senior Django, identity-security, multi-tenant, data-migration, and
production-readiness engineer for RunMyCampus. Audit and repair the entire
operator-to-tenant lifecycle end to end. Do not stop at source assertions or
mock-only tests. Implement the fixes, apply required migrations in the correct
environment, validate real host routing, capture evidence, commit the intended
changes, push the branch, and report deployment and rollback steps.

## Immutable contracts

Treat these as the visual and behavioral source of truth:

- `docs/HANDOFF_DJANGO_ADMIN_APPROVAL_HTML.md`
- `var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html`
- `var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html`

Preserve the operator/tenant boundaries in those contracts. A school owner is a
tenant-scoped owner (`SchoolMembership.is_school_owner=True`, tenant role
`ADMIN`); it is not a platform `SUPERADMIN`, Django `is_superuser`, or global
operator.

## Production target requiring a guarded owner invitation

- School UUID: `f984ea95-d2ad-4900-b513-66a345928316`
- School slug: `gilead-tech`
- Tenant hostname: `gilead-tech.runmycampus.com`
- Invite email and resulting username: `yimgah@yahoo.com`

Never create or send this invitation until:

1. the active production environment and production database are confirmed;
2. both UUID and slug resolve to the same active school;
3. migrations are current;
4. no conflicting email or username identity exists;
5. the deployed revision contains the guarded owner-invite workflow; and
6. transactional email configuration and delivery/queue health are verified.

Run the invitation command first with `--dry-run`, inspect its output and audit
context, then run it once without `--dry-run`. Do not create a platform
superuser. Confirm that delivery was accepted or queued and that exactly one
pending, unexpired owner invite exists. Never paste the invitation token into a
public log or report.

## Required lifecycle audit

Trace and test all entry paths that can create or activate a school:

- operator-created school;
- self-service signup, where enabled;
- provisioning retries and idempotency;
- initial owner setup email and resend;
- additional school-owner invitation;
- expired, already-used, suppressed-email, duplicate-email, wrong-host, and
  inactive-school cases;
- partial failures between school, membership, defaults, entitlements, domain,
  jobs, email, migration workspace, and audit-event creation;
- retry, compensation, rollback, and operator recovery controls.

For every path, identify the transaction boundary and durable lifecycle state.
Prove retries cannot create duplicate schools, owners, memberships, invitations,
jobs, imports, or email deliveries.

## First-time identity and MFA contract

For a new initial or additional school owner, enforce this sequence:

1. use the tenant-specific, single-use, expiring invitation;
2. set a policy-valid password;
3. authenticate into the intended tenant only;
4. enroll a confirmed TOTP authenticator or supported passkey;
5. generate and present recovery codes safely;
6. choose whether to trust the current browser;
7. if trusted, choose exactly `1`, `7`, `14`, or `30` days;
8. enter the tenant workspace only after mandatory MFA enrollment succeeds.

Operator `SUPERADMIN`/`is_superuser` principals and active school owners must
always use strict MFA enrollment. Tenant optional/grace policy must never weaken
that floor. A trusted-browser waiver applies only after successful MFA proof; it
does not waive initial enrollment.

Prove the `1/7/14/30` choice is real on both manager/operator and tenant hosts:

- the selected value controls the signed token expiry and cookie `Max-Age`;
- arbitrary, negative, zero, malformed, or over-cap client values cannot extend
  trust;
- normal logout, re-login, session expiry, and session rotation retain trust for
  exactly the selected period;
- “Log out and forget this browser,” password reset/change, account disable,
  owner suspension, and explicit security revocation invalidate it;
- expiry forces a fresh MFA challenge;
- the cookie is signed, HttpOnly, Secure in production, SameSite-appropriate,
  password-bound, and no broader in domain than the authenticated cross-host
  session contract;
- the token cannot be replayed for another user;
- tenant and operator routing do not bypass enrollment, challenge, suspension,
  or scope checks.

Exercise TOTP, recovery-code, and passkey verification paths. Validate MFA setup
and verify pages on `manager.runmycampus.com` and the real tenant hostname; do
not rely on `127.0.0.1`, because host routing selects different sites and policy.

## Data migration into a newly created school

Trace the migration-cloud intake and import lifecycle from tenant creation
through steady state:

- tenant binding and authorization;
- upload validation and malware/content checks;
- connector/token provisioning;
- staging isolation and row-level tenant scoping;
- schema mapping, transformations, reconciliation, exception queues, and
  approval gates;
- dry-run/diff, cutover, rollback, resumability, and idempotency;
- files, jobs, artifacts, logs, and generated records carrying the correct
  school UUID;
- no cross-tenant object reference, cache key, task payload, export, audit log,
  or storage prefix;
- progress/status visibility for tenant and operator without leaking data;
- retention, deletion, DSAR, legal hold, and audit evidence.

Create a fresh disposable tenant and run a representative import. Prove counts,
relationships, financial precision, attendance/grade semantics, user identity
mapping, duplicate handling, restart behavior, and rollback. Do not point a
destructive test at `gilead-tech`.

## Continuous management and day-2 operations

Audit:

- adding/removing/suspending owners and staff;
- role and membership changes;
- password/MFA recovery with dual-control or equivalent audited authority;
- domain/slug changes and redirects;
- email resend/suppression recovery;
- feature, entitlement, billing, and runtime-default changes;
- import reruns and incremental sync;
- support impersonation/read-only controls;
- exports, audit search, incident investigation, and access reviews;
- school disable/reactivate/offboard/delete;
- background jobs, scheduled tasks, dead-letter/retry queues, monitoring, SLOs,
  backups, restore drills, and runbooks.

Every operator action must be authorized, tenant-scoped where applicable,
audited with actor/target/reason/correlation ID, and reversible where the product
claims reversibility.

## Django admin parity and functionality

Audit every operator-wide and tenant-wide Django admin surface: index, app
index, changelist, add, change, history, delete, delete-selected, guided actions,
Site Settings, Schools, registries, and specialized templates.

Trace `PlatformAdminSite` and `TenantAdminSite` inheritance, template blocks,
partials, CSS order, JavaScript ownership, static resolution, cache busting,
service-worker versions, host routing, tenant scoping, and migration state.
Enforce:

- operator grid: `minmax(0,1fr) minmax(9.2rem,17%) 2.35rem`;
- tenant grid: `minmax(0,1fr) minmax(9.5rem,18%) 2.35rem`;
- one column at `1024px` and below;
- full-width content surfaces and native Django tables;
- compact split Save actions;
- page-aware right rail and tool strip;
- operator CTAs only on the operator index;
- no Studio, Invite School, fleet, or operator controls on tenant pages;
- no duplicate shell/header/breadcrumb/navigation/drawer/fixed overlay;
- no simulated controls;
- all stylesheet links owned by `<head>`;
- build ID, cache-bust ID, and service-worker version bumped together.

## Required validation and evidence

Run at minimum:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate --plan`
- the actual required migration in the target environment
- `python manage.py collectstatic --dry-run --noinput`
- Django template compilation
- provisioning and owner-onboarding tests
- tenant identity/invitation tests
- tenant and operator MFA routing, strictness, trust-duration, expiry, logout,
  revocation, TOTP, recovery-code, and passkey tests
- migration-cloud isolation, reconciliation, cutover, retry, and rollback tests
- admin preview-parity audit
- admin leftovers audit
- platform-wide sweep
- miss-nothing audit
- service-worker monotonicity check
- `git diff --check`

Test authenticated real-host routes at `1440`, `1024`, `768`, and `390px` in
light and dark themes. For every valid scoped route assert HTTP 200, expected
hostname/site/school, one visible H1, no horizontal overflow, no broken
resources, no duplicate CSS URL, no stylesheet in body, no unexpected fixed
overlay, no raw unrendered icon name, native table display, valid CSRF, and
working form actions.

Capture sanitized screenshots plus DOM/computed-style, redirect-chain,
cookie-attribute, database-state, queued-email, background-job, and audit-event
evidence. Remove stale failure artifacts before the final rerun.

## Required final report

Report:

- exact root causes and affected flows;
- security and tenant-isolation impact;
- changed files and migrations;
- before/after redirect and state-machine behavior;
- exact commands and pass/fail counts;
- production school/invite verification without disclosing its token;
- evidence locations;
- any remaining blocker with the exact external permission or secret required;
- deployment order, predeploy migration, smoke tests, monitoring, and rollback;
- commit SHA, pushed branch, and pull request.

Do not claim an invitation was sent merely because a local test or dry run
passed. Do not claim production readiness while deployment, migrations, email
delivery, real-host testing, or required evidence is still outstanding.
