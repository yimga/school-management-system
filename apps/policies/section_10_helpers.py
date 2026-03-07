"""
Section 10: Platform-wide configurability by module — policy consumers.
Use these helpers so Finance, Attendance, Communication, HR, Compliance are driven by policy only.
"""
from __future__ import annotations

from typing import Any

from apps.policies.policy_registry import get_effective_policy


def get_finance_policy(school) -> dict[str, Any]:
    """10.3: Invoice timing, fee templates, discounts, scholarship, late fee rules, collection flows, write-off, payment providers."""
    policy = get_effective_policy(school) if school else {}
    return policy.get("finance") or {}


def get_attendance_policy(school) -> dict[str, Any]:
    """10.4: Statuses, lateness rules, absence escalation, homeroom/class model, who marks, parent notification timing."""
    policy = get_effective_policy(school) if school else {}
    return policy.get("attendance") or {}


def get_communication_policy(school) -> dict[str, Any]:
    """10.5: Channels, fallback order, opt-in/out, digest vs instant, message approval, segmentation, school/quiet hours."""
    policy = get_effective_policy(school) if school else {}
    return policy.get("communication") or {}


def get_hr_staff_policy(school) -> dict[str, Any]:
    """10.6: Recruitment, onboarding, certification tracking, review cycles, leave approvals, substitute workflows."""
    policy = get_effective_policy(school) if school else {}
    return policy.get("hr_staff") or {}


def get_compliance_policy(school) -> dict[str, Any]:
    """10.7: Retention, evidence packs, inspector portal, document requirements, safeguarding, regional controls."""
    policy = get_effective_policy(school) if school else {}
    return policy.get("compliance") or {}
