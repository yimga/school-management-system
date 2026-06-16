"""
Unified assistant registry for governed, local-first AI entry points.

Maps assistant keys to permissions and prompt/routing hints. UIs resolve ``entry_url_names``
via Django ``reverse`` when present.
"""

from __future__ import annotations

from typing import Any

_ASSISTANTS: tuple[dict[str, Any], ...] = (
    {
        "assistant_key": "config_copilot",
        "label": "Configuration copilot",
        "hint": "Tenant configuration changes, brand cascade, feature flags. Safe to paste settings JSON.",
        "domain": "siteconfig",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-runtime-config-explain",
        "entry_url_names": ("siteconfig:console_domains_hub",),
    },
    {
        "assistant_key": "workflow_builder_assistant",
        "label": "Workflow builder assistant",
        "hint": "Draft automations, triggers, and conditions. References Studio OS automation surface.",
        "domain": "automation",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-studio-os-assistant",
        "studio_mode": "automation",
        "entry_url_names": ("studio_os:automation",),
    },
    {
        "assistant_key": "report_comment_assistant",
        "label": "Report comment assistant",
        "hint": "Drafts narrative report-card comments. Operator must review every draft before send.",
        "domain": "reports",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-interop-assistant",
        "entry_url_names": ("siteconfig:scheduled_reports_delivery_hub",),
    },
    {
        "assistant_key": "northstar_operator_drafts",
        "label": "North Star AI drafts (scheduled reports hub & bulk letters)",
        "hint": "Operator drafts for scheduled-report cover notes and bulk-letter copy.",
        "domain": "reports",
        "required_permission": "settings.manage",
        "enabled_by_default": False,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-interop-assistant",
        "entry_url_names": (
            "siteconfig:scheduled_reports_delivery_hub",
            "siteconfig:bulk_letters",
        ),
    },
    {
        "assistant_key": "onboarding_assistant",
        "label": "Onboarding assistant",
        "hint": "Step-by-step setup help for first-time tenants. Safe to paste setup snapshots.",
        "domain": "onboarding",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-setup-assistant",
        "entry_url_names": ("siteconfig:onboarding", "studio_os:launch"),
    },
    {
        "assistant_key": "support_assistant",
        "label": "Support assistant",
        "hint": "Customer-success copilot. Drafts replies grounded in tenant config + KB articles.",
        "domain": "support",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-interop-assistant",
        "entry_url_names": ("siteconfig:support_copilot",),
    },
    {
        "assistant_key": "first_line_support",
        "label": "First-line support (⌘K engine room)",
        "hint": "Zero-fluff how-to steps from KB + live topology. Escalates when docs are missing.",
        "domain": "support",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "first_line_support",
        "api_url_name": "api:ai-support-assistant",
        "entry_url_names": ("feedback:help_center", "siteconfig:ai_center"),
    },
    {
        "assistant_key": "smart_settings",
        "label": "Smart settings assistant",
        "hint": "Natural-language guidance for SiteSettings, feature flags, and theme tokens.",
        "domain": "configuration",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "first_line_support",
        "api_url_name": "api:ai-smart-settings",
        "entry_url_names": ("siteconfig:onboarding", "siteconfig:ai_center"),
    },
    {
        "assistant_key": "import_resolver",
        "label": "Import error resolver",
        "hint": "Maps CSV validation errors to fix steps and import review paths.",
        "domain": "data",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-import-error-resolver",
        "entry_url_names": ("siteconfig:ai_center",),
    },
    {
        "assistant_key": "report_generator",
        "label": "Custom report generator",
        "hint": "Permission-aware report library recommendations with structured output.",
        "domain": "analytics",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "report_library",
        "api_url_name": "api:ai-guardrail-report",
        "entry_url_names": ("siteconfig:ai_center",),
    },
    {
        "assistant_key": "guided_tour",
        "label": "Guided tour planner",
        "hint": "Step-by-step onboarding tour from topology + setup assistant.",
        "domain": "onboarding",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "setup_assistant",
        "api_url_name": "api:ai-guided-tour",
        "entry_url_names": ("siteconfig:onboarding", "siteconfig:ai_center"),
    },
    {
        "assistant_key": "data_quality_assistant",
        "label": "Data quality assistant",
        "hint": "Diagnoses tenant-data integrity gaps (orphan rows, missing FKs, validation drift).",
        "domain": "data_quality",
        "required_permission": "settings.manage",
        "enabled_by_default": False,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-interop-assistant",
        "entry_url_names": ("siteconfig:metadata_operator_hub",),
    },
    {
        "assistant_key": "trust_compliance_assistant",
        "label": "Trust & compliance assistant",
        "hint": "High-level trust-center and audit posture. Not legal advice.",
        "domain": "compliance",
        "required_permission": "settings.manage",
        "enabled_by_default": False,
        "provider_policy": "local_only_rules",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-trust-compliance-assistant",
        "entry_url_names": ("siteconfig:config_mutation_audit_evidence",),
    },
    {
        "assistant_key": "studio_os_assistant",
        "label": "Studio OS assistant",
        "hint": "Cross-mode Studio OS guidance (experience, automation, output, launch, control).",
        "domain": "studio_os",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-studio-os-assistant",
        "entry_url_names": ("studio_os:experience",),
    },
    {
        "assistant_key": "observability_assistant",
        "label": "Observability & SLO assistant",
        "hint": "For operators: health endpoints, SLO dashboard, and runbook-style hints. No live secrets.",
        "domain": "observability",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-observability-assistant",
        "entry_url_names": ("super:ai_gateway_console",),
    },
    {
        "assistant_key": "billing_usage_explain",
        "label": "Billing & usage explainer",
        "hint": "SKUs, entitlements, and usage concepts. Do not paste payment card or bank data.",
        "domain": "billing",
        "required_permission": "settings.manage",
        "enabled_by_default": True,
        "provider_policy": "ollama_first_rules_fallback",
        "prompt_key": "general_chat",
        "api_url_name": "api:ai-billing-usage-explain",
        "entry_url_names": ("siteconfig:billing_plan_readonly",),
    },
)


def get_assistant(assistant_key: str) -> dict[str, Any] | None:
    for row in _ASSISTANTS:
        if row["assistant_key"] == assistant_key:
            return row
    return None


def iter_assistants() -> tuple[dict[str, Any], ...]:
    return _ASSISTANTS


def assistant_keys() -> frozenset[str]:
    return frozenset(a["assistant_key"] for a in _ASSISTANTS)


def user_may_use_assistant(user, required_permission: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        if user_has_control_plane_access(user):
            return True
    except ImportError:
        pass
    return user.has_feature_permission(required_permission)
