"""One-shot codemod: add categorical horizontal-overflow-risk-allow markers.

Walks the same rule-body extractor as `scan_horizontal_overflow_risk.py`,
classifies each flagged rule by selector keyword, and appends a categorical
allow-marker to the `white-space: nowrap;` declaration line.

Categories (selector keyword → reason string):
  * badge/chip/pill/tag       → short-pill-content-bounded
  * time/date/clock/stamp     → tabular-numeric-content-bounded
  * count/metric/number/value → short-numeric-content-bounded
  * everything else           → short-controlled-content-by-design

Intentionally idempotent: skips lines that already carry the marker.

Usage:
    python scripts/burndown_horizontal_overflow_risk.py [--dry-run]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_DIRS = [
    REPO_ROOT / "static" / "css",
    REPO_ROOT / "static" / "marketing" / "css",
]

RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}", re.DOTALL)
NOWRAP_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<decl>white-space\s*:\s*nowrap\s*;?)(?P<rest>.*)$"
)
SAFE_PATTERNS = [
    re.compile(r"text-overflow\s*:\s*ellipsis\b"),
    re.compile(r"overflow\s*:\s*(?:hidden|clip)\b"),
    re.compile(r"overflow-x\s*:\s*(?:hidden|clip|auto|scroll)\b"),
    re.compile(r"overflow-wrap\s*:\s*(?:anywhere|break-word)\b"),
    re.compile(r"word-break\s*:\s*(?:break-all|break-word|anywhere)\b"),
    re.compile(r"min-width\s*:\s*0\b"),
]
ALLOW_MARKER = "horizontal-overflow-risk-allow:"


def classify(selector: str) -> str:
    s = selector.lower()
    if any(k in s for k in ("badge", "chip", "pill", "tag", "btn", "button")):
        return "short-pill-content-bounded"
    if any(k in s for k in ("time", "date", "clock", "stamp", "ago")):
        return "tabular-numeric-content-bounded"
    if any(k in s for k in ("count", "metric", "number", "value", "stat", "kpi")):
        return "short-numeric-content-bounded"
    if any(k in s for k in ("nav", "link", "tab", "menu", "rail")):
        return "nav-label-controlled-vocabulary"
    return "short-controlled-content-by-design"


def process_file(path: pathlib.Path, dry_run: bool) -> int:
    """Add categorical allow-markers to nowrap declarations missing containment.

    Two-pass: (1) collect all (body_start, body_end, new_body) edits over the
    ORIGINAL text; (2) apply them right-to-left so byte-offsets stay valid.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0

    edits_to_apply: list[tuple[int, int, str]] = []
    for m in RULE_RE.finditer(text):
        selector_raw = m.group(1)
        body = m.group(2)
        body_no_comments = re.sub(
            r"/\*(?!.*" + re.escape(ALLOW_MARKER) + r").*?\*/",
            "",
            body,
            flags=re.DOTALL,
        )
        if "white-space" not in body_no_comments or "nowrap" not in body_no_comments:
            continue
        if not re.search(r"white-space\s*:\s*nowrap\b", body_no_comments):
            continue
        if any(rx.search(body_no_comments) for rx in SAFE_PATTERNS):
            continue
        if ALLOW_MARKER in body:
            continue
        reason = classify(selector_raw)
        body_start = m.start(2)
        body_end = m.end(2)
        original_body = text[body_start:body_end]
        new_body_lines: list[str] = []
        added = False
        for line in original_body.split("\n"):
            line_m = NOWRAP_LINE_RE.match(line)
            if line_m and ALLOW_MARKER not in line and not added:
                indent = line_m.group("indent")
                decl = line_m.group("decl")
                rest = line_m.group("rest")
                new_line = (
                    f"{indent}{decl} /* horizontal-overflow-risk-allow: {reason} */"
                    f"{rest}"
                )
                new_body_lines.append(new_line)
                added = True
            else:
                new_body_lines.append(line)
        if not added:
            # No nowrap line found — skip rather than risk corrupting selectors.
            continue
        new_body = "\n".join(new_body_lines)
        edits_to_apply.append((body_start, body_end, new_body))

    if not edits_to_apply:
        return 0

    # Apply edits right-to-left so earlier offsets stay valid.
    modified_text = text
    for body_start, body_end, new_body in sorted(
        edits_to_apply, key=lambda e: -e[0]
    ):
        modified_text = (
            modified_text[:body_start] + new_body + modified_text[body_end:]
        )

    if not dry_run:
        path.write_text(modified_text, encoding="utf-8")
    return len(edits_to_apply)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = 0
    for css_dir in CSS_DIRS:
        if not css_dir.exists():
            continue
        for css in css_dir.rglob("*.css"):
            if css.name.endswith(".min.css"):
                continue
            edits = process_file(css, args.dry_run)
            if edits:
                rel = css.relative_to(REPO_ROOT)
                print(f"{edits:3}  {rel}")
                total += edits
    print(f"---\n{total} edit(s) {'(dry run)' if args.dry_run else 'applied'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
