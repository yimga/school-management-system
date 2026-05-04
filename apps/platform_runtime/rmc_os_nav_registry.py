"""
Role-aware navigation taxonomy (documentation + future registry hooks).

Live tenant portal navigation remains driven by ``PORTAL_SIDEBAR_ITEMS`` / SiteSettings.
This module defines canonical **job cluster** names for audits and future label alignment
without changing URL targets here.

Taxonomy (UX layer — preserve existing reverses):
- founder_operator: Command Center, Schools, Growth, Marketplace, Automation, Insights,
  Trust & Security, Configuration, External Readiness
- school_admin: School Command Center, People, Classes, Attendance, Marks & Results,
  Reports, Money Center, Parent Portal, Automation, Apps, Offline Sync, Settings
- teacher: My Teaching Day, My Classes, Daily Attendance, Marks Entry, Students,
  Reports, Offline Queue, Help
- parent: Family Home, Children, Invoices & Receipts, Reports, Messages, Help
- student: My Learning, Results, Attendance, Reports, Messages
"""

from __future__ import annotations

# Maps rmc_os_shell.role_cluster -> ordered group ids (stable for analytics/tests).
NAV_JOB_CLUSTERS_BY_ROLE_CLUSTER: dict[str, tuple[str, ...]] = {
    "anonymous": (),
    "public": (),
    "founder_operator": (
        "command",
        "schools",
        "growth",
        "marketplace",
        "automation",
        "insights",
        "trust",
        "configuration",
        "readiness",
    ),
    "operator": (
        "command",
        "schools",
        "growth",
        "marketplace",
        "automation",
        "insights",
        "trust",
        "configuration",
        "readiness",
    ),
    "school_admin": (
        "school_command",
        "people",
        "classes",
        "attendance",
        "marks",
        "reports",
        "money",
        "parent_portal",
        "automation",
        "apps",
        "offline",
        "settings",
    ),
    "school_staff": (
        "school_command",
        "people",
        "classes",
        "reports",
        "settings",
    ),
    "teacher": (
        "teaching_day",
        "classes",
        "attendance",
        "marks",
        "students",
        "reports",
        "offline",
        "help",
    ),
    "parent": (
        "family",
        "children",
        "money",
        "reports",
        "messages",
        "help",
    ),
    "student": (
        "learning",
        "results",
        "attendance",
        "reports",
        "messages",
    ),
}


def job_clusters_for(role_cluster: str) -> tuple[str, ...]:
    if role_cluster in NAV_JOB_CLUSTERS_BY_ROLE_CLUSTER:
        return NAV_JOB_CLUSTERS_BY_ROLE_CLUSTER[role_cluster]
    return NAV_JOB_CLUSTERS_BY_ROLE_CLUSTER["school_staff"]
