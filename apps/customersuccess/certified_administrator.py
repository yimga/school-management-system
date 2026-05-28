"""Wave L (v3.95.0 — 2026-05-26) — Certified Administrator program registry.

Salesforce / Shopify / HubSpot all monetize a certification program: school
administrators earn credentials by completing a curriculum + passing an exam.
This gives RMC three flywheel effects:

1. **Switching cost moat** — certified admins are personally invested.
2. **Talent supply** — districts hiring RMC-certified admins prefer RMC schools.
3. **Operator-controlled lead pool** — every certified admin is a named
   contact + email + LinkedIn-shaped profile we can reach.

This module is the **track + module + exam registry**. The actual learner
state (which admin has passed which module) lives in a separate model that
this module *does not* create — it's added in Wave L+ once the curriculum
content is stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CertificationModule:
    """A single learnable unit within a track."""

    module_id: str
    title: str
    minutes_estimated: int
    objectives: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class CertificationExam:
    """The proctored exam that gates the credential."""

    exam_id: str
    title: str
    minutes_total: int
    question_count: int
    pass_threshold_pct: int


@dataclass(frozen=True)
class CertificationTrack:
    """A named credential track."""

    track_id: str
    title: str
    audience: str  # e.g. "Operator", "Tenant-Admin", "Bursar", "Teacher-Champion"
    level: str    # "Foundational" | "Professional" | "Expert"
    description: str
    modules: tuple[CertificationModule, ...]
    exam: CertificationExam
    badge_slug: str = ""
    issuer: str = "RunMyCampus"
    renewal_months: int = 24


# ---------------------------------------------------------------------------
# Registry (in-memory; populated at import time)
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, CertificationTrack] = {}


def register_track(track: CertificationTrack) -> None:
    _REGISTRY[track.track_id] = track


def list_tracks() -> tuple[CertificationTrack, ...]:
    return tuple(_REGISTRY.values())


def get_track(track_id: str) -> CertificationTrack | None:
    return _REGISTRY.get(track_id)


def tracks_for_audience(audience: str) -> tuple[CertificationTrack, ...]:
    aud = (audience or "").strip()
    return tuple(t for t in _REGISTRY.values() if t.audience == aud)


def total_modules() -> int:
    return sum(len(t.modules) for t in _REGISTRY.values())


def total_estimated_hours() -> float:
    """Sum of all module minutes across all tracks, in hours."""
    total = sum(m.minutes_estimated for t in _REGISTRY.values() for m in t.modules)
    return round(total / 60.0, 1)


def clear_registry_for_tests() -> None:
    _REGISTRY.clear()


# ---------------------------------------------------------------------------
# Seeded curriculum — 5 tracks, 27 modules total
# ---------------------------------------------------------------------------

def _seed_curriculum() -> None:
    # Track 1: RMC Tenant Admin — Foundational
    register_track(CertificationTrack(
        track_id="rmc-tenant-admin-foundational",
        title="RMC Tenant Administrator — Foundational",
        audience="Tenant-Admin",
        level="Foundational",
        description=(
            "The starting credential. Covers tenant setup, user/role "
            "management, basic configuration, and first-month operations."
        ),
        modules=(
            CertificationModule(
                module_id="ta-f-01",
                title="Tenant Setup & First-Login",
                minutes_estimated=45,
                objectives=(
                    "Provision a new tenant subdomain.",
                    "Complete Setup Studio first-login wizard.",
                    "Configure brand palette + logo + favicon.",
                ),
            ),
            CertificationModule(
                module_id="ta-f-02",
                title="User & Role Management",
                minutes_estimated=60,
                objectives=(
                    "Create users via bulk-import + entity console.",
                    "Apply RBAC roles + ReBAC scopes.",
                    "Reset MFA + recover orphaned accounts.",
                ),
                prerequisites=("ta-f-01",),
            ),
            CertificationModule(
                module_id="ta-f-03",
                title="Academic Year & Calendar Setup",
                minutes_estimated=45,
                objectives=(
                    "Configure academic years + terms + holidays.",
                    "Wire grading scales + report-card templates.",
                ),
                prerequisites=("ta-f-01",),
            ),
            CertificationModule(
                module_id="ta-f-04",
                title="Student & Guardian Enrollment",
                minutes_estimated=60,
                objectives=(
                    "Run the unified enrollment wizard.",
                    "Link guardians + emergency contacts.",
                    "Bulk import legacy student data.",
                ),
                prerequisites=("ta-f-02",),
            ),
            CertificationModule(
                module_id="ta-f-05",
                title="Communications & Announcements",
                minutes_estimated=45,
                objectives=(
                    "Compose + approve school-wide announcements.",
                    "Configure channel preferences (email/SMS/WhatsApp).",
                ),
                prerequisites=("ta-f-02",),
            ),
            CertificationModule(
                module_id="ta-f-06",
                title="Fees & Invoicing Basics",
                minutes_estimated=60,
                objectives=(
                    "Configure fee structures + waivers.",
                    "Generate term invoices + distribute via parent portal.",
                ),
                prerequisites=("ta-f-03",),
            ),
        ),
        exam=CertificationExam(
            exam_id="ta-f-exam",
            title="RMC Tenant Admin Foundational Exam",
            minutes_total=90,
            question_count=60,
            pass_threshold_pct=75,
        ),
        badge_slug="rmc-ta-foundational",
        renewal_months=24,
    ))

    # Track 2: RMC Tenant Admin — Professional
    register_track(CertificationTrack(
        track_id="rmc-tenant-admin-professional",
        title="RMC Tenant Administrator — Professional",
        audience="Tenant-Admin",
        level="Professional",
        description=(
            "Second-tier admin credential. Covers advanced workflows: "
            "approvals, integrations, analytics, marketplace, automation."
        ),
        modules=(
            CertificationModule(
                module_id="ta-p-01",
                title="Approval Workflows",
                minutes_estimated=60,
                objectives=(
                    "Configure announcement / grade / syllabus approval roles.",
                    "Set up delegation mappings + escalation paths.",
                ),
            ),
            CertificationModule(
                module_id="ta-p-02",
                title="Integrations & API Center",
                minutes_estimated=75,
                objectives=(
                    "Connect Stripe / Paystack / WhatsApp / Zoom integrations.",
                    "Generate + rotate API keys.",
                    "Configure webhook receivers.",
                ),
                prerequisites=("ta-p-01",),
            ),
            CertificationModule(
                module_id="ta-p-03",
                title="Marketplace & Extensions",
                minutes_estimated=60,
                objectives=(
                    "Install + configure marketplace packages.",
                    "Roll back a failed pack installation.",
                ),
            ),
            CertificationModule(
                module_id="ta-p-04",
                title="Analytics & Reporting",
                minutes_estimated=60,
                objectives=(
                    "Build custom dashboards + KPIs.",
                    "Schedule recurring reports.",
                ),
                prerequisites=("ta-p-01",),
            ),
            CertificationModule(
                module_id="ta-p-05",
                title="Automation & Workflows",
                minutes_estimated=75,
                objectives=(
                    "Compose multi-step automations.",
                    "Wire triggers + conditions + actions.",
                ),
                prerequisites=("ta-p-01",),
            ),
        ),
        exam=CertificationExam(
            exam_id="ta-p-exam",
            title="RMC Tenant Admin Professional Exam",
            minutes_total=120,
            question_count=80,
            pass_threshold_pct=80,
        ),
        badge_slug="rmc-ta-professional",
        renewal_months=24,
    ))

    # Track 3: RMC Bursar — Specialist
    register_track(CertificationTrack(
        track_id="rmc-bursar-specialist",
        title="RMC Bursar Specialist",
        audience="Bursar",
        level="Professional",
        description=(
            "Finance-focused credential. Covers fee structures, PSP "
            "configuration, reconciliation, compliance, and reporting."
        ),
        modules=(
            CertificationModule(
                module_id="bu-s-01",
                title="Fee Structure & Billing Models",
                minutes_estimated=60,
                objectives=(
                    "Configure per-grade fee structures.",
                    "Apply scholarships + sibling discounts.",
                ),
            ),
            CertificationModule(
                module_id="bu-s-02",
                title="PSP Configuration",
                minutes_estimated=75,
                objectives=(
                    "Connect Stripe Connect / Paystack / Flutterwave / Razorpay.",
                    "Configure mobile-money rails (MTN MoMo / Orange Money).",
                ),
                prerequisites=("bu-s-01",),
            ),
            CertificationModule(
                module_id="bu-s-03",
                title="Reconciliation & Audit",
                minutes_estimated=60,
                objectives=(
                    "Reconcile gateway settlements with internal ledger.",
                    "Resolve disputed transactions.",
                ),
                prerequisites=("bu-s-02",),
            ),
            CertificationModule(
                module_id="bu-s-04",
                title="Tax & Compliance Reporting",
                minutes_estimated=60,
                objectives=(
                    "Generate per-jurisdiction tax reports.",
                    "Handle VAT/GST/sales-tax remittance.",
                ),
            ),
        ),
        exam=CertificationExam(
            exam_id="bu-s-exam",
            title="RMC Bursar Specialist Exam",
            minutes_total=90,
            question_count=60,
            pass_threshold_pct=80,
        ),
        badge_slug="rmc-bursar-specialist",
        renewal_months=24,
    ))

    # Track 4: RMC Teacher Champion — Foundational
    register_track(CertificationTrack(
        track_id="rmc-teacher-champion-foundational",
        title="RMC Teacher Champion — Foundational",
        audience="Teacher-Champion",
        level="Foundational",
        description=(
            "Lead-teacher credential. Trains the in-school champion who "
            "supports other teachers + acts as the school's RMC liaison."
        ),
        modules=(
            CertificationModule(
                module_id="tc-f-01",
                title="Classroom Setup & Roster Management",
                minutes_estimated=45,
                objectives=(
                    "Configure class lists + seating + co-teachers.",
                    "Import student rosters.",
                ),
            ),
            CertificationModule(
                module_id="tc-f-02",
                title="Daily Operations — Attendance & Activities",
                minutes_estimated=45,
                objectives=(
                    "Mark attendance + bulk-mark patterns.",
                    "Log classroom activities + parent updates.",
                ),
                prerequisites=("tc-f-01",),
            ),
            CertificationModule(
                module_id="tc-f-03",
                title="Assignments & Grading",
                minutes_estimated=60,
                objectives=(
                    "Configure assignment categories + weights.",
                    "Enter grades + comments + run grade-book audits.",
                ),
                prerequisites=("tc-f-01",),
            ),
            CertificationModule(
                module_id="tc-f-04",
                title="Parent Communication & Reports",
                minutes_estimated=45,
                objectives=(
                    "Send individual + class-level messages.",
                    "Generate progress reports + report cards.",
                ),
                prerequisites=("tc-f-02",),
            ),
        ),
        exam=CertificationExam(
            exam_id="tc-f-exam",
            title="RMC Teacher Champion Foundational Exam",
            minutes_total=75,
            question_count=50,
            pass_threshold_pct=75,
        ),
        badge_slug="rmc-tc-foundational",
        renewal_months=24,
    ))

    # Track 5: RMC Migration Specialist — Concierge (Wave M complement)
    register_track(CertificationTrack(
        track_id="rmc-migration-specialist-concierge",
        title="RMC Migration Specialist — Concierge",
        audience="Migration-Specialist",
        level="Expert",
        description=(
            "Concierge-migration credential. Trains specialists to lead "
            "end-to-end migrations from PowerSchool / SIMS / Arbor / etc. "
            "into RMC."
        ),
        modules=(
            CertificationModule(
                module_id="ms-c-01",
                title="Pre-Migration Audit",
                minutes_estimated=90,
                objectives=(
                    "Run pre-migration data quality audits.",
                    "Identify schema mismatches + data-loss risks.",
                ),
            ),
            CertificationModule(
                module_id="ms-c-02",
                title="Source-System Adapters",
                minutes_estimated=75,
                objectives=(
                    "Configure migration adapters for top 6 source systems.",
                    "Handle CSV + SIS API + JDBC source paths.",
                ),
                prerequisites=("ms-c-01",),
            ),
            CertificationModule(
                module_id="ms-c-03",
                title="Cutover & Rollback Playbook",
                minutes_estimated=90,
                objectives=(
                    "Plan + rehearse the cutover.",
                    "Execute rollback if cutover fails.",
                ),
                prerequisites=("ms-c-02",),
            ),
            CertificationModule(
                module_id="ms-c-04",
                title="Post-Migration Validation",
                minutes_estimated=60,
                objectives=(
                    "Run integrity checks across all migrated entities.",
                    "Sign off the migration with the tenant.",
                ),
                prerequisites=("ms-c-03",),
            ),
        ),
        exam=CertificationExam(
            exam_id="ms-c-exam",
            title="RMC Migration Specialist Concierge Exam",
            minutes_total=150,
            question_count=80,
            pass_threshold_pct=85,
        ),
        badge_slug="rmc-ms-concierge",
        renewal_months=18,  # tighter renewal — source systems change fast
    ))


_seed_curriculum()


# ---------------------------------------------------------------------------
# Public summary
# ---------------------------------------------------------------------------

def summary() -> dict[str, Any]:
    """High-level summary used by operator dashboards + verifier scripts."""
    tracks = list_tracks()
    return {
        "track_count": len(tracks),
        "module_count": total_modules(),
        "exam_count": len(tracks),
        "total_estimated_hours": total_estimated_hours(),
        "by_level": {
            level: sum(1 for t in tracks if t.level == level)
            for level in ("Foundational", "Professional", "Expert")
        },
        "by_audience": {
            t.audience: 1 + sum(
                1 for o in tracks if o.audience == t.audience and o.track_id < t.track_id
            )
            for t in tracks
        },
    }
