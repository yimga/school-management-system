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


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_partial_hooks() -> list[str]:
    partial = REPO_ROOT / "templates" / "studio_os" / "partials" / "cockpit_copilot_rail.html"
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


def check_shell_wires_assets() -> list[str]:
    shell = REPO_ROOT / "templates" / "studio_os" / "shell.html"
    text = _read(shell)
    if not text:
        return [f"missing: {shell}"]
    findings: list[str] = []
    if "rmc-copilot-rail.css" not in text:
        findings.append(
            f"{shell.relative_to(REPO_ROOT)}: rmc-copilot-rail.css not loaded"
        )
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


def main() -> int:
    all_findings: list[str] = []
    all_findings.extend(check_partial_hooks())
    all_findings.extend(check_shell_wires_assets())
    all_findings.extend(check_js_armed_synchronous())
    all_findings.extend(check_service_uses_ai_helpers())
    if all_findings:
        for f in all_findings:
            print(f"FAIL: {f}")
        return 1
    print("PASS: co-pilot rail contract clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
