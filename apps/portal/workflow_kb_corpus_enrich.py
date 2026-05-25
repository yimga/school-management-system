"""
Enriched Phase 9 audit runbook content — editorial-quality structure for every workflow.

Replaces generic four-step stubs with contextual pre-flight, steps, and escalation.
"""

from __future__ import annotations

import re
from typing import Any


def _title_from_workflow_id(workflow_id: str) -> str:
    core = workflow_id.split("-", 1)[-1] if "-" in workflow_id else workflow_id
    words = re.sub(r"[-_]+", " ", core).strip()
    return words[:1].upper() + words[1:] if words else workflow_id


def _preflight_bullets(workflow_id: str, audience: str) -> list[str]:
    wid = workflow_id.lower()
    if any(k in wid for k in ("migration", "connector", "maa", "intake")):
        return [
            "Confirm Migration Authorization Agreement (MAA) is signed when prompted.",
            "Export from the SIS official UI — never use unofficial scrapers.",
            "Assign a second reviewer if your policy requires dual control on apply.",
        ]
    if any(k in wid for k in ("finance", "payroll", "payment", "billing", "invoice")):
        return [
            "Run in test mode first; verify ledger entries before go-live.",
            "Finance lead signoff recorded before disabling test gateways.",
            "Never paste gateway secrets into support tickets or KB comments.",
        ]
    if any(k in wid for k in ("compliance", "erasure", "dsar", "consent")):
        return [
            "Confirm requester identity out-of-band before approving.",
            "Check legal holds, open balances, or disputes that block action.",
            "Route to counsel when jurisdiction or retention is unclear.",
        ]
    if any(k in wid for k in ("report", "term", "publish", "promotion")):
        return [
            "Grade approval queues complete for the affected term window.",
            "Promotion preview reviewed — resolve unexpected retentions.",
            "Backup or regulatory export taken if your policy requires it.",
        ]
    if any(k in wid for k in ("onboard", "wizard", "configure", "siteconfig")):
        return [
            "Academic year and term dates confirmed with leadership.",
            "Assign an owner for each wizard section before starting.",
            "Complete dependencies in order — do not skip roster before timetables.",
        ]
    if "marketplace" in wid or "publisher" in wid:
        return [
            "Publisher account verified and scoped to the correct tenant.",
            "Webhook or API credentials stored in site settings — not email.",
            "Test in sandbox before promoting to production tenants.",
        ]
    if "observability" in wid or "incident" in wid:
        return [
            "Capture incident timestamp, tenant scope, and error rate baseline.",
            "Notify customer success when more than one production tenant is affected.",
            "Document rollback target before applying runtime changes.",
        ]
    return [
        f"Sign in with the {audience.replace('_', ' ')} role that owns this workflow.",
        "Open Help center search with this workflow name if the route moved.",
        "Watch validation banners before saving irreversible changes.",
    ]


def _step_lines(workflow_id: str, recommendation: str, audience: str) -> list[str]:
    wid = workflow_id.lower()
    title = _title_from_workflow_id(workflow_id)
    if recommendation and len(recommendation) > 40:
        base = [
            f"Review the workflow goal: {recommendation.strip()}",
            f"Navigate to the {title} surface from Configure, your role dashboard, or the manager control plane.",
            "Complete required fields; resolve validation blockers before submit.",
            "Verify the outcome in the target list or audit trail.",
            "If blocked, search Help center or open a support ticket with your active URL.",
        ]
    elif "teacher" in audience or "teacher" in wid:
        base = [
            "Open your teacher dashboard or class workspace.",
            f"Locate <strong>{title}</strong> from the module menu or quick actions.",
            "Complete the task for the correct class, term, and date window.",
            "Submit before the school cutoff when attendance or grades apply.",
            "Contact your school admin if permissions or data look wrong.",
        ]
    elif "parent" in audience or "parent" in wid:
        base = [
            "Sign in to the parent portal on your school's subdomain.",
            f"Open <strong>{title}</strong> from the dashboard or child profile.",
            "Review details carefully before confirming payments or consents.",
            "Save or submit; watch for email/SMS confirmation per school policy.",
            "Use Contact school if the action fails or data looks incorrect.",
        ]
    elif audience == "operator" or wid.startswith("operator-"):
        base = [
            "Open the manager control plane on manager.runmycampus.com.",
            f"Navigate to <strong>{title}</strong> from the sidebar or command palette (Ctrl+K).",
            "Confirm tenant scope and blast radius before mutating production data.",
            "Apply changes; monitor observability and tenant health for regressions.",
            "Record approver name when your runbook requires dual control.",
        ]
    else:
        base = [
            "Sign in as a school administrator with the correct tenant context.",
            f"Open <strong>{title}</strong> from Configure or the backend dashboard.",
            "Complete required fields; resolve validation banners before commit.",
            "Verify results in the related list view or audit log.",
            "Escalate to platform support only after school lead review.",
        ]
    if any(k in wid for k in ("migration", "connector")):
        base.insert(2, "Review quarantine rows — never bulk-apply with unresolved PK conflicts.")
    if "publish" in wid or "term" in wid:
        base.insert(3, "Confirm with academic leadership — publish is largely irreversible.")
    return base


def enriched_content_from_audit_row(row: dict[str, Any]) -> str:
    wid = (row.get("workflow_id") or "").strip()
    audience = (row.get("audience") or "school_admin").strip()
    priority = (row.get("priority") or "p2").upper()
    rec = (row.get("recommendation") or "").strip()
    title = _title_from_workflow_id(wid)
    preflight_html = "\n".join(f"<li>{b}</li>" for b in _preflight_bullets(wid, audience))
    steps_html = "\n".join(f"<li>{s}</li>" for s in _step_lines(wid, rec, audience))
    overview = rec or f"Operator and tenant runbook for <strong>{title}</strong>."
    return f"""
<h2>Overview</h2>
<p>{overview}</p>
<h3>Who this is for</h3>
<p>Audience: <strong>{audience.replace("_", " ")}</strong> · Priority: <strong>{priority}</strong></p>
<h3>Pre-flight checklist</h3>
<ul>
{preflight_html}
</ul>
<h3>Steps</h3>
<ol>
{steps_html}
</ol>
<h3>Escalation</h3>
<p>Money, migration apply, term publish, and compliance erasure flows require school-admin or operator review before override. Include workflow ID <code>{wid}</code> in support tickets — never paste student PII.</p>
    """.strip()
