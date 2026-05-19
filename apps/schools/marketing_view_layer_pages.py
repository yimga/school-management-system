"""
Dedicated marketing page definitions for the advisory-board view-layer map.

Merged into MARKETING_PAGE_DEFINITIONS at import time. Each slug aligns with
``marketing_personality.py`` so HTTP routes render distinct personalities + viz.
"""

from __future__ import annotations

from apps.schools.marketing_personality import resolve_marketing_personality

_VIEW_LAYER_COPY: dict[str, tuple[str, str, list[dict[str, str]]]] = {
    "careers": (
        "Build campus software with us.",
        "Interactive engineering stack selector, open roles, and how we ship tenant-safe features.",
        [
            {"title": "Stack", "body": "Django, TypeScript, and mechanical verifiers — no shadow IT in prod."},
            {"title": "Ownership", "body": "Small teams own RUN · TEACH · PAY · COMMUNICATE surfaces end-to-end."},
            {"title": "Remote-friendly", "body": "Async-first with quarterly campus immersion weeks."},
        ],
    ),
    "brand-assets": (
        "Brand system for partners and press.",
        "Download SVG marks, copy hex tokens, and preview co-brand lockups — pixel-perfect, not placeholder ZIPs.",
        [
            {"title": "Logo suite", "body": "Primary, reversed, and favicon variants with clear-space rules."},
            {"title": "Color tokens", "body": "Semantic marketing palette mapped to CSS variables for co-brand sites."},
            {"title": "Typography", "body": "Source Serif 4 pairing guidance for editorial surfaces."},
        ],
    ),
    "hardware-store": (
        "Campus hardware that pairs with your OS.",
        "Rugged scanners, receipt printers, and ID card kits with spec tables and deployment notes per region.",
        [
            {"title": "Curated catalog", "body": "SKUs vetted for attendance, canteen, and front-office workflows."},
            {"title": "Spec transparency", "body": "Power, connectivity, and warranty columns — no mystery bundles."},
            {"title": "Fulfillment honesty", "body": "Lead times and RMA paths vary by corridor; checkout routes to your operator."},
        ],
    ),
    "training-academies": (
        "Operator academies with measurable progress.",
        "Video walkthroughs, certification paths, and role-based checkpoints for admins, teachers, and finance.",
        [
            {"title": "Learning paths", "body": "Modular courses aligned to RUN · TEACH · PAY · COMMUNICATE matrices."},
            {"title": "Progress telemetry", "body": "Completion bars reflect real module states — not decorative percentages."},
            {"title": "Office hours", "body": "Book implementation office hours from any academy module."},
        ],
    ),
    "teacher-communities": (
        "Professional communities without algorithmic noise.",
        "Thread lists, tag filters, and school-scoped channels that respect tenant boundaries.",
        [
            {"title": "Scoped discussions", "body": "Communities inherit tenant isolation — no cross-school leakage."},
            {"title": "Moderation tools", "body": "Admins pin, archive, and export threads for policy review."},
            {"title": "Resource attachments", "body": "Link lesson assets and KB articles inline."},
        ],
    ),
    "lesson-planning": (
        "Template canvas for rapid outlining.",
        "Drag-friendly blocks, standards tags, and dependency hints for multi-period units.",
        [
            {"title": "Block library", "body": "Objectives, materials, assessments, and differentiation columns."},
            {"title": "Dependency tree", "body": "Visualize prerequisite lessons before publishing to teachers."},
            {"title": "Publish path", "body": "Push approved templates to teacher workspaces in one action."},
        ],
    ),
    "infrastructure-map": (
        "Regional topology you can audit.",
        "Interactive map of API gateways, worker regions, and failover pairs — illustrative, refreshed from status feeds.",
        [
            {"title": "Edge gateways", "body": "Ingress nodes with latency vectors per geography."},
            {"title": "Worker regions", "body": "Celery and async workers pinned to data-residency choices."},
            {"title": "Failover pairs", "body": "Warm standby paths documented for operator drills."},
        ],
    ),
    "security-matrix": (
        "Role × resource access grid.",
        "Dense matrix mapping platform roles to data domains with export for procurement reviewers.",
        [
            {"title": "RBAC source", "body": "Generated from live permission registry — not a static PDF."},
            {"title": "Field-level notes", "body": "Sensitive tiers flagged for finance and student health data."},
            {"title": "Export", "body": "CSV and JSON artifacts for security questionnaires."},
        ],
    ),
    "solutions-higher-ed": (
        "Research university operating model.",
        "Provost-ready narratives for multi-college governance, research compliance, and cross-campus analytics.",
        [
            {"title": "Schools & colleges", "body": "Delegate autonomy with network-level policy inheritance."},
            {"title": "Research data", "body": "Separate sensitivity tiers for grants and human-subjects workflows."},
            {"title": "Accreditation packs", "body": "Evidence exports aligned to regional accreditors."},
        ],
    ),
    "solutions-k12-districts": (
        "District oversight without shadow systems.",
        "Board-ready compliance, feeder patterns, and per-campus isolation with group rollups.",
        [
            {"title": "Campus isolation", "body": "Each school is a tenant; district sees permitted aggregates only."},
            {"title": "Policy inheritance", "body": "Push grading scales, calendars, and finance rules from the center."},
            {"title": "Board packets", "body": "Procurement-friendly exports for public meetings."},
        ],
    ),
    "legal-ferpa": (
        "FERPA-aligned education records.",
        "Access, disclosure, and audit mechanics for student records — written for counsel and IT together.",
        [
            {"title": "Directory information", "body": "Configurable opt-outs and disclosure logging."},
            {"title": "School official access", "body": "Legitimate educational interest enforced in RBAC."},
            {"title": "Parent rights", "body": "Portal paths for review and amendment requests."},
        ],
    ),
    "legal-coppa": (
        "Child safety and parental consent.",
        "Age gates, consent capture, and minimized profiles for younger learners.",
        [
            {"title": "Consent boundaries", "body": "Parent authorization before non-essential processing."},
            {"title": "Data minimization", "body": "Fields required for instruction only — no surplus profiling."},
            {"title": "Vendor diligence", "body": "Marketplace apps inherit child-safety review states."},
        ],
    ),
    "legal-gdpr": (
        "GDPR and cross-border transfers.",
        "Lawful basis registry, DSAR workflow, and erasure attestations.",
        [
            {"title": "DSAR runbook", "body": "30-day SLA with redaction and operator attestation."},
            {"title": "Transfer tools", "body": "SCCs and DPA templates linked from procurement packets."},
            {"title": "Erasure", "body": "Right-to-be-forgotten paths with audit trail."},
        ],
    ),
    "legal-wcag": (
        "Accessibility conformance matrix.",
        "WCAG 2.2 criteria mapped to product surfaces with remediation status.",
        [
            {"title": "Criteria grid", "body": "A/AA coverage per shell: marketing, portal, control plane."},
            {"title": "Assistive tech", "body": "Keyboard, screen reader, and contrast gates in CI."},
            {"title": "VPAT path", "body": "Request VPAT exports via procurement checklist."},
        ],
    ),
    "legal-terms": (
        "Terms of service.",
        "Side-anchored navigation across acceptance, usage, and limitation sections.",
        [
            {"title": "Acceptance", "body": "Contract formation for schools and authorized users."},
            {"title": "Acceptable use", "body": "Prohibited conduct and security responsibilities."},
            {"title": "Liability", "body": "Limitations described in plain language with counsel review dates."},
        ],
    ),
    "legal-cookie": (
        "Cookie and storage matrix.",
        "Tracker categories with purpose, retention, and opt-out mechanics.",
        [
            {"title": "Strictly necessary", "body": "Session, CSRF, and tenant routing — no consent required."},
            {"title": "Analytics", "body": "Optional telemetry with regional defaults."},
            {"title": "Preferences", "body": "Theme and density stored with explicit consent where required."},
        ],
    ),
}


def _build_page(slug: str) -> dict:
    personality = resolve_marketing_personality(slug)
    headline, subheadline, segments = _VIEW_LAYER_COPY[slug]
    label = personality["label"]
    return {
        "label": label,
        "seo_title": f"{label} | RunMyCampus",
        "seo_description": subheadline[:155],
        "headline": headline,
        "subheadline": subheadline,
        "schema_type": "WebPage",
        "segments": segments,
    }


VIEW_LAYER_MARKETING_PAGE_SLUGS: tuple[str, ...] = tuple(_VIEW_LAYER_COPY.keys())

VIEW_LAYER_MARKETING_PAGE_DEFINITIONS: dict[str, dict] = {
    slug: _build_page(slug) for slug in VIEW_LAYER_MARKETING_PAGE_SLUGS
}
