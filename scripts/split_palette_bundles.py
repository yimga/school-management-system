"""Wave C-3 — split consolidated heritage palette bundle into 10 per-family files.

Reads ``static/css/design-tokens-local-palettes.css`` and emits 10 files of the
form ``design-tokens-local-<family>.css`` so CDN caches can serve only the
palette family a tenant uses. Idempotent — safe to re-run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FAMILIES = (
    "editorial-cream",
    "warm-terracotta",
    "cool-indigo",
    "green-emerald",
    "desert-amber",
    "monsoon-teal",
    "sakura-blush",
    "andes-clay",
    "savanna-ochre",
    "nordic-slate",
)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "static" / "css" / "design-tokens-local-palettes.css"
    if not src.exists():
        print(f"FAIL: missing {src}")
        return 1
    text = src.read_text(encoding="utf-8")
    out_dir = src.parent
    written = 0
    for family in FAMILIES:
        block_re = re.compile(
            r"(?ms)^/\*\s*"
            + re.escape(family)
            + r"\s*—.*?\*/\s*\n:root\[data-rmc-local-palette=\""
            + re.escape(family)
            + r"\"\]\s*\{[^}]*\}",
        )
        match = block_re.search(text)
        if not match:
            print(f"WARN: palette family '{family}' block not found in source — skipping")
            continue
        block = match.group(0)
        header = (
            f"/* design-tokens-local-{family}.css — split from "
            f"design-tokens-local-palettes.css (Wave C-3 / batch 1402). */\n\n"
        )
        out = out_dir / f"design-tokens-local-{family}.css"
        out.write_text(header + block + "\n", encoding="utf-8")
        written += 1
    print(f"PALETTE_BUNDLE_SPLIT_PASS ({written}/{len(FAMILIES)} families written)")
    return 0 if written == len(FAMILIES) else 1


if __name__ == "__main__":
    sys.exit(main())
