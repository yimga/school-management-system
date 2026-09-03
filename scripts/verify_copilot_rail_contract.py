"""Verify the Studio OS persistent AI presence contract (v3.53.1, 2026-05-21).

Locks 4 invariants the co-pilot rail relies on. PASS exits 0; any breach
exits 1 with a single-line diagnosis.

  1. cockpit_copilot_rail.html ships all 3 section hooks
     (data-rmc-copilot-rail-context / -insights / -actions).
  2. studio_os/shell.html loads rmc-copilot-rail.{js,css}.
  3. rmc-copilot-rail.js sets data-rmc-copilot-rail-armed synchronously
     (text-grep — no defer/async wrapping the setAttribute call).
  4. apps/studio_os/copilot_rail_service.py uses services.ai_helpers,
     NOT services.ai_gateway directly.
"""

from __future__ import annotations

import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_partial_hooks() -> list[str]:
    # Was studio_os/partials/cockpit_copilot_rail.html, retired 2026-09-02 with
    # its stylesheet: its only include sat inside the {% if False %} retired
    # cockpit block, so these hooks were being asserted on markup that never
    # rendered. The LIVE rail carries all three.
    partial = REPO_ROOT / "templates" / "partials" / "cockpit" / "_ai_copilot_rail.html"
    text = _read(partial)
    if not text:
        return [f"missing: {partial}"]
    findings: list[str] = []
    for hook in (
        "data-rmc-copilot-rail-context",
        "data-rmc-copilot-rail-insights",
        "data-rmc-copilot-rail-actions",
    ):
        if hook not in text:
            findings.append(
                f"{partial.relative_to(REPO_ROOT)}: missing section hook '{hook}'"
            )
    return findings


LIVE_RAIL_PARTIAL = "partials/cockpit/_ai_copilot_rail.html"
LIVE_RAIL_RULE = "rmc-copilot-rail__insights-list"
RAIL_SHELLS = ("templates/portal_base.html", "templates/control_plane_skeleton.html")


def _check_live_rail_rule_delivered() -> list[str]:
    """The one rule the LIVE rail partial needs must reach every shell that renders it."""
    import shell_css_contract as scc

    findings: list[str] = []
    rendering = [s for s in RAIL_SHELLS if scc.renders(s, LIVE_RAIL_PARTIAL)]
    if not rendering:
        # A zero here would otherwise pass vacuously: no shell, no requirement.
        return [
            "no shell renders %s -- the live co-pilot rail is unwired" % LIVE_RAIL_PARTIAL
        ]
    for shell_rel in rendering:
        delivered = False
        for name, _provider in scc.linked_stylesheet_sources(shell_rel).items():
            src = REPO_ROOT / "static" / "css" / name
            if src.is_file() and ("." + LIVE_RAIL_RULE) in _read(src):
                delivered = True
                break
        if not delivered:
            findings.append(
                "%s: renders %s but no stylesheet it loads defines .%s"
                % (shell_rel, LIVE_RAIL_PARTIAL, LIVE_RAIL_RULE)
            )
    return findings


def check_shell_wires_assets() -> list[str]:
    shell = REPO_ROOT / "templates" / "studio_os" / "shell.html"
    text = _read(shell)
    if not text:
        return [f"missing: {shell}"]
    findings: list[str] = []
    # Was: `if "rmc-copilot-rail.css" not in text`. That asserted a FILENAME
    # against studio_os/shell.html, and it had been red for months because
    # nothing loaded that file anywhere. Deleting the demand would have been
    # wrong too -- the question is whether the rule is DELIVERED, not whether
    # a name appears. Of the 18 selectors rmc-copilot-rail.css defined, 15 were
    # used only by studio_os/partials/cockpit_copilot_rail.html, whose sole
    # include sits inside the {% if False %} at studio_os/shell.html:87 (the
    # retired v3.53 Mission Cockpit chrome, kept unreachable on purpose). One
    # selector had a LIVE consumer, so it moved to rmc-cp-200x.css and the file
    # was deleted. This now checks the surviving contract: every shell that
    # actually renders the live rail partial must be delivered that rule.
    findings.extend(_check_live_rail_rule_delivered())
    if "rmc-copilot-rail.js" not in text:
        findings.append(
            f"{shell.relative_to(REPO_ROOT)}: rmc-copilot-rail.js not loaded"
        )
    # Defer / async on the rail script would break the armed-attribute timing.
    script_re = re.compile(r"<script[^>]*rmc-copilot-rail\.js[^>]*>")
    for m in script_re.finditer(text):
        tag = m.group(0)
        if " defer" in tag or " async" in tag:
            findings.append(
                f"{shell.relative_to(REPO_ROOT)}: rmc-copilot-rail.js must load without defer/async"
            )
    return findings


