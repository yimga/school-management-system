"""
Human-authored runbooks for high-stakes Phase 9 workflows (batch 1487).

Overrides audit-generated stubs during seed. Each entry must pass
``verify_workflow_kb_editorial.py`` (min length + required sections).
"""

from __future__ import annotations

from typing import Any

HIGH_STAKES_WORKFLOW_IDS: frozenset[str] = frozenset(
    {
        "tenant-compliance-erasure-request",
        "tenant-reports-publish-term",
        "tenant-migration-cloud-connector-import",
        "operator-platform-runtime-pack-rollback",
        "operator-platform-runtime-blueprint-apply",
        "operator-schools-create-school-wizard",
        "operator-schools-onboard-wizard",
        "tenant-accounts-mfa-setup",
        "tenant-accounts-onboarding-wizard",
        "tenant-customersuccess-guided-onboarding",
        "tenant-accounts-migration-wizard",
        "tenant-finance-payment-readiness",
        "operator-migration-cloud-guardian-consent",
        "tenant-payroll-create-run",
    }
)

EDITORIAL_WORKFLOW_KB_CORPUS: tuple[dict[str, Any], ...] = (
    {
        "workflow_id": "tenant-compliance-erasure-request",
        "slug": "tenant-compliance-erasure-request",
        "title": "Submit a data erasure (DSAR) request",
        "summary": "Legally load-bearing erasure workflow — verify identity, scope, and counsel checkpoints before approve.",
        "category_slug": "compliance",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "compliance,dsar,erasure,ferpa,gdpr,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Before you start</h2>
<p>Erasure requests are <strong>legally load-bearing</strong>. Do not use this flow for routine account lockouts or password resets. See the operator DSAR runbook for retention exceptions.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm the requester is the data subject or an authorized guardian (verified out-of-band).</li>
<li>Record the jurisdiction (GDPR, FERPA, state privacy law) and expected SLA (typically 30 days).</li>
<li>Identify systems touched: SIS records, finance ledger, communications, migration artifacts.</li>
<li>Check for legal holds, active disputes, or open finance balances that block erasure.</li>
</ul>
<h3>Steps in RunMyCampus</h3>
<ol>
<li>Open <strong>Compliance → Erasure requests</strong> from Configure or the backend dashboard.</li>
<li>Create a request with student/staff identifier, request channel, and verification method used.</li>
<li>Attach counsel-approved scope notes — which domains may be purged vs anonymized.</li>
<li>Route to school admin reviewer; do <em>not</em> self-approve your own submission.</li>
<li>After approval, monitor the job status; failed rows land in quarantine for manual review.</li>
</ol>
<h3>When to escalate</h3>
<p>Escalate to platform support only after school counsel signs off. Never paste raw student PII into support tickets.</p>
<p><strong>Operator reference:</strong> docs/DSAR_RUNBOOK.md</p>
        """,
    },
    {
        "workflow_id": "tenant-reports-publish-term",
        "slug": "tenant-reports-publish-term",
        "title": "Publish a term (irreversible)",
        "summary": "Pre-flight checklist before term publish — parent visibility, grades lock, and rollback limits.",
        "category_slug": "reporting",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "reports,term,publish,irreversible,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Critical warning</h2>
<p><strong>Term publish is largely irreversible.</strong> Parents and students may immediately see report cards and term marks. Run this only after academic leadership signs off.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>All grade approval queues for the term show <strong>complete</strong> (no pending teacher rows).</li>
<li>Import monitor shows zero fatal errors for the term window.</li>
<li>Promotion preview reviewed — unexpected retentions or skips resolved.</li>
<li>Communications team ready for parent notification (if your policy requires it).</li>
<li>Backup/export snapshot taken for the term (regulatory export if required).</li>
</ul>
<h3>Publish steps</h3>
<ol>
<li>Open <strong>Reports → Term publish</strong> (or the term publish status evidence page).</li>
<li>Select the academic year and term; review the live preview counts (students affected, classes).</li>
<li>Resolve validation blockers listed on the page — do not override silently.</li>
<li>Confirm publish with your admin password / MFA step when prompted.</li>
<li>Verify parent portal shows the term for a test parent account before announcing widely.</li>
</ol>
<h3>Rollback</h3>
<p>Rollback may be unavailable or partial after publish. Contact platform support with term ID and publish timestamp if counsel directs a correction.</p>
        """,
    },
    {
        "workflow_id": "tenant-migration-cloud-connector-import",
        "slug": "tenant-migration-cloud-connector-import",
        "title": "Migration Cloud connector import (school admin)",
        "summary": "Land vendor CSV through the connector wizard — quarantine, map, validate, then apply.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "migration,connector,import,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>The connector wizard imports vendor exports into the canonical model. <strong>Nothing applies to live tenant data</strong> until you explicitly pass validate → import with admin confirmation.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Export from your SIS using the vendor's official export UI (do not use unofficial scrapers).</li>
<li>Prefer canonical CSV templates from Migration Cloud → Templates.</li>
<li>Ensure MAA (Migration Authorization Agreement) is signed for this intake if prompted.</li>
</ul>
<h3>Wizard steps</h3>
<ol>
<li>Open <strong>Configure → Migration Cloud → Connector</strong> and start a new connection.</li>
<li>Upload the file; review detected vendor fingerprint and column mapping hits (≥3 required).</li>
<li>Fix quarantine rows (encoding, date formats, missing student IDs) before continuing.</li>
<li>Run validate — resolve all blocking errors; warnings may proceed with documented acceptance.</li>
<li>Import to staging batch first; compare counts with source export.</li>
<li>Apply only after second admin review when your policy requires dual control.</li>
</ol>
<p><strong>Reference:</strong> docs/COMPANION_SIBLINGS_HANDSHAKE_AND_CSV_INGEST.md</p>
        """,
    },
    {
        "workflow_id": "operator-platform-runtime-pack-rollback",
        "slug": "operator-platform-runtime-pack-rollback",
        "title": "Rollback a platform runtime pack (operators)",
        "summary": "High-stakes rollback — verify blast radius, tenant pin state, and audit trail before revert.",
        "category_slug": "operations",
        "target_roles": [],
        "help_audience": "OPERATOR",
        "tags": "operator,rollback,runtime,pack,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>When to rollback</h2>
<p>Use pack rollback when a promoted runtime pack causes widespread tenant misconfiguration, broken defaults, or security regression. This affects <strong>all tenants pinned to the pack</strong>.</p>
<h3>Pre-flight</h3>
<ul>
<li>Identify pack version, promotion timestamp, and number of pinned tenants.</li>
<li>Open observability incidents / tenant health for correlated error spikes.</li>
<li>Confirm target rollback version in change-requests with approver name.</li>
<li>Notify customer success if &gt;10 production tenants are pinned.</li>
</ul>
<h3>Rollback steps</h3>
<ol>
<li>Navigate to <strong>Control → Platform runtime → Pack rollback</strong> on the manager host.</li>
<li>Select source pack and target rollback version; read the diff summary.</li>
<li>Run dry-run impact preview — note tenants that will receive cascade refresh.</li>
<li>Execute rollback during the approved change window; stay on the audit feed until complete.</li>
<li>Spot-check two tenants (small + large) on Configure hub after rollback.</li>
</ol>
        """,
    },
    {
        "workflow_id": "operator-platform-runtime-blueprint-apply",
        "slug": "operator-platform-runtime-blueprint-apply",
        "title": "Apply a platform runtime blueprint (operators)",
        "summary": "Promote blueprint packs to tenants — irreversible config cascade; requires change request.",
        "category_slug": "operations",
        "target_roles": [],
        "help_audience": "OPERATOR",
        "tags": "operator,blueprint,runtime,apply,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>Blueprint apply pushes packaged defaults (modules, feature flags, grading templates) into tenant runtime. Treat as a <strong>production change</strong>.</p>
<h3>Pre-flight</h3>
<ul>
<li>Change request approved with linked blueprint version and tenant allowlist.</li>
<li>Staging tenant validated with the same blueprint hash.</li>
<li>Rollback pack version identified before apply (see pack rollback runbook).</li>
</ul>
<h3>Apply steps</h3>
<ol>
<li>Open <strong>Control → Implementation command center</strong> or blueprint apply surface.</li>
<li>Select blueprint slug and target tenant cohort (never “all tenants” without exec signoff).</li>
<li>Review evidence bundle — 403-test posture and apicenter import flags when shown.</li>
<li>Apply in waves (pilot → cohort → remainder) when more than 25 tenants.</li>
<li>Monitor tenant health dashboard for 24h after apply.</li>
</ol>
        """,
    },
    {
        "workflow_id": "operator-schools-create-school-wizard",
        "slug": "operator-schools-create-school-wizard",
        "title": "Provision a new school tenant (operators)",
        "summary": "Create-school wizard — subdomain, schema, plan, and initial admin user without orphan tenants.",
        "category_slug": "system-admin",
        "target_roles": [],
        "help_audience": "OPERATOR",
        "tags": "operator,provision,school,wizard,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>Creates an isolated tenant schema, subdomain routing, and bootstrap admin. Incorrect subdomain or plan tier is expensive to fix.</p>
<h3>Checklist</h3>
<ul>
<li>Subdomain slug is unique and matches customer contract (lowercase, no spaces).</li>
<li>Plan tier matches billing (trial vs paid modules).</li>
<li>Initial admin email is customer-owned — not a shared inbox.</li>
<li>Region / grading pack selected matches customer geography.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>From <strong>Home → Schools → Create school</strong>, start the wizard.</li>
<li>Enter legal school name, subdomain, timezone, and default locale.</li>
<li>Assign plan and module bundle; enable Migration Cloud only when contracted.</li>
<li>Submit — wait for schema-ready signal before sending login instructions.</li>
<li>Verify tenant login on subdomain and manager 360 view shows healthy status.</li>
</ol>
        """,
    },
    {
        "workflow_id": "operator-schools-onboard-wizard",
        "slug": "operator-schools-onboard-wizard",
        "title": "Operator onboarding wizard",
        "summary": "Guide a new customer from contract to go-live — checkpoints, not a single button.",
        "category_slug": "system-admin",
        "target_roles": [],
        "help_audience": "OPERATOR",
        "tags": "operator,onboarding,customer-success,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Purpose</h2>
<p>Tracks operator-facing onboarding from tenant creation through go-live. Each step gates the next.</p>
<ol>
<li>Confirm school tenant exists and admin can log in.</li>
<li>Complete guided configuration (brand, academic year, grading scale).</li>
<li>Run Migration Cloud intake OR manual roster import — not both as source of truth.</li>
<li>Payment readiness checklist green before enabling parent billing.</li>
<li>Customer success signoff recorded in onboarding wizard before “go-live” flag.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-accounts-mfa-setup",
        "slug": "tenant-accounts-mfa-setup",
        "title": "Set up multi-factor authentication (MFA)",
        "summary": "Avoid lockouts — enroll backup codes and test before enforcing org-wide MFA policy.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN", "TEACHER"],
        "help_audience": "TENANT",
        "tags": "security,mfa,accounts,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>MFA protects admin and teacher accounts. Enforcing MFA school-wide before users enroll causes lockouts.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm break-glass superadmin credentials are in the vault — never in email.</li>
<li>Choose TOTP app or SMS delivery and test with IT admin accounts first.</li>
<li>Communicate enrollment deadline to staff with the help center MFA link.</li>
</ul>
<h3>Recommended rollout</h3>
<ol>
<li>Pilot with IT admin accounts first; verify TOTP app or SMS delivery.</li>
<li>Communicate enrollment deadline to staff; provide help center link.</li>
<li>Enable optional MFA, then required MFA after 95% enrollment.</li>
<li>Keep break-glass superadmin credentials in vault — never in email.</li>
</ol>
<h3>User steps</h3>
<ol>
<li>Open profile → Security → Enable MFA.</li>
<li>Scan QR with authenticator app; save backup codes offline.</li>
<li>Log out and verify login with MFA code before closing the session.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-accounts-onboarding-wizard",
        "slug": "tenant-accounts-onboarding-wizard",
        "title": "School onboarding wizard (first-time setup)",
        "summary": "Complete tenant setup in order — skipping steps causes downstream grade, finance, and portal errors.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "onboarding,setup,wizard,admin,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Order matters</h2>
<p>The onboarding wizard sequences dependencies: academic structure before enrollments, enrollments before timetables, timetables before teacher assignments.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm academic year dates with leadership before creating terms.</li>
<li>Decide roster source: Migration Cloud intake OR manual import — not both as source of truth.</li>
<li>Assign a school admin owner for each wizard section.</li>
</ul>
<h3>Setup sequence</h3>
<ol>
<li>Academic years and terms</li>
<li>Departments and subjects</li>
<li>Grading scales and assessment components</li>
<li>Roster import or manual student create</li>
<li>Staff accounts and role assignment</li>
<li>Parent portal policy and communications defaults</li>
</ol>
<p>Resume from the onboarding hub — completed steps stay green; do not reset unless counsel directs a full re-import.</p>
        """,
    },
    {
        "workflow_id": "tenant-customersuccess-guided-onboarding",
        "slug": "tenant-customersuccess-guided-onboarding",
        "title": "Guided onboarding (customer success track)",
        "summary": "Customer-facing onboarding hub — milestones, owner assignments, and blockers visible to CS.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "onboarding,customer-success,milestones",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>Wraps the school onboarding wizard with customer-success milestones (kickoff, data load, UAT, go-live).</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Assign school admin and RunMyCampus CS owners for each milestone.</li>
<li>Confirm payment readiness, term structure, and at least one admin MFA enrolled before go-live.</li>
</ul>
<h3>Milestone flow</h3>
<ol>
<li>Kickoff — scope, timeline, and data sources agreed.</li>
<li>Data load — Migration Cloud or roster import complete with quarantine cleared.</li>
<li>UAT — test parent and teacher accounts verified on tenant subdomain.</li>
<li>Go-live — CS signoff recorded; blockers cleared on CS dashboard.</li>
</ol>
<ul>
<li>Each milestone has an owner (school admin vs RunMyCampus CS).</li>
<li>Blockers surface to CS dashboard — resolve before advancing stage.</li>
</ul>
        """,
    },
    {
        "workflow_id": "tenant-accounts-migration-wizard",
        "slug": "school-admin-migration-cloud-intake",
        "title": "Start a Migration Cloud intake (school admins)",
        "summary": "Land SIS exports safely with MAA, quarantine review, and dual-control apply.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "admin,migration,import,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>Migration Cloud bundles exports, maps fields to the canonical model, and requires review before apply.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm MAA is signed for this intake when prompted.</li>
<li>Export from the SIS official UI; prefer canonical CSV templates.</li>
<li>Assign a second reviewer if your policy requires dual control on apply.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open <strong>Migration Cloud</strong> from Configure or the admin menu.</li>
<li>Start intake; choose method (CSV upload, companion export, connector).</li>
<li>Complete MAA when prompted — records authorized scope and signer.</li>
<li>Review quarantine and conflict rows; never bulk-apply with unresolved PK conflicts.</li>
<li>Second reviewer approves apply when your policy requires dual control.</li>
</ol>
<p>Operator runbooks: companion export procedures on manager Migration Cloud console.</p>
        """,
    },
    {
        "workflow_id": "tenant-finance-payment-readiness",
        "slug": "school-admin-payment-readiness",
        "title": "Payment readiness checklist (school admins)",
        "summary": "Gateway, fee structures, test payments, and parent comms before go-live billing.",
        "category_slug": "finance",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "admin,finance,payments,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Before opening online payments</h2>
<h3>Pre-flight checklist</h3>
<ol>
<li>Fee structures and billing periods configured in Finance.</li>
<li>Payment gateway connected in site settings — <strong>test mode first</strong>.</li>
<li>Run a small test payment with a staff account; verify receipt and ledger entry.</li>
<li>Suspense queue empty or triaged for test transactions.</li>
<li>Publish parent fee notice from Communications when ready.</li>
<li>Disable test mode only after finance lead signoff.</li>
</ol>
<p>Money paths: never share gateway secrets in support tickets or KB comments.</p>
        """,
    },
    {
        "workflow_id": "operator-migration-cloud-guardian-consent",
        "slug": "operator-migration-cloud-guardian-consent",
        "title": "Guardian consent for Migration Cloud (operators)",
        "summary": "Legally load-bearing consent collection before minor data migration.",
        "category_slug": "compliance",
        "target_roles": [],
        "help_audience": "OPERATOR",
        "tags": "operator,migration,consent,guardian,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>Guardian consent flow collects verifiable approval before migrating student PII from legacy systems.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm tenant intake is in <strong>awaiting consent</strong> state.</li>
<li>Use approved school email/SMS channel per counsel template.</li>
<li>Record consent threshold required before student domain apply.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Confirm tenant intake is in <strong>awaiting consent</strong> state.</li>
<li>Send consent links via approved channel (school email/SMS policy).</li>
<li>Track completion in Migration Cloud guardian consent dashboard.</li>
<li>Do not apply student domain rows until consent threshold met per counsel template.</li>
<li>Archive consent artifacts per retention policy.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-payroll-create-run",
        "slug": "tenant-payroll-create-run",
        "title": "Create a payroll run",
        "summary": "Money path — validate periods, deductions, and approval chain before submit.",
        "category_slug": "finance",
        "target_roles": ["ADMIN"],
        "help_audience": "TENANT",
        "tags": "payroll,finance,high-stakes",
        "editorial_tier": "high_stakes",
        "content": """
<h2>Overview</h2>
<p>Payroll runs aggregate staff pay for a period. Errors affect legal tax reporting.</p>
<h3>Pre-flight</h3>
<ul>
<li>Pay period dates match HR records.</li>
<li>New hires and terminations reflected in staff roster.</li>
<li>Deductions and benefits updated for the period.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open <strong>Payroll → Create run</strong>; select period.</li>
<li>Review calculated lines; resolve exceptions (missing bank details, zero hours).</li>
<li>Route to approver per school policy.</li>
<li>Export audit PDF before final submit if required.</li>
<li>Submit — monitor for gateway/processor callbacks if integrated.</li>
</ol>
        """,
    },
)

EDITORIAL_BY_WORKFLOW_ID: dict[str, dict[str, Any]] = {
    row["workflow_id"]: row for row in EDITORIAL_WORKFLOW_KB_CORPUS
}
