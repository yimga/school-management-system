"""
Phase 9 P0 workflow KB articles — teacher/parent/school_admin how-tos.

Idempotent seed via ``seed_workflow_kb_corpus`` management command.
"""

from __future__ import annotations

from typing import Any

WORKFLOW_KB_CORPUS: tuple[dict[str, Any], ...] = (
    {
        "workflow_id": "tenant-evals-grade-approval",
        "slug": "teacher-grade-approval-workflow",
        "title": "Approve and publish grades (teachers)",
        "summary": "Review submitted marks, resolve blockers, and publish gradebooks for the term.",
        "category_slug": "grading-assessment",
        "target_roles": ["TEACHER", "ADMIN"],
        "tags": "teacher,grades,approval,evals",
        "content": """
<h2>When to use this guide</h2>
<p>Use this when you need to review class marks before they appear on report cards or the parent portal.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Import monitor shows complete with zero fatal errors for this assessment window.</li>
<li>Offline sync conflicts resolved if you use offline grade entry.</li>
<li>Term and class filters match the roster you taught.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open <strong>Grading → Grade approval</strong> from your teacher dashboard.</li>
<li>Filter by class or assessment period.</li>
<li>Open each pending row and confirm marks match your gradebook source.</li>
<li>Resolve validation warnings (missing components, out-of-range scores) before approving.</li>
<li>Submit for school-admin publish when your queue is clear.</li>
</ol>
<h3>Escalation</h3>
<p>Contact your school admin if publish is blocked after approval — do not override validation warnings.</p>
        """,
    },
    {
        "workflow_id": "tenant-evals-grade-import",
        "slug": "teacher-grade-import-how-to",
        "title": "Import grades from spreadsheet (teachers)",
        "summary": "Upload CSV or Excel exports, map columns, and monitor the import job.",
        "category_slug": "grading-assessment",
        "target_roles": ["TEACHER", "ADMIN"],
        "tags": "teacher,import,grades,csv",
        "content": """
<h2>Overview</h2>
<p>Import grades from a spreadsheet when your source system exports CSV or Excel.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Export includes student ID or admission number in the first column.</li>
<li>Remove merged header rows — one row per student per assessment.</li>
<li>Confirm UTF-8 encoding if names contain accents.</li>
</ul>
<h3>Upload steps</h3>
<ol>
<li>Go to <strong>Grading → Import grades</strong>.</li>
<li>Choose v1 (simple) or v2 (column mapping wizard) based on your file shape.</li>
<li>Preview the first 10 rows — fix encoding issues before committing.</li>
<li>Start the job and open <strong>Import monitor</strong> for progress.</li>
</ol>
<h3>After import</h3>
<p>Run grade approval only after the job status shows complete with zero fatal errors.</p>
        """,
    },
    {
        "workflow_id": "tenant-academics-syllabus-approval",
        "slug": "teacher-syllabus-submission",
        "title": "Submit a syllabus for approval (teachers)",
        "summary": "Upload or edit syllabus content and route it to your school admin reviewer.",
        "category_slug": "grading-assessment",
        "target_roles": ["TEACHER"],
        "tags": "teacher,syllabus,academics",
        "content": """
<h2>Overview</h2>
<p>Schools may require syllabus approval before term start. Submit early so admins can review before classes begin.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Use the school template if your admin published one.</li>
<li>Confirm subject, class, and term match your assignment.</li>
<li>Include assessment components your school requires.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open your class or subject workspace.</li>
<li>Attach or paste the syllabus using the school template if provided.</li>
<li>Submit for review — you will be notified when approved or if changes are requested.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-portal-photo-upload",
        "slug": "parent-student-photo-upload",
        "title": "Upload or update a student photo (parents)",
        "summary": "Use the secure photo link from your school to upload a portrait for ID cards and records.",
        "category_slug": "student-management",
        "target_roles": ["PARENT", "STUDENT"],
        "tags": "parent,photo,upload,mobile",
        "content": """
<h2>Getting started</h2>
<p>Your school sends a time-limited link by SMS or email. Open it on your phone for the best camera experience.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Link is still valid — request a new one from the school office if expired.</li>
<li>Photo meets school dress-code guidance when provided.</li>
<li>File is JPEG or PNG under the size limit on the upload page.</li>
</ul>
<h3>Tips for a good photo</h3>
<ul>
<li>Plain background, face centered, no filters.</li>
<li>Good lighting — avoid heavy shadows on the face.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open the secure link from your school on your phone or computer.</li>
<li>Select or capture a portrait photo meeting the checklist above.</li>
<li>Submit and wait for the confirmation message.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-parent-view-grades",
        "slug": "parent-view-child-grades",
        "title": "View your child's grades (parents)",
        "summary": "Find published report cards and term marks in the parent portal.",
        "category_slug": "grading-assessment",
        "target_roles": ["PARENT"],
        "tags": "parent,grades,report-card",
        "content": """
<h2>Overview</h2>
<p>Published grades appear only after your school releases the term to parents.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Sign in with the parent account linked to your child.</li>
<li>Confirm the correct child is selected on the dashboard.</li>
<li>Check that the term you expect has been published by the school.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Sign in to the parent portal and select your child if prompted.</li>
<li>Open <strong>Grades</strong> or <strong>Report cards</strong> from the dashboard.</li>
<li>Choose the term — only published terms appear (your school controls release dates).</li>
</ol>
<p>If grades are missing, contact the school office — teachers may still be in the approval workflow.</p>
        """,
    },
    {
        "workflow_id": "tenant-parent-contact-school",
        "slug": "parent-contact-school-office",
        "title": "Contact your school (parents)",
        "summary": "Reach the school office for attendance, fees, or student-specific questions.",
        "category_slug": "communication",
        "target_roles": ["PARENT"],
        "tags": "parent,contact,support",
        "content": """
<h2>School vs platform support</h2>
<p><strong>School contact</strong> is for student-specific issues (fees, attendance, pickup). <strong>Platform support</strong> is for login or app problems.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Have student name, class, and a short subject line ready.</li>
<li>Use the school lane — not platform support — for fee or attendance questions.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>From Help center, open <strong>Contact support</strong> or <strong>Contact school</strong>.</li>
<li>Choose the correct lane — school messages go to your office inbox.</li>
<li>Include student name, class, and a short subject line.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-accounts-migration-wizard",
        "slug": "school-admin-migration-cloud-intake",
        "title": "Start a Migration Cloud intake (school admins)",
        "summary": "Land SIS exports safely with guardrails before data applies to your tenant.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN"],
        "tags": "admin,migration,import",
        "content": """
<h2>Overview</h2>
<p>Migration Cloud bundles exports, maps fields to the canonical model, and requires review before apply.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Complete MAA when prompted — records authorized scope.</li>
<li>Export from the SIS official UI; prefer canonical CSV templates.</li>
<li>Assign a second reviewer if dual control is required.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open <strong>Migration Cloud</strong> from Configure or the admin menu.</li>
<li>Start a new migration and choose your intake method (CSV upload, companion export, etc.).</li>
<li>Review conflicts and quarantine rows before final apply.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-finance-payment-readiness",
        "slug": "school-admin-payment-readiness",
        "title": "Payment readiness checklist (school admins)",
        "summary": "Configure fee structures, gateways, and receipts before parents pay online.",
        "category_slug": "finance",
        "target_roles": ["ADMIN"],
        "tags": "admin,finance,payments",
        "content": """
<h2>Before opening online payments</h2>
<h3>Pre-flight checklist</h3>
<ol>
<li>Confirm fee structures and billing periods in Finance.</li>
<li>Connect your payment gateway in site settings (test mode first).</li>
<li>Run a small test payment with a staff account.</li>
<li>Publish parent-facing fee notices from Communications when ready.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-portal-configure-hub",
        "slug": "school-admin-configure-hub",
        "title": "Configure your school (admin hub)",
        "summary": "Use the Configure hub to manage branding, modules, and runtime settings.",
        "category_slug": "system-admin",
        "target_roles": ["ADMIN"],
        "tags": "admin,configure,sitesettings",
        "content": """
<h2>Configure hub</h2>
<p>The Configure surface groups site settings, feature flags, and module toggles in one place.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm you have admin role for the active tenant.</li>
<li>Note which domains need publish vs immediate save.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open <strong>Configure</strong> from the portal header or backend dashboard.</li>
<li>Use search to jump to a setting domain (brand, attendance, finance, etc.).</li>
<li>Save changes — some domains require a publish or cache refresh before tenants see updates.</li>
</ol>
        """,
    },
    {
        "workflow_id": "tenant-teacher-attendance",
        "slug": "teacher-mark-attendance",
        "title": "Mark daily attendance (teachers)",
        "summary": "Record present, absent, or late status for your class roster.",
        "category_slug": "student-management",
        "target_roles": ["TEACHER"],
        "tags": "teacher,attendance,class",
        "content": """
<h2>Overview</h2>
<p>Record daily attendance for your class before the school cutoff time.</p>
<h3>Pre-flight checklist</h3>
<ul>
<li>Confirm class, date, and period match your timetable.</li>
<li>Resolve roster changes (new transfers) with the office before submitting.</li>
</ul>
<h3>Steps</h3>
<ol>
<li>Open <strong>Attendance</strong> for your class and date.</li>
<li>Tap each student or use bulk actions for all present.</li>
<li>Submit before the school cutoff time (shown in the header when configured).</li>
</ol>
<p>Parents receive notifications according to your school's communication policy.</p>
        """,
    },
)

from apps.portal.workflow_kb_corpus_audit import build_audit_workflow_kb_corpus
from apps.portal.workflow_kb_corpus_editorial import (
    EDITORIAL_BY_WORKFLOW_ID,
    EDITORIAL_WORKFLOW_KB_CORPUS,
    HIGH_STAKES_WORKFLOW_IDS,
)

WORKFLOW_ID_SLUG_MAP: dict[str, str] = {
    row["workflow_id"]: row["slug"] for row in WORKFLOW_KB_CORPUS
}

_AUDIT_CORPUS = build_audit_workflow_kb_corpus(
    skip_workflow_ids=set(WORKFLOW_ID_SLUG_MAP.keys()),
)


def _merge_workflow_corpus(*layers: tuple[dict, ...]) -> tuple[dict[str, Any], ...]:
    merged: dict[str, dict[str, Any]] = {}
    for layer in layers:
        for row in layer:
            merged[row["workflow_id"]] = row
    return tuple(merged.values())


ALL_WORKFLOW_KB_CORPUS: tuple[dict[str, Any], ...] = _merge_workflow_corpus(
    WORKFLOW_KB_CORPUS,
    _AUDIT_CORPUS,
    EDITORIAL_WORKFLOW_KB_CORPUS,
)

for row in ALL_WORKFLOW_KB_CORPUS:
    WORKFLOW_ID_SLUG_MAP[row["workflow_id"]] = row["slug"]


def slug_for_workflow_id(workflow_id: str) -> str:
    return WORKFLOW_ID_SLUG_MAP.get(workflow_id, workflow_id)


TEACHER_WORKFLOW_SLUGS = tuple(
    row["slug"]
    for row in ALL_WORKFLOW_KB_CORPUS
    if "TEACHER" in row.get("target_roles", [])
)
PARENT_WORKFLOW_SLUGS = tuple(
    row["slug"]
    for row in ALL_WORKFLOW_KB_CORPUS
    if "PARENT" in row.get("target_roles", [])
)
