#!/usr/bin/env python3
"""
Gate: first-line support engine room + universal command bar completeness.

Run: python scripts/verify_ai_engine_room.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = (
    "services/ai_center/__init__.py",
    "services/ai_center/query_service.py",
    "services/ai_center/indexing.py",
    "services/ai_center/ollama_client.py",
    "services/ai_center/kb_generator.py",
    "services/ai_center/friction_analysis.py",
    "services/ai_center/contextual_insights.py",
    "services/ai_center/audit.py",
    "ai/Modelfile",
    "apps/apicenter/views_ai_center_super.py",
    "apps/apicenter/ai_center_urls.py",
    "services/ai/__init__.py",
    "services/ai/gateway.py",
    "services/ai/prompts.py",
    "services/ai/reflection.py",
    "services/ai/tenant_isolation.py",
    "services/ai/token_optimizer.py",
    "services/ai/knowledge.py",
    "services/ai/lifecycle.py",
    "services/ai/platform_context.py",
    "services/ai/topology_map.py",
    "services/ai/command_bar.py",
    "services/ai/product_assistants.py",
    "apps/portal/views_command_bar.py",
    "apps/portal/views_ai_gateway.py",
    "apps/portal/views_ai_product.py",
    "apps/siteconfig/management/commands/engine_room_sync_ollama.py",
    "static/js/rmc-command-palette.js",
    "static/js/rmc-page-context-help.js",
    "static/js/rmc_ai_guided_assistant.js",
    "templates/components/rmc_command_palette.html",
    "src/components/shared/navigation/CommandBar.tsx",
    "src/components/shared/navigation/CommandBar.test.tsx",
    "src/components/shared/navigation/commandBarLogic.ts",
    "services/ai/tests/test_aggressive_engine.py",
    "services/ai/tests/test_multitenant_isolation.py",
    "services/ai/tests/test_prompt_completeness.py",
    "services/ai/tests/test_product_assistants.py",
    "apps/portal/tests/test_command_bar_api.py",
    "apps/portal/tests/test_ai_engine_room_apis.py",
)

TENANT_PROMPT_MARKERS = (
    "ABSOLUTE ANCHORING",
    "SYSTEM NAVIGATION PATHS",
    "PERMISSION-AWARE BOUNDARIES",
    "ZERO-FLUFF OUTPUT",
    "RESPONSE STRUCTURE",
    "[RETRIEVED KNOWLEDGE BASE SNIPPETS]",
    "[USER CURRENT CONTEXT]",
    "Escalate to Campus Helpdesk",
    "Main Menu > Academics > Course Catalog",
    "click the blue Save button",
    "As a [Role], you do not possess the [PERMISSION_NAME]",
    "**Direct Answer**",
    "**Execution Path**",
    "**Action Steps**",
    "**System Bound**",
    "New Enrollment",
    "Commit Records",
)

PLATFORM_PROMPT_MARKERS = (
    "Control Plane > AI Gateway Console",
    "Escalate via the operator helpdesk",
    "Do not paste API keys",
)

GATEWAY_MARKERS = (
    "assemble_ollama_payload",
    "validate_response_structure",
    "escalation_required",
    "process_platform_query",
    "execute_engine_room_query",
    "_finalize_model_text",
)

COMMAND_BAR_MARKERS = (
    "build_system_topology_map",
    "search_topology",
    "search_command_bar",
    "SYSTEM_TOPOLOGY_MAP",
    "first_line_support",
    "missing_permission",
    "fetchRemote",
    "ai-command-bar",
)

SETTINGS_MARKERS = (
    "AI_ENGINE_ROOM_SUPPORT",
    "AI_ENGINE_ROOM_TIMEOUT_SECONDS",
    "AI_ENGINE_ROOM_MAX_INPUT_TOKENS",
    "AI_CENTER_MAX_CONTEXT_DOCS",
    "OLLAMA_BASE_URL",
    "AI_GATEWAY_PROVIDER",
)


def main() -> int:
    failures: list[str] = []

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            failures.append(f"missing file: {rel}")

    prompts = (ROOT / "services/ai/prompts.py").read_text(encoding="utf-8")
    for marker in TENANT_PROMPT_MARKERS:
        if marker not in prompts:
            failures.append(f"TENANT prompt missing: {marker!r}")
    for marker in PLATFORM_PROMPT_MARKERS:
        if marker not in prompts:
            failures.append(f"PLATFORM prompt missing: {marker!r}")
    if "COMMAND_BAR_SNIPPET_HINT" not in prompts:
        failures.append("prompts.py missing COMMAND_BAR_SNIPPET_HINT")

    for rel, markers in (
        ("services/ai/gateway.py", GATEWAY_MARKERS),
        ("services/ai/topology_map.py", ("build_system_topology_map", "search_topology", "SYSTEM_TOPOLOGY_MAP", "first_line_support")),
        ("services/ai/command_bar.py", ("search_command_bar", "COMMAND_BAR_SNIPPET_HINT", "missing_permission")),
        ("apps/portal/views_command_bar.py", ("search_command_bar",)),
        ("static/js/rmc-command-palette.js", ("fetchRemote", "first_line_support")),
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                failures.append(f"{rel} missing: {marker!r}")

    settings = (ROOT / "config/settings.py").read_text(encoding="utf-8")
    for marker in SETTINGS_MARKERS:
        if marker not in settings:
            failures.append(f"config/settings.py missing: {marker}")

    urls = (ROOT / "apps/api/urls.py").read_text(encoding="utf-8")
    for name, symbol in (
        ("ai-command-bar", "api_command_bar_search"),
        ("ai-smart-settings", "api_smart_settings_assistant"),
        ("ai-import-error-resolver", "api_import_error_resolver"),
        ("ai-guardrail-report", "api_guardrail_report_generator"),
        ("ai-guided-tour", "api_guided_tour_planner"),
    ):
        if name not in urls or symbol not in urls:
            failures.append(f"api:{name} route not registered")

    guided_js = (ROOT / "static/js/rmc_ai_guided_assistant.js").read_text(encoding="utf-8")
    for marker in ("escalation_required", "active_url", "data-rmc-ai-escalation", "data-rmc-ai-feedback"):
        if marker not in guided_js:
            failures.append(f"rmc_ai_guided_assistant.js missing: {marker!r}")

    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    if "data-rmc-page-help" not in portal:
        failures.append("portal_base.html missing data-rmc-page-help")
    if "rmc-page-context-help.js" not in portal:
        failures.append("portal_base.html missing rmc-page-context-help.js")

    cp = (ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if "data-rmc-page-help" not in cp:
        failures.append("control_plane_skeleton.html missing data-rmc-page-help")
    if "rmc-page-context-help.js" not in cp:
        failures.append("control_plane_skeleton.html missing rmc-page-context-help.js")

    admin_shell = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
    if "data-rmc-page-help" not in admin_shell:
        failures.append("admin/base_site.html missing data-rmc-page-help")
    if "rmc-page-context-help.js" not in admin_shell:
        failures.append("admin/base_site.html missing rmc-page-context-help.js")

    gh_workflow = (ROOT / ".github/workflows/architectural-boundaries.yml").read_text(encoding="utf-8")
    if "ai-engine-room:" not in gh_workflow or "verify_ai_engine_room.py" not in gh_workflow:
        failures.append("architectural-boundaries.yml missing ai-engine-room CI job")

    release = (ROOT / "scripts/release_readiness_check.sh").read_text(encoding="utf-8")
    if "verify_ai_engine_room.py" not in release:
        failures.append("release_readiness_check.sh missing verify_ai_engine_room.py")

    phases = (ROOT / "scripts/verify_phases_3_11_gates.py").read_text(encoding="utf-8")
    if "verify_ai_engine_room.py" not in phases:
        failures.append("verify_phases_3_11_gates.py missing verify_ai_engine_room.py")

    tasks = (ROOT / "apps/platform_runtime/tasks.py").read_text(encoding="utf-8")
    if "engine_room_sync_ollama" not in tasks:
        failures.append("platform_runtime.tasks missing engine_room_sync_ollama chain")

    palette_js = (ROOT / "static/js/rmc-command-palette.js").read_text(encoding="utf-8")
    page_help_js = (ROOT / "static/js/rmc-page-context-help.js").read_text(encoding="utf-8")
    for marker in ("help_center_url", 'row.type === "escalate"', "rmc:cmdk:active_url", "active_url"):
        if marker not in palette_js:
            failures.append(f"rmc-command-palette.js missing: {marker!r}")
    if "help_center_url" not in page_help_js:
        failures.append("rmc-page-context-help.js must route via help_center_url")
    if "from=page_help" not in page_help_js or "active_url" not in page_help_js:
        failures.append("rmc-page-context-help.js missing page-aware help center params")

    ai_center_js = (ROOT / "static/js/_pages/siteconfig__ai_center.js").read_text(encoding="utf-8")
    if "data-active-url-override" not in ai_center_js:
        failures.append("siteconfig__ai_center.js missing data-active-url-override")

    ai_body = (ROOT / "templates/siteconfig/partials/ai_center_body.html").read_text(encoding="utf-8")
    if "data-rmc-ai-escalation" not in ai_body:
        failures.append("ai_center_body.html missing data-rmc-ai-escalation")

    ollama_doc = (ROOT / "docs/OLLAMA_OPERATIONS_AND_UPDATES.md").read_text(encoding="utf-8")
    if "/api/ai/smart-settings/" not in ollama_doc:
        failures.append("OLLAMA_OPERATIONS missing product assistant endpoints")

    cmdk_tpl = (ROOT / "templates/components/rmc_command_palette.html").read_text(encoding="utf-8")
    if "help_center_url" not in cmdk_tpl:
        failures.append("rmc_command_palette.html missing help_center_url in JSON")

    assistants = (ROOT / "apps/siteconfig/ai_assistants.py").read_text(encoding="utf-8")
    for key, api in (
        ("first_line_support", "api:ai-support-assistant"),
        ("smart_settings", "api:ai-smart-settings"),
        ("import_resolver", "api:ai-import-error-resolver"),
        ("report_generator", "api:ai-guardrail-report"),
        ("guided_tour", "api:ai-guided-tour"),
    ):
        if key not in assistants or api not in assistants:
            failures.append(f"ai_assistants missing {key} → {api}")

    registry = (ROOT / "apps/siteconfig/prompt_registry.py").read_text(encoding="utf-8")
    if '"first_line_support"' not in registry:
        failures.append("prompt_registry missing first_line_support fallback")

    for rel in ("services/ai/prompts.py", "services/ai/gateway.py", "services/ai/command_bar.py"):
        path = ROOT / rel
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"syntax error in {rel}: {exc}")

    if failures:
        print("verify_ai_engine_room: FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("verify_ai_engine_room: OK (tiers 1-5 engine room + product assistants 100%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