def check_js_armed_synchronous() -> list[str]:
    js_path = REPO_ROOT / "static" / "js" / "rmc-copilot-rail.js"
    text = _read(js_path)
    if not text:
        return [f"missing: {js_path}"]
    findings: list[str] = []
    armed_line = "data-rmc-copilot-rail-armed"
    if armed_line not in text:
        findings.append(
            f"{js_path.relative_to(REPO_ROOT)}: missing setAttribute('{armed_line}', '1') call"
        )
        return findings
    # Find the setAttribute call's line number; ensure it lives outside any
    # event listener / DOMContentLoaded handler.
    lines = text.splitlines()
    arm_idx = next(
        (i for i, l in enumerate(lines) if "setAttribute" in l and armed_line in l),
        -1,
    )
    if arm_idx < 0:
        findings.append(
            f"{js_path.relative_to(REPO_ROOT)}: armed attribute set call not found"
        )
        return findings
    # Check the call is not inside an init() / DOMContentLoaded() / addEventListener block.
    head = "\n".join(lines[:arm_idx])
    # Heuristic: the IIFE opens with `(function () {` and the armed-attr line
    # should appear inside the IIFE body but BEFORE the init() function and
    # BEFORE any DOMContentLoaded/addEventListener call.
    if "DOMContentLoaded" in head and "function init" in head:
        findings.append(
            f"{js_path.relative_to(REPO_ROOT)}: armed attribute appears after init() / DOMContentLoaded; must be synchronous"
        )
    return findings


def check_service_uses_ai_helpers() -> list[str]:
    """Use AST to confirm services.ai_helpers is imported AND services.ai_gateway is not."""
    import ast

    svc = REPO_ROOT / "apps" / "studio_os" / "copilot_rail_service.py"
    text = _read(svc)
    if not text:
        return [f"missing: {svc}"]
    findings: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [f"{svc.relative_to(REPO_ROOT)}: syntax error {e}"]

    imports_ai_helpers = False
    imports_ai_gateway = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "services.ai_helpers":
                imports_ai_helpers = True
            if module == "services.ai_gateway":
                imports_ai_gateway = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "services.ai_helpers":
                    imports_ai_helpers = True
                if alias.name == "services.ai_gateway":
                    imports_ai_gateway = True

    if not imports_ai_helpers:
        findings.append(
            f"{svc.relative_to(REPO_ROOT)}: missing import of services.ai_helpers"
        )
    if imports_ai_gateway:
        findings.append(
            f"{svc.relative_to(REPO_ROOT)}: app code must not import services.ai_gateway directly"
        )
    return findings


def check_send_urls_in_template() -> list[str]:
    """Send/stream endpoints must be template-resolved, not JS-hardcoded."""
    findings: list[str] = []
    for rel in (
        "templates/partials/cockpit/_ai_copilot_rail.html",
    ):
        path = REPO_ROOT / rel
        text = _read(path)
        if not text:
            findings.append(f"missing: {rel}")
            continue
        if "data-send-url" not in text or "copilot_rail_send" not in text:
            findings.append(f"{rel}: missing data-send-url from studio_os:copilot_rail_send")
        if "data-send-stream-url" not in text:
            findings.append(f"{rel}: missing data-send-stream-url")
    js_path = REPO_ROOT / "static" / "js" / "_pages" / "rmc-copilot-rail.js"
    js_text = _read(js_path)
    if "/studio/copilot/rail/send/" in js_text:
        findings.append(
            f"{js_path.relative_to(REPO_ROOT)}: hardcoded studio copilot send path"
        )
    if "rmc_manager_csrftoken" not in js_text:
        findings.append(
            f"{js_path.relative_to(REPO_ROOT)}: getCSRFToken must read rmc_manager_csrftoken (manager host isolation)"
        )
    if 'meta[name="csrf-token"]' not in js_text:
        findings.append(
            f"{js_path.relative_to(REPO_ROOT)}: getCSRFToken must fall back to meta csrf-token"
        )
    views_path = REPO_ROOT / "apps" / "studio_os" / "views_copilot_rail.py"
    views_text = _read(views_path)
    if "response_schema=\"guided_assistant\"" not in views_text:
        findings.append(
            f"{views_path.relative_to(REPO_ROOT)}: copilot rail send must use guided_assistant rules fallback"
        )
    if "extract_copilot_rail_reply" not in views_text and "_reply_text_from_invoke" not in views_text:
        findings.append(
            f"{views_path.relative_to(REPO_ROOT)}: missing guided reply formatter for rail send"
        )
    return findings


def main() -> int:
    all_findings: list[str] = []
    all_findings.extend(check_partial_hooks())
    all_findings.extend(check_shell_wires_assets())
    all_findings.extend(check_js_armed_synchronous())
    all_findings.extend(check_service_uses_ai_helpers())
    all_findings.extend(check_send_urls_in_template())
    if all_findings:
        for f in all_findings:
            print(f"FAIL: {f}")
        return 1
    print("PASS: co-pilot rail contract clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
