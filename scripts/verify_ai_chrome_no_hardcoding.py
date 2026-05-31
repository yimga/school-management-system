#!/usr/bin/env python3
"""Aggressive audit: AI chrome must not hardcode URLs, env vendor names, or policy defaults in JS."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

FORBIDDEN_JS_PATTERNS = [
    (re.compile(r'["\']/api/ai-copilot/'), "hardcoded /api/ai-copilot/ path in JS"),
    (re.compile(r'["\']/studio/copilot/rail/'), "hardcoded /studio/copilot/rail/ path in JS"),
    (re.compile(r'["\']/api/ai/health'), "hardcoded /api/ai/health path in JS"),
    (re.compile(r'["\']/portal/ai/stream/'), "hardcoded /portal/ai/stream/ path in JS"),
    (re.compile(r"LITELLM_PROXY_URL"), "hardcoded LITELLM env hint in JS"),
    (re.compile(r"localhost:11434"), "hardcoded Ollama host in JS"),
    (re.compile(r"GEMINI_API"), "hardcoded Gemini reference in JS"),
]

REQUIRED_MARKERS = [
    (ROOT / "apps" / "portal" / "ai_chrome_config.py", "resolve_ai_chrome_config"),
    (ROOT / "apps" / "portal" / "ai_chrome_config.py", "ai_stream"),
    (ROOT / "templates" / "partials" / "rmc_ai_chrome_page_data.html", "page-data-rmc-ai-chrome"),
    (ROOT / "apps" / "siteconfig" / "models_support.py", "parent_student_ai_assistant_panel"),
    (ROOT / "apps" / "siteconfig" / "models_support.py", "enable_manager_ai_copilot_rail"),
    (ROOT / "templates" / "partials" / "cockpit" / "_ai_copilot_rail.html", "data-send-url"),
    (ROOT / "static" / "js" / "_pages" / "components__ai_copilot-1.js", "page-data-rmc-ai-chrome"),
]


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_js() -> list[str]:
    findings: list[str] = []
    for rel in (
        "static/js/_pages/components__ai_copilot-1.js",
        "static/js/_pages/rmc-copilot-rail.js",
        "static/js/rmc-ai-health-pill.js",
        "static/js/_pages/rmc-ai-stream-bridge.js",
    ):
        path = ROOT / rel
        text = _read(path)
        if not text:
            findings.append(f"missing file: {rel}")
            continue
        for pattern, msg in FORBIDDEN_JS_PATTERNS:
            if pattern.search(text):
                findings.append(f"{rel}: {msg}")
    return findings


def check_templates_no_raw_url_tags() -> list[str]:
    findings: list[str] = []
    for rel in (
        "templates/portal_base.html",
        "templates/base.html",
        "templates/control_plane_skeleton.html",
        "templates/components/ai_copilot.html",
    ):
        text = _read(ROOT / rel)
        if "{% url 'ai_copilot_query'" in text or '{% url "ai_copilot_query"' in text:
            findings.append(f"{rel}: use AI_COPILOT_QUERY_URL from ai_chrome_config, not raw url tag")
        if '{% url \'ai_health\'' in text or '{% url "ai_health"' in text:
            findings.append(f"{rel}: use AI_HEALTH_URL from ai_chrome_config, not raw url tag")
    return findings


def check_required_markers() -> list[str]:
    findings: list[str] = []
    for path, needle in REQUIRED_MARKERS:
        text = _read(path)
        if needle not in text:
            findings.append(f"{path.relative_to(ROOT)}: missing marker '{needle}'")
    return findings


def check_help_governance_configurable() -> list[str]:
    text = _read(ROOT / "apps" / "portal" / "help_governance.py")
    if "parent_student_ai_assistant_panel" not in text:
        return ["help_governance.py: parent/student policy must read tenant flags"]
    if "def parent_student_help_surface_policy(request" not in text:
        return ["help_governance.py: policy must accept request for tenant cascade"]
    return []


def main() -> int:
    findings: list[str] = []
    findings.extend(check_js())
    findings.extend(check_templates_no_raw_url_tags())
    findings.extend(check_required_markers())
    findings.extend(check_help_governance_configurable())
    if findings:
        for item in findings:
            print(f"FAIL: {item}")
        print(f"\nAI_CHROME_NO_HARDCODING_FAIL ({len(findings)} findings)")
        return 1
    print("AI_CHROME_NO_HARDCODING_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
