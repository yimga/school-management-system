"""
GAP.15: In-code declaration of the seven answers (DECISION_ARCHITECTURE_CHECKLIST).
Key control-plane and catalog pages pass decision_architecture in context so templates
can render data attributes and satisfy the checklist.
"""

from __future__ import annotations

from typing import Dict

DECISION_ARCHITECTURE_KEYS = (
    "who_is_this_for",
    "what_question_are_they_asking",
    "what_state_are_they_in",
    "what_action_should_they_take_next",
    "what_confidence_signal_do_we_show",
    "what_happens_if_they_are_wrong",
    "what_is_the_fallback_path",
)

_PRESETS: Dict[str, Dict[str, str]] = {
    "super_dashboard": {
        "who_is_this_for": "Super / platform operator",
        "what_question_are_they_asking": "How is the platform?",
        "what_state_are_they_in": "Operational",
        "what_action_should_they_take_next": "Drill into tenant, billing, support",
        "what_confidence_signal_do_we_show": "Metrics strip, tenant list",
        "what_happens_if_they_are_wrong": "—",
        "what_is_the_fallback_path": "Support, incident dashboard",
    },
    "runtime_inspector": {
        "who_is_this_for": "Operator / super",
        "what_question_are_they_asking": "What is effective for this school?",
        "what_state_are_they_in": "Inspecting a school",
        "what_action_should_they_take_next": "Inspect another school or Back to dashboard",
        "what_confidence_signal_do_we_show": "School name, blueprint, packs, overrides shown",
        "what_happens_if_they_are_wrong": "Error message if no school / resolution failure",
        "what_is_the_fallback_path": "Back to dashboard; pick school from sample",
    },
    "runtime_truth_hub": {
        "who_is_this_for": "Platform operator / super",
        "what_question_are_they_asking": "Where do global defaults live after slimming the tenant site settings row?",
        "what_state_are_they_in": "Reviewing RuntimeDefaults.payload + slim tenant site settings row",
        "what_action_should_they_take_next": "Use platform admin playbooks or execution logs, or runtime inspector for a tenant drill-down",
        "what_confidence_signal_do_we_show": "Key counts, payload key preview, maintenance flag, playbook audit counts",
        "what_happens_if_they_are_wrong": "Empty payload or missing row — still valid for fresh envs",
        "what_is_the_fallback_path": "Studio Automation rail, workflow simulator, Phase B diff, bounded config center",
    },
    "playbook_operator_hub": {
        "who_is_this_for": "Platform operator running migration playbooks",
        "what_question_are_they_asking": "What ran, where do I manage playbooks, and what are the next safe surfaces?",
        "what_state_are_they_in": "Auditing automation playbook execution or preparing a dry-run",
        "what_action_should_they_take_next": "Open admin changelists, curated links, or workflow simulator for resolution checks",
        "what_confidence_signal_do_we_show": "Recent log rows, playbook counts, task name fingerprint",
        "what_happens_if_they_are_wrong": "Empty logs on fresh envs — expected until first execute_playbook call",
        "what_is_the_fallback_path": "Runtime truth hub, Phase B diff, Studio Automation rail, outcomes console",
    },
    "phase_b_snapshot_diff": {
        "who_is_this_for": "Platform operator / super",
        "what_question_are_they_asking": "Does materialized Phase B JSON still match live tenant site settings slices?",
        "what_state_are_they_in": "Auditing domain snapshots vs owned_payload",
        "what_action_should_they_take_next": "Re-save the tenant site settings row or use admin snapshot rows; open unified diff per domain",
        "what_confidence_signal_do_we_show": "Per-domain checksum parity and drift count",
        "what_happens_if_they_are_wrong": "Runtime merge may disagree until sync catches up",
        "what_is_the_fallback_path": "Runtime truth hub, Django admin snapshot changelist",
    },
    "policy_diff": {
        "who_is_this_for": "Operator",
        "what_question_are_they_asking": "What does this bundle change?",
        "what_state_are_they_in": "Comparing bundle",
        "what_action_should_they_take_next": "Apply to sandbox, view impact",
        "what_confidence_signal_do_we_show": "Impact preview, blueprint compatibility",
        "what_happens_if_they_are_wrong": "Bundle not found",
        "what_is_the_fallback_path": "Back to policy list",
    },
    "app_catalog": {
        "who_is_this_for": "Operator",
        "what_question_are_they_asking": "What can I roll out?",
        "what_state_are_they_in": "Selecting school + app",
        "what_action_should_they_take_next": "Install to sandbox for school",
        "what_confidence_signal_do_we_show": "Catalog stats, compatibility",
        "what_happens_if_they_are_wrong": "No school selected",
        "what_is_the_fallback_path": "Governance, sandbox inspector",
    },
}


def get_decision_architecture_for_page(page_key: str) -> Dict[str, str]:
    """Return the seven-answer dict for a known page; empty dict if unknown."""
    return dict(_PRESETS.get(page_key, {}))
