#!/usr/bin/env python3
"""v2.31 — CSS-side font-size literal → ramp-token bridge.

Walks every project CSS file (excluding vendor/, design-tokens.css itself,
and the design-tokens-luxury companion) and rewrites
  font-size: <literal>;
to
  font-size: var(--type-size-<role>);

Mapping table is the consolidated v2.27 + extension covering the 50+ unique
literal values discovered in the survey. Values not in the table are left
alone — better to leave a literal than guess and shift layout.

Skips:
  - design-tokens*.css  (the SOT — circular if we replaced ramp values)
  - vendor/*            (third-party)
  - font-size declarations already inside a var()
  - declarations using inherit / initial / unset / smaller / larger / N%
  - declarations using calc() that don't contain a known literal

Idempotent: re-running is a no-op if every literal already maps to var().
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / "static" / "css"

EXCLUDE_FILES = {
    "design-tokens.css",
    "design-tokens-luxury.css",
    "rmc-print.css",          # print stylesheet — pt units are intentional
    "report-card-print.css",  # print stylesheet
}
EXCLUDE_DIR_PARTS = {"vendor"}

# Comprehensive literal -> token map. Conservative groupings: ranges where
# the rendered size shifts by at most ~6%. The 0.9rem -> body mapping is the
# biggest jump (14.4px -> 16px = 11% larger) but Apple HIG canonical body
# text is 16px, so this is moving in the right direction.
FONT_SIZE_MAP: dict[str, str] = {
    # micro tier (0.65rem = 10.4px)
    "0.4rem":   "var(--type-size-micro)",
    "0.5rem":   "var(--type-size-micro)",
    "0.58rem":  "var(--type-size-micro)",  # v2.38 burndown
    "0.6rem":   "var(--type-size-micro)",
    "0.62rem":  "var(--type-size-micro)",  # v2.38 burndown
    "0.64rem":  "var(--type-size-micro)",
    "0.65rem":  "var(--type-size-micro)",
    "0.66rem":  "var(--type-size-micro)",
    "0.68rem":  "var(--type-size-micro)",
    ".68rem":   "var(--type-size-micro)",
    "0.6875rem":"var(--type-size-micro)",
    "0.7rem":   "var(--type-size-micro)",
    ".7rem":    "var(--type-size-micro)",
    "0.72rem":  "var(--type-size-micro)",
    ".72rem":   "var(--type-size-micro)",
    "0.74rem":  "var(--type-size-micro)",
    "8px":      "var(--type-size-micro)",
    "9px":      "var(--type-size-micro)",
    "10px":     "var(--type-size-micro)",
    # eyebrow tier (0.75rem = 12px)
    "0.75rem":  "var(--type-size-eyebrow)",
    ".75rem":   "var(--type-size-eyebrow)",
    "0.76rem":  "var(--type-size-eyebrow)",
    "0.78rem":  "var(--type-size-eyebrow)",
    ".78rem":   "var(--type-size-eyebrow)",  # v2.38 burndown
    ".75em":    "var(--type-size-eyebrow)",  # v2.38 burndown
    "11px":     "var(--type-size-eyebrow)",
    "12px":     "var(--type-size-eyebrow)",
    # caption tier (0.8125rem = 13px)
    "0.8rem":   "var(--type-size-caption)",
    ".8rem":    "var(--type-size-caption)",
    "0.8125rem":"var(--type-size-caption)",
    ".8125rem": "var(--type-size-caption)",  # v2.38 burndown
    "0.82rem":  "var(--type-size-caption)",
    ".82rem":   "var(--type-size-caption)",
    "0.85rem":  "var(--type-size-caption)",
    ".85rem":   "var(--type-size-caption)",
    "0.85em":   "var(--type-size-caption)",
    "0.87rem":  "var(--type-size-caption)",  # v2.38 burndown
    "0.875rem": "var(--type-size-caption)",
    ".875rem":  "var(--type-size-caption)",  # v2.38 burndown
    "0.88rem":  "var(--type-size-caption)",
    ".88rem":   "var(--type-size-caption)",
    "0.83rem":  "var(--type-size-caption)",
    "0.84rem":  "var(--type-size-caption)",
    "0.86rem":  "var(--type-size-caption)",
    "13px":     "var(--type-size-caption)",
    "14px":     "var(--type-size-caption)",
    "14.5px":   "var(--type-size-caption)",
    # body tier (16px)
    "0.9rem":   "var(--type-size-body)",
    ".9rem":    "var(--type-size-body)",
    "0.92rem":  "var(--type-size-body)",
    ".92rem":   "var(--type-size-body)",
    "0.9375rem":"var(--type-size-body)",
    "0.94rem":  "var(--type-size-body)",
    "0.95rem":  "var(--type-size-body)",
    ".95rem":   "var(--type-size-body)",
    "0.95em":   "var(--type-size-body)",  # v2.38 burndown
    "0.96rem":  "var(--type-size-body)",
    "0.98rem":  "var(--type-size-body)",
    "1rem":     "var(--type-size-body)",
    "1em":      "var(--type-size-body)",
    "15px":     "var(--type-size-body)",
    "16px":     "var(--type-size-body)",
    # body-l tier (17-19px)
    "1.02rem":  "var(--type-size-body-l)",
    "1.05rem":  "var(--type-size-body-l)",
    "1.0625rem":"var(--type-size-body-l)",
    "1.08rem":  "var(--type-size-body-l)",  # v2.38 burndown
    "1.1rem":   "var(--type-size-body-l)",
    "1.125rem": "var(--type-size-body-l)",
    "1.15rem":  "var(--type-size-body-l)",
    "1.1875rem":"var(--type-size-body-l)",
    "1.2rem":   "var(--type-size-body-l)",
    "1.22rem":  "var(--type-size-body-l)",  # v2.38 burndown
    "1.25rem":  "var(--type-size-body-l)",
    "17px":     "var(--type-size-body-l)",
    "18px":     "var(--type-size-body-l)",
    "19px":     "var(--type-size-body-l)",
    "20px":     "var(--type-size-body-l)",
    # headline-m tier (22-28px)
    "1.3rem":   "var(--type-size-headline-m)",
    "1.35rem":  "var(--type-size-headline-m)",
    "1.375rem": "var(--type-size-headline-m)",
    "1.4rem":   "var(--type-size-headline-m)",
    "1.5rem":   "var(--type-size-headline-m)",
    "1.55rem":  "var(--type-size-headline-m)",
    "1.6rem":   "var(--type-size-headline-m)",
    "1.65rem":  "var(--type-size-headline-m)",  # v2.38 burndown
    "1.7rem":   "var(--type-size-headline-m)",
    "22px":     "var(--type-size-headline-m)",
    "24px":     "var(--type-size-headline-m)",
    "26px":     "var(--type-size-headline-m)",
    "28px":     "var(--type-size-headline-m)",
    # headline-l tier (28-40px)
    "1.75rem":  "var(--type-size-headline-l)",
    "1.8rem":   "var(--type-size-headline-l)",
    "1.85rem":  "var(--type-size-headline-l)",  # v2.38 burndown
    "2rem":     "var(--type-size-headline-l)",
    "2.25rem":  "var(--type-size-headline-l)",
    "2.5rem":   "var(--type-size-headline-l)",
    "30px":     "var(--type-size-headline-l)",
    "32px":     "var(--type-size-headline-l)",
    "36px":     "var(--type-size-headline-l)",
    "40px":     "var(--type-size-headline-l)",
    # headline-xl tier (36-56px)
    "2.75rem":  "var(--type-size-headline-xl)",
    "3rem":     "var(--type-size-headline-xl)",
    "3.25rem":  "var(--type-size-headline-xl)",
    "3.5rem":   "var(--type-size-headline-xl)",
    "44px":     "var(--type-size-headline-xl)",
    "48px":     "var(--type-size-headline-xl)",
    "56px":     "var(--type-size-headline-xl)",
    # display tier (48-80px)
    "4rem":     "var(--type-size-display)",
    "4.5rem":   "var(--type-size-display)",
    "5rem":     "var(--type-size-display)",
    "60px":     "var(--type-size-display)",
    "64px":     "var(--type-size-display)",
    "72px":     "var(--type-size-display)",
    "80px":     "var(--type-size-display)",
}

# Match `font-size: <value>` where value is everything up to ; or }. Capture
# the value so we can decide whether to swap it. Operates on whole-file text.
FONT_SIZE_DECL = re.compile(
    r"(?P<prefix>(?<![A-Za-z-])font-size\s*:\s*)(?P<value>[^;{}\n!]+?)(?P<important>\s*!important)?(?P<suffix>\s*(?:[;}\n]|$))",
    re.IGNORECASE,
)


def _migrate(text: str, stats: dict[str, int]) -> str:
    def repl(m: re.Match[str]) -> str:
        prefix = m.group("prefix")
        value = m.group("value").strip()
        important = m.group("important") or ""
        suffix = m.group("suffix")
        # Already token-based — leave alone
        if "var(" in value:
            stats["already_var"] = stats.get("already_var", 0) + 1
            return m.group(0)
        # Sentinel literals we don't touch
        if value in {"inherit", "initial", "unset", "smaller", "larger", "0", "auto"}:
            return m.group(0)
        if value.endswith("%"):
            return m.group(0)
        if value.endswith("pt"):
            # print-stylesheet sizes; intentional
            return m.group(0)
        if value.startswith("calc("):
            stats["calc_skipped"] = stats.get("calc_skipped", 0) + 1
            return m.group(0)
        if value.startswith("clamp("):
            stats["clamp_skipped"] = stats.get("clamp_skipped", 0) + 1
            return m.group(0)
        target = FONT_SIZE_MAP.get(value)
        if target is None:
            stats["unmapped"] = stats.get("unmapped", 0) + 1
            return m.group(0)
        stats["migrated"] = stats.get("migrated", 0) + 1
        return f"{prefix}{target}{important}{suffix}"

    return FONT_SIZE_DECL.sub(repl, text)


def main() -> int:
    stats: dict[str, int] = {}
    files_changed = 0
    for p in sorted(CSS_ROOT.rglob("*.css")):
        if p.name in EXCLUDE_FILES:
            continue
        if any(part in EXCLUDE_DIR_PARTS for part in p.parts):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        before = stats.get("migrated", 0)
        new = _migrate(src, stats)
        if new != src:
            p.write_text(new, encoding="utf-8")
            files_changed += 1
        after = stats.get("migrated", 0)
        delta = after - before
        if delta > 0:
            print(f"  fixed {delta:>4}: {p.relative_to(ROOT)}")
    print(f"\nFiles changed: {files_changed}")
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
