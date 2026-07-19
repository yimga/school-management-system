#!/usr/bin/env python3
"""
Phase 5 gate: Studio OS conformance.

Checks:
1) mode contracts (five canonical Studio modes)
2) legacy redirect coverage contract (legacy identities resolve to Studio OS)
3) Output Studio native-path constraints on touched panes

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Phase 5 Studio OS conformance."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_literal(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.literal_eval(node.value)
    raise KeyError(name)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_phase5_studio_os_conformance: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    views_py = root / "apps" / "studio_os" / "views.py"
    urls_py = root / "apps" / "studio_os" / "urls.py"
    deep_links_py = root / "apps" / "studio_os" / "deep_links.py"
    shell_main_tpl = (
        root / "templates" / "studio_os" / "partials" / "shell_main_content.html"
    )
    output_mode_tpl = (
        root / "templates" / "studio_os" / "partials" / "output_mode_canvas.html"
    )
    output_canvas_tpl = (
        root
        / "templates"
        / "studio_os"
        / "partials"
        / "workspace"
        / "output_canvas.html"
    )

    for p in (views_py, urls_py, deep_links_py, shell_main_tpl, output_mode_tpl, output_canvas_tpl):
        if not p.is_file():
            errors.append(f"Missing required file: {p.relative_to(root).as_posix()}")
    if errors:
        print("verify_phase5_studio_os_conformance:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    views_text = _read(views_py)
    urls_text = _read(urls_py)
    deep_links_text = _read(deep_links_py)
    shell_text = _read(shell_main_tpl)
    output_text = _read(output_canvas_tpl)
    output_shell_text = _read(output_mode_tpl)

    # 1) Mode contracts from STUDIO_MODES literal.
    try:
        modes_literal = _extract_literal(ast.parse(views_text), "STUDIO_MODES")
        mode_ids = {m.get("id") for m in modes_literal if isinstance(m, dict)}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Unable to parse STUDIO_MODES literal: {exc}")
        mode_ids = set()

    expected_mode_ids = {"experience", "automation", "output", "launch", "control"}
    if mode_ids != expected_mode_ids:
        errors.append(
            f"STUDIO_MODES ids mismatch. expected={sorted(expected_mode_ids)} got={sorted(mode_ids)}"
        )

    required_mode_routes = (
        'path("experience/", studio_shell, {"mode": "experience"}, name="experience")',
        'path("automation/", studio_shell, {"mode": "automation"}, name="automation")',
        'path("output/", studio_shell, {"mode": "output"}, name="output")',
        'path("launch/", studio_shell, {"mode": "launch"}, name="launch")',
        'path("control/", studio_shell, {"mode": "control"}, name="control")',
    )
    for route in required_mode_routes:
        if route not in urls_text:
            errors.append(f"studio_os/urls.py missing canonical mode route: {route}")

    # 2) Legacy redirect coverage contract in deep link map.
    for key in ("customizer", "workflow_hub", "report_library"):
        if f'("{key}"' not in deep_links_text:
            errors.append(f"studio_legacy_urls_map missing key: {key}")
    if "out[\"report_library\"]" not in deep_links_text or "pane=reports" not in deep_links_text:
        errors.append(
            "studio_legacy_urls_map must force report_library to Output pane=reports."
        )

    # 3) Output native constraints.
    for pane in (
        "dependency",
        "reports",
        "documents",
        "builder",
        "credentials",
        "branding",
        "policy",
    ):
        if f'"{pane}"' not in views_text:
            errors.append(f"views.py missing output pane token: {pane}")

    for pane in ("documents", "reports", "credentials", "branding", "policy", "builder", "dependency"):
        token = f"if output_pane == \"{pane}\""
        alt = f"elif output_pane == \"{pane}\""
        if token not in views_text and alt not in views_text:
            errors.append(f"views.py missing explicit output branch for pane: {pane}")
    if views_text.count('context["output_iframe_src"] = ""') < 7:
        errors.append("views.py must clear output_iframe_src in native output branches.")

    for label in ("Experience", "Automation", "Outputs", "Launch", "Control"):
        if label not in shell_text:
            errors.append(f"shell_main_content.html missing Studio mode label: {label}")
    # B1 (2026-06-22): studio-local #studio-cmd-palette retired; unified ⌘K via
    # studio_command_pill.html (data-rmc-cmdk-trigger). Keep include + pill markers.
    if "studio_os/partials/studio_command_pill.html" not in shell_text:
        errors.append(
            "shell_main_content.html missing Studio command pill include "
            "(studio_os/partials/studio_command_pill.html)."
        )
    pill_path = (
        root / "templates" / "studio_os" / "partials" / "studio_command_pill.html"
    )
    pill_text = _read(pill_path) if pill_path.is_file() else ""
    if "data-rmc-cmdk-trigger" not in pill_text or "studio-cmd-pill" not in pill_text:
        errors.append(
            "studio_command_pill.html missing unified ⌘K trigger contract "
            "(data-rmc-cmdk-trigger + studio-cmd-pill)."
        )

    for marker in (
        "output_pane == 'dependency'",
        "output_pane == 'reports'",
        "output_pane == 'documents'",
        "output_pane == 'builder'",
        "output_pane == 'credentials'",
        "output_pane == 'branding'",
        "output_pane == 'policy'",
    ):
        if marker not in output_text:
            errors.append(f"output_mode_canvas.html missing native pane branch: {marker}")

    if "output_iframe_src" not in output_text:
        errors.append("output_canvas.html missing fallback iframe contract.")
    if "workspace_layout.html" not in output_shell_text:
        errors.append("output_mode_canvas.html must include workspace_layout.html")
    if "data-studio-output-native=\"reports\"" not in _read(
        root
        / "templates"
        / "studio_os"
        / "partials"
        / "output_reports_library_body.html"
    ):
        errors.append("output_reports_library_body.html missing native marker for reports pane.")

    if errors:
        print("verify_phase5_studio_os_conformance:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_phase5_studio_os_conformance: PASS "
        "(mode contracts + legacy redirect coverage + output native constraints)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
