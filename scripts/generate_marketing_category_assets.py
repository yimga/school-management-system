#!/usr/bin/env python
"""Generate category-dominance marketing SVG assets (illustrative product mockups)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "static" / "images" / "marketing"


def _svg(title: str, desc: str, body: str, *, w: int = 920, h: int = 340) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="t d">
  <title id="t">{title}</title>
  <desc id="d">{desc}</desc>
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#020617"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
    <filter id="sh"><feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#000" flood-opacity="0.35"/></filter>
    <style>
      .card {{ fill: #1e293b; stroke: #475569; stroke-width: 1.2; rx: 10; filter: url(#sh); }}
      .accent {{ fill: #c2410c; }}
      .ok {{ fill: #34d399; }}
      .warn {{ fill: #f59e0b; }}
      .t {{ fill: #e2e8f0; font: 700 11px ui-sans-serif, system-ui, sans-serif; }}
      .ts {{ fill: #94a3b8; font: 600 9px ui-sans-serif, system-ui, sans-serif; }}
      .row {{ fill: #334155; rx: 3; }}
    </style>
  </defs>
  <rect width="{w}" height="{h}" fill="url(#bg)"/>
  {body}
</svg>
"""


ASSETS: dict[str, tuple[str, str, str, int, int]] = {
    "home-unified-school-journey.svg": (
        "Unified school journey on RunMyCampus",
        "Illustrative flow from inquiry through governance on one operating system.",
        """<text class="t" x="460" y="28" text-anchor="middle" font-size="13">One learner journey — connected surfaces</text>
  <g transform="translate(40,56)">
    <rect class="card" x="0" y="0" width="100" height="44"/><text class="t" x="50" y="28" text-anchor="middle">Inquiry</text>
    <path stroke="#64748b" stroke-width="2" d="M104 22 H120"/><polygon fill="#64748b" points="120,18 128,22 120,26"/>
    <rect class="card" x="132" y="0" width="110" height="44"/><text class="t" x="187" y="28" text-anchor="middle">Admission</text>
    <path stroke="#64748b" stroke-width="2" d="M246 22 H262"/><polygon fill="#64748b" points="262,18 270,22 262,26"/>
    <rect class="card" x="274" y="0" width="120" height="44"/><text class="t" x="334" y="28" text-anchor="middle">Enrollment</text>
    <path stroke="#64748b" stroke-width="2" d="M398 22 H414"/><polygon fill="#64748b" points="414,18 422,22 414,26"/>
    <rect class="card" x="426" y="0" width="110" height="44"/><text class="t" x="481" y="28" text-anchor="middle">Attendance</text>
    <path stroke="#64748b" stroke-width="2" d="M540 22 H556"/><polygon fill="#64748b" points="556,18 564,22 556,26"/>
    <rect class="card" x="568" y="0" width="80" height="44"/><text class="t" x="608" y="28" text-anchor="middle">Fees</text>
    <path stroke="#64748b" stroke-width="2" d="M652 22 H668"/><polygon fill="#64748b" points="668,18 676,22 668,26"/>
    <rect class="card" x="680" y="0" width="100" height="44"/><text class="t" x="730" y="28" text-anchor="middle">Assessment</text>
    <path stroke="#64748b" stroke-width="2" d="M784 22 H800"/><polygon fill="#64748b" points="800,18 808,22 800,26"/>
    <rect class="card" x="812" y="0" width="88" height="44"/><text class="t" x="856" y="28" text-anchor="middle">Reports</text>
  </g>
  <g transform="translate(80,130)">
    <rect class="card" x="0" y="0" width="760" height="180"/>
    <text class="t" x="24" y="32">Parent portal · Finance · Leadership analytics · Governance</text>
    <rect class="row" x="24" y="52" width="220" height="10"/><rect class="row" x="24" y="72" width="180" height="10"/>
    <rect class="row" x="280" y="52" width="200" height="10"/><rect class="ok" x="280" y="72" width="120" height="10" rx="3"/>
    <rect class="row" x="520" y="52" width="210" height="10"/><rect class="warn" x="520" y="72" width="90" height="10" rx="3"/>
    <text class="ts" x="24" y="160">Illustrative product composite — not customer-specific data</text>
  </g>""",
        920,
        340,
    ),
    "home-six-operating-surfaces.svg": (
        "Six operating surfaces of RunMyCampus",
        "Illustrative grid of command center, teacher, parent, finance, publishing, and analytics surfaces.",
        """<text class="t" x="460" y="28" text-anchor="middle" font-size="13">Six operating surfaces — one education OS</text>
  <g transform="translate(24,48)">
    <rect class="card" x="0" y="0" width="280" height="120"/><text class="t" x="16" y="28">School command center</text><rect class="row" x="16" y="44" width="200" height="8"/><rect class="accent" x="16" y="62" width="140" height="8" rx="3"/>
    <rect class="card" x="296" y="0" width="280" height="120"/><text class="t" x="312" y="28">Teacher workspace</text><rect class="row" x="312" y="44" width="200" height="8"/><rect class="ok" x="312" y="62" width="120" height="8" rx="3"/>
    <rect class="card" x="592" y="0" width="280" height="120"/><text class="t" x="608" y="28">Parent mobile portal</text><rect class="row" x="608" y="44" width="200" height="8"/><rect class="row" x="608" y="62" width="160" height="8"/>
    <rect class="card" x="0" y="136" width="280" height="120"/><text class="t" x="16" y="164">Finance cockpit</text><rect class="row" x="16" y="180" width="200" height="8"/><rect class="warn" x="16" y="198" width="100" height="8" rx="3"/>
    <rect class="card" x="296" y="136" width="280" height="120"/><text class="t" x="312" y="164">Academic publishing studio</text><rect class="row" x="312" y="180" width="200" height="8"/><rect class="row" x="312" y="198" width="180" height="8"/>
    <rect class="card" x="592" y="136" width="280" height="120"/><text class="t" x="608" y="164">Analytics &amp; governance</text><rect class="row" x="608" y="180" width="200" height="8"/><rect class="ok" x="608" y="198" width="130" height="8" rx="3"/>
  </g>""",
        920,
        300,
    ),
    "platform-sis-record-spine.svg": (
        "Student record spine",
        "Illustrative learner profile timeline with guardians, enrollment, and related workflows.",
        """<text class="t" x="460" y="28" text-anchor="middle">Learner record spine — completeness &amp; status</text>
  <rect class="card" x="40" y="52" width="280" height="250"/><text class="t" x="56" y="78">Profile</text><rect class="ok" x="56" y="92" width="120" height="12" rx="4"/><text class="ts" x="56" y="120">Enrollment: active</text>
  <rect class="card" x="340" y="52" width="540" height="250"/><text class="t" x="356" y="78">Linked workflows</text>
  <rect class="row" x="356" y="100" width="480" height="10"/><rect class="row" x="356" y="120" width="420" height="10"/><rect class="row" x="356" y="140" width="460" height="10"/>
  <text class="ts" x="356" y="280">Documents · attendance · fees · grades · notes</text>""",
        920,
        340,
    ),
    "platform-attendance-daily-register.svg": (
        "Daily attendance register",
        "Illustrative class roll with late patterns and parent notification.",
        """<text class="t" x="460" y="28" text-anchor="middle">Daily rhythm register</text>
  <rect class="card" x="40" y="48" width="840" height="260"/>
  <text class="t" x="60" y="82">Class 7B · Tuesday</text>
  <rect class="ok" x="60" y="100" width="24" height="24" rx="4"/><rect class="ok" x="92" y="100" width="24" height="24" rx="4"/><rect class="warn" x="124" y="100" width="24" height="24" rx="4"/>
  <rect class="row" x="60" y="140" width="760" height="10"/><rect class="row" x="60" y="160" width="720" height="10"/>
  <text class="ts" x="60" y="280">Late cluster flagged · parent notify queued</text>""",
        920,
        340,
    ),
    "platform-grading-publishing-studio.svg": (
        "Academic publishing studio",
        "Illustrative gradebook, comments, and report card publishing workflow.",
        """<text class="t" x="460" y="28" text-anchor="middle">Academic publishing studio</text>
  <rect class="card" x="40" y="52" width="400" height="250"/><text class="t" x="56" y="78">Gradebook</text><rect class="row" x="56" y="100" width="320" height="10"/><rect class="accent" x="56" y="120" width="200" height="10" rx="3"/>
  <rect class="card" x="460" y="52" width="420" height="250"/><text class="t" x="476" y="78">Publishing status</text><rect class="ok" x="476" y="100" width="180" height="12" rx="4"/><text class="ts" x="476" y="140">Approved · parent-visible</text>""",
        920,
        340,
    ),
    "platform-communications-orchestration.svg": (
        "Communications orchestration",
        "Illustrative audience targeting, composer, and delivery status.",
        """<text class="t" x="460" y="28" text-anchor="middle">Message orchestration center</text>
  <rect class="card" x="40" y="52" width="360" height="250"/><text class="t" x="56" y="78">Composer</text><rect class="row" x="56" y="100" width="300" height="60" rx="6"/>
  <rect class="card" x="420" y="52" width="460" height="250"/><text class="t" x="436" y="78">Delivery</text><text class="ts" x="436" y="110">Sent 1,240 · Delivered 1,198 · Read 892</text><rect class="ok" x="436" y="130" width="300" height="12" rx="4"/>""",
        920,
        340,
    ),
    "platform-workflows-automation-timeline.svg": (
        "Workflow automation timeline",
        "Illustrative triggers, approvals, tasks, and audit trail.",
        """<text class="t" x="460" y="28" text-anchor="middle">Automation timeline</text>
  <line x1="80" y1="170" x2="840" y2="170" stroke="#475569" stroke-width="3"/>
  <circle cx="120" cy="170" r="14" class="accent"/><circle cx="320" cy="170" r="14" fill="#34d399"/><circle cx="520" cy="170" r="14" class="warn"/><circle cx="720" cy="170" r="14" fill="#64748b"/>
  <text class="t" x="120" y="210" text-anchor="middle">Trigger</text><text class="t" x="320" y="210" text-anchor="middle">Approve</text><text class="t" x="520" y="210" text-anchor="middle">Task</text><text class="t" x="720" y="210" text-anchor="middle">Audit</text>""",
        920,
        340,
    ),
    "platform-offline-sync-console.svg": (
        "Offline sync console",
        "Illustrative offline capture, sync queue, and conflict review.",
        """<text class="t" x="460" y="28" text-anchor="middle">Edge-native resilience console</text>
  <rect class="card" x="40" y="52" width="400" height="250"/><text class="t" x="56" y="78">Queued events</text><rect class="warn" x="56" y="100" width="320" height="12" rx="3"/><rect class="row" x="56" y="120" width="280" height="10"/>
  <rect class="card" x="460" y="52" width="420" height="250"/><text class="t" x="476" y="78">Sync status</text><rect class="ok" x="476" y="100" width="200" height="12" rx="4"/><text class="ts" x="476" y="140">Last sync: 2m ago · 0 conflicts</text>""",
        920,
        340,
    ),
    "platform-student-self-service.svg": (
        "Student self-service hub",
        "Illustrative timetable, assignments, results, and announcements.",
        """<text class="t" x="460" y="28" text-anchor="middle">Student self-service hub</text>
  <rect class="card" x="280" y="40" width="360" height="280" rx="16"/><text class="t" x="300" y="72">Today</text><rect class="row" x="300" y="90" width="300" height="10"/><rect class="row" x="300" y="110" width="260" height="10"/><rect class="accent" x="300" y="140" width="200" height="10" rx="3"/>""",
        920,
        340,
    ),
    "platform-analytics-leadership-dashboard.svg": (
        "Leadership analytics dashboard",
        "Illustrative executive dashboard with enrollment, attendance, and fee signals.",
        """<text class="t" x="460" y="28" text-anchor="middle">Leadership intelligence center</text>
  <rect class="card" x="40" y="52" width="260" height="100"/><rect class="card" x="320" y="52" width="260" height="100"/><rect class="card" x="600" y="52" width="280" height="100"/>
  <rect class="card" x="40" y="170" width="840" height="130"/><rect class="accent" x="60" y="200" width="500" height="60" rx="6" opacity="0.5"/>""",
        920,
        340,
    ),
    "platform-security-governance-center.svg": (
        "Security governance center",
        "Illustrative permission matrix, audit timeline, and access controls.",
        """<text class="t" x="460" y="28" text-anchor="middle">Governance control room</text>
  <rect class="card" x="40" y="52" width="420" height="250"/><text class="t" x="56" y="78">Role matrix</text><rect class="row" x="56" y="100" width="360" height="10"/><rect class="row" x="56" y="120" width="360" height="10"/>
  <rect class="card" x="480" y="52" width="400" height="250"/><text class="t" x="496" y="78">Audit stream</text><rect class="ok" x="496" y="100" width="320" height="10" rx="3"/>""",
        920,
        340,
    ),
    "solution-private-growth-engine.svg": (
        "Private school growth engine",
        "Illustrative enrollment-to-parent-trust flywheel.",
        """<text class="t" x="460" y="28" text-anchor="middle">Private school growth flywheel</text>
  <circle cx="460" cy="180" r="100" fill="none" stroke="#c2410c" stroke-width="2" opacity="0.6"/>
  <text class="t" x="460" y="120" text-anchor="middle">Inquiry</text><text class="t" x="580" y="180" text-anchor="middle">Fees</text><text class="t" x="460" y="250" text-anchor="middle">Trust</text><text class="t" x="340" y="180" text-anchor="middle">Reports</text>""",
        920,
        340,
    ),
    "solution-international-global-model.svg": (
        "International global operating model",
        "Illustrative multi-currency, calendars, and localization readiness.",
        """<text class="t" x="460" y="28" text-anchor="middle">Global operating model</text>
  <rect class="card" x="40" y="60" width="260" height="220"/><text class="t" x="56" y="88">Currencies</text><text class="ts" x="56" y="120">USD · EUR · XAF · GBP</text>
  <rect class="card" x="320" y="60" width="260" height="220"/><text class="t" x="336" y="88">Calendars</text>
  <rect class="card" x="600" y="60" width="280" height="220"/><text class="t" x="616" y="88">Parent regions</text>""",
        920,
        340,
    ),
    "solution-k12-lifecycle.svg": (
        "K-12 student lifecycle",
        "Illustrative journey from admission to graduation.",
        """<text class="t" x="460" y="28" text-anchor="middle">Full K–12 lifecycle</text>
  <rect class="card" x="60" y="80" width="800" height="200"/><line x1="100" y1="180" x2="820" y2="180" stroke="#c2410c" stroke-width="3"/>
  <text class="t" x="120" y="160" text-anchor="middle">Admit</text><text class="t" x="300" y="160" text-anchor="middle">Learn</text><text class="t" x="500" y="160" text-anchor="middle">Assess</text><text class="t" x="700" y="160" text-anchor="middle">Graduate</text>""",
        920,
        340,
    ),
    "solution-multi-campus-command-center.svg": (
        "Multi-campus command center",
        "Illustrative central office with campus rollups.",
        """<text class="t" x="460" y="28" text-anchor="middle">Network command center</text>
  <rect class="card" x="40" y="52" width="840" height="250"/><text class="t" x="56" y="78">Campus rollups</text>
  <rect class="row" x="56" y="100" width="200" height="40"/><rect class="row" x="280" y="100" width="200" height="40"/><rect class="row" x="504" y="100" width="200" height="40"/>""",
        920,
        340,
    ),
    "solution-faith-community-hub.svg": (
        "Faith-based community operations",
        "Illustrative family communication, events, and fee clarity.",
        """<text class="t" x="460" y="28" text-anchor="middle">Community operations hub</text>
  <rect class="card" x="40" y="52" width="400" height="250"/><text class="t" x="56" y="78">Family comms</text><rect class="row" x="56" y="100" width="320" height="10"/>
  <rect class="card" x="460" y="52" width="420" height="250"/><text class="t" x="476" y="78">Events &amp; care</text><rect class="ok" x="476" y="100" width="280" height="12" rx="4"/>""",
        920,
        340,
    ),
    "solution-growing-network-playbook.svg": (
        "Growing school network playbook",
        "Illustrative launch checklist and rollout timeline.",
        """<text class="t" x="460" y="28" text-anchor="middle">Repeatable launch playbook</text>
  <rect class="card" x="40" y="52" width="840" height="250"/><text class="t" x="56" y="78">Launch readiness</text>
  <rect class="ok" x="56" y="100" width="240" height="12" rx="4"/><rect class="warn" x="56" y="120" width="200" height="12" rx="4"/><rect class="row" x="56" y="140" width="300" height="12" rx="4"/>""",
        920,
        340,
    ),
    "platform-admissions-readiness-board.svg": (
        "Admissions readiness board",
        "Illustrative pipeline board with applicant cards and document readiness.",
        """<text class="t" x="460" y="28" text-anchor="middle">Enrollment command board</text>
  <rect class="card" x="40" y="52" width="260" height="250"/><rect class="card" x="320" y="52" width="260" height="250"/><rect class="card" x="600" y="52" width="280" height="250"/>
  <text class="ts" x="56" y="280">Applicant cards · doc readiness · decisions due</text>""",
        920,
        340,
    ),
    "platform-fees-collection-cockpit.svg": (
        "Fees collection cockpit",
        "Illustrative collection summary, invoices, and arrears.",
        """<text class="t" x="460" y="28" text-anchor="middle">Finance control room</text>
  <rect class="card" x="40" y="52" width="840" height="250"/><text class="t" x="56" y="78">Collected vs outstanding</text><rect class="ok" x="56" y="100" width="400" height="20" rx="4"/><rect class="warn" x="56" y="130" width="120" height="20" rx="4"/>""",
        920,
        340,
    ),
    "platform-parent-day-in-life.svg": (
        "Parent day in life",
        "Illustrative mobile view with attendance, fees, and messages.",
        """<text class="t" x="460" y="28" text-anchor="middle">Family mobile command center</text>
  <rect class="card" x="300" y="40" width="320" height="280" rx="20"/><text class="t" x="320" y="72">Today for Ada</text><rect class="row" x="320" y="90" width="260" height="36" rx="8"/>""",
        520,
        420,
    ),
    "platform-teacher-classroom-desk.svg": (
        "Teacher classroom desk",
        "Illustrative daily schedule, roll call, and marks.",
        """<text class="t" x="460" y="28" text-anchor="middle">Classroom operating desk</text>
  <rect class="card" x="40" y="52" width="840" height="250"/><text class="t" x="56" y="78">Period 3 · Science</text><rect class="row" x="56" y="100" width="760" height="10"/><rect class="accent" x="56" y="120" width="200" height="10" rx="3"/>""",
        920,
        340,
    ),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (title, desc, body, w, h) in ASSETS.items():
        path = OUT / name
        path.write_text(_svg(title, desc, body, w=w, h=h), encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")
    # Alias filenames used in templates
    aliases = {
        "platform-analytics-leadership-dashboard.svg": "platform-analytics-leadership.svg",
        "platform-security-governance-center.svg": "platform-security-governance.svg",
        "platform-fees-collection-cockpit.svg": "platform-fees-payments-dashboard.svg",
    }
    for src, dest in aliases.items():
        if (OUT / src).exists() and dest != src:
            text = (OUT / src).read_text(encoding="utf-8")
            (OUT / dest).write_text(text, encoding="utf-8")
            print(f"aliased {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
