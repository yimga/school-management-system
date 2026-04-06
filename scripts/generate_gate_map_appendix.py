#!/usr/bin/env python3
"""Generate/check the gate-map appendix in docs/PHASES_3_11_GATE_VERIFICATION.md.

[--base REPO_ROOT] selects the repository root for `docs/gate_map_appendix_config.json`
and `docs/PHASES_3_11_GATE_VERIFICATION.md` (default: .).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

START = "<!-- GATE_MAP_APPENDIX:START -->"
END = "<!-- GATE_MAP_APPENDIX:END -->"


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _load_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


def _render(cfg: dict) -> str:
    lines: list[str] = []
    lines.append(cfg["title"])
    lines.append("")
    lines.append(cfg.get("description", ""))
    lines.append("")
    lines.append("| Verifier / check | Purpose | Entry points |")
    lines.append("|------------------|---------|--------------|")
    for row in cfg["entries"]:
        verifier = f"`{row['verifier']}`"
        purpose = row["purpose"]
        entry_points = "; ".join(f"`{x}`" for x in row["entry_points"])
        lines.append(f"| {verifier} | {purpose} | {entry_points} |")
    lines.append("")
    lines.append(cfg["note"])
    lines.append("")
    return "\n".join(lines)


def _replace_block(text: str, replacement: str) -> str:
    if START not in text or END not in text:
        raise RuntimeError(
            f"Missing markers in target doc: {START} ... {END}. "
            "Add markers once, then rerun."
        )
    before, rest = text.split(START, 1)
    _old, after = rest.split(END, 1)
    return f"{before}{START}\n{replacement}\n{END}{after}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default=".",
        help="Repository root (default: .)",
    )
    ap.add_argument("--check", action="store_true", help="Fail if appendix is out of date")
    ap.add_argument("--write", action="store_true", help="Write generated appendix to target")
    args = ap.parse_args()
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"generate_gate_map_appendix: {exc}", file=sys.stderr)
        return 1

    config_path = root / "docs" / "gate_map_appendix_config.json"
    target = root / "docs" / "PHASES_3_11_GATE_VERIFICATION.md"

    cfg = _load_config(config_path)
    generated = _render(cfg)
    current = target.read_text(encoding="utf-8")
    updated = _replace_block(current, generated)

    if args.check:
        if updated != current:
            print(
                "generate_gate_map_appendix: FAIL (appendix out of date). "
                "Run: python scripts/generate_gate_map_appendix.py --write",
                file=sys.stderr,
            )
            return 1
        print("generate_gate_map_appendix: PASS (appendix up to date)")
        return 0

    if args.write or not args.check:
        target.write_text(updated, encoding="utf-8")
        print("generate_gate_map_appendix: wrote appendix block")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
