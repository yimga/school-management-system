#!/usr/bin/env python3
"""Verify unified AI assistant wiring (Phase A batch 1393 + Phase B 1394 + Phase C 1395)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ok(path: str, needle: str) -> bool:
    p = ROOT / path
    if not p.is_file():
        return False
    return needle in p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    checks = [
        # Phase A
        ("surface-context-module", (ROOT / "apps/portal/ai_surface_context.py").is_file()),
        ("gateway-default-path", _ok("apps/portal/views_ai_gateway.py", "build_ai_surface_context")),
        ("copilot-path-prompt", _ok("apps/portal/views_ai_copilot.py", "current_path=surface.get")),
        ("command-bar-path", _ok("apps/portal/views_command_bar.py", "build_ai_surface_context")),
        ("copilot-service-live", _ok("apps/observability/ai_copilot_service.py", "enrich_manager_copilot_rail")),
        ("cockpit-enrich", _ok("apps/siteconfig/cockpit_context.py", "enrich_manager_copilot_rail")),
        ("support-hooks-triage", _ok("apps/siteconfig/support_ticket_hooks.py", "_maybe_enqueue_support_ai_triage")),
        ("gap-auto-draft", _ok("apps/portal/help_content_gaps.py", "maybe_auto_draft_from_content_gap")),
        ("portal-nudge", _ok("templates/portal_base.html", "help_proactive_nudge.html")),
        ("finance-inline", _ok("templates/finance/dashboard.html", "help_module_inline_assistant.html")),
        ("intake-ai-url", _ok("apps/migration_cloud/urls.py", "intake_ai_ask")),
        ("intake-ai-bridge", _ok("apps/migration_cloud/ai_bridge.py", "answer_intake_question")),
        ("intake-ai-partial", (ROOT / "templates/migration_cloud/partials/intake_ai_assistant.html").is_file()),
        ("a11y-spec", (ROOT / "tests/e2e/help-ai-center-a11y.spec.js").is_file()),
        ("a11y-lane2-script", (ROOT / "scripts/run_geos_ai_a11y_lane2.sh").is_file()),
        # Phase B — workflow copilot
        ("playbook-ai-module", (ROOT / "apps/portal/workflow_playbook_ai.py").is_file()),
        ("playbook-views", _ok("apps/portal/views_workflow_playbook.py", "api_onboarding_playbook_ask")),
        ("playbook-api-urls", _ok("apps/api/urls.py", "ai-onboarding-playbook")),
        ("playbook-partial", _ok("templates/partials/workflow_playbook_assistant.html", "data-rmc-workflow-playbook")),
        ("playbook-js", (ROOT / "static/js/rmc-workflow-playbook.js").is_file()),
        ("tenant-proactive", _ok("apps/portal/tenant_proactive_suggestions.py", "proactive_suggestions_for_request")),
        ("attendance-inline", _ok("templates/teacher/attendance.html", "help_module_inline_assistant.html")),
        ("offboarding-playbook-ui", _ok("templates/siteconfig/tenant_self_offboarding.html", "workflow_playbook_assistant.html")),
        ("onboarding-playbook-ui", _ok("templates/siteconfig/partials/onboarding_body.html", "workflow_playbook_assistant.html")),
        ("forum-kb-bridge", _ok("apps/portal/help_forum_kb_bridge.py", "suggested_kb_for_text")),
        ("studio-inline-prefix", _ok("apps/portal/help_proactive_inline.py", "/studio_os/")),
        # Phase C — school OS intelligence
        ("education-teacher", _ok("apps/portal/views_education_pack.py", "education_pack_teacher")),
        ("education-parent", _ok("apps/portal/views_education_pack.py", "education_pack_parent")),
        ("education-templates", (ROOT / "templates/portal/education_pack_teacher.html").is_file()),
        ("partner-doc-ui", _ok("templates/portal/partner_documentation_assistant.html", "data-rmc-partner-doc-assistant")),
        ("tenant-kb-submit", _ok("apps/portal/views_kb.py", "kb_article_submit")),
        ("mcp-scaffold", _ok("services/ai/mcp_product_server.py", "PRODUCT_MCP_TOOLS")),
        ("mcp-views", _ok("apps/portal/views_mcp_product.py", "api_mcp_list_tools")),
        ("mcp-settings", _ok("config/settings.py", "RMC_PRODUCT_MCP_ENABLED")),
        ("ai-nutrition-label", _ok("templates/partials/ai_nutrition_label.html", "data-rmc-ai-nutrition-label")),
        ("prompt-playbook", _ok("apps/siteconfig/prompt_registry.py", "workflow_playbook")),
        # Gear 2 (batch 1396)
        ("intent-router", (ROOT / "apps/portal/ai_intent_router.py").is_file()),
        ("surface-intent-wired", _ok("apps/portal/ai_surface_context.py", "surface_intent")),
        ("lesson-plan-service", (ROOT / "services/teacher_lesson_plan.py").is_file()),
        ("lesson-outline-api", _ok("apps/portal/urls.py", "ai_draft_lesson_outline")),
        ("lesson-outline-js", (ROOT / "static/js/rmc-lesson-outline-draft.js").is_file()),
        ("runmycampus-guide", _ok("apps/portal/urls.py", "runmycampus_guide")),
        ("guide-template", (ROOT / "templates/portal/runmycampus_guide.html").is_file()),
        ("cmdk-guide", _ok("apps/siteconfig/command_bar_registry.py", "portal:runmycampus_guide")),
        ("cmdk-education-teacher", _ok("apps/siteconfig/command_bar_registry.py", "education_pack_teacher")),
        ("mcp-lesson-tool", _ok("services/ai/mcp_product_server.py", "lesson_plan_outline")),
        ("mcp-guide-tool", _ok("services/ai/mcp_product_server.py", "guide_surfaces")),
        ("proactive-guide-nudge", _ok("apps/portal/tenant_proactive_suggestions.py", "runmycampus_guide")),
        ("lane2-readiness-script", (ROOT / "scripts/verify_unified_ai_lane2_readiness.py").is_file()),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\nUNIFIED_AI_ASSISTANT_FAIL ({len(failed)} checks)")
        return 1
    print("\nUNIFIED_AI_ASSISTANT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
