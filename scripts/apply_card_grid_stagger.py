#!/usr/bin/env python3
"""v2.30 — apply `.rmc-reveal-stagger` to card-grid rows + `.rmc-reveal` to children.

Targets Bootstrap-grid rows whose direct children look card-like, so the
cards cascade in via the `--reveal-stagger` 90ms delay defined in v2.26 CSS.
Form rows, label-input pairs, and other non-card row uses are skipped.

Detection heuristic (intentionally conservative):
  - parent: <div class="... row ..."> with at least one Bootstrap gap class
            (g-1..g-5, gx-*, gy-*) — gap signals visual card grid intent
  - direct children: <div class="col*">  that themselves contain a
            descendant with a card-like class within the next ~600 chars
  - card-like = class includes any of: `card`, `dashboard-card`, `stat-card`,
            `kpi-card`, `metric-card`, `tile`, `portal-stat-card`,
            `dashboard-stat-card`

Output: idempotent. Skips rows already carrying `rmc-reveal-stagger`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"
EXCLUDE_DIR_PARTS = {"partials", "components", "errors", "emails", "admin", "unfold"}

CARD_HINTS = re.compile(
    r"\b(?:card|dashboard-card|stat-card|kpi-card|metric-card|tile|"
    r"portal-stat-card|dashboard-stat-card|mkt-edt-bell|insight-card|"
    r"portal-app-card|product-card|app-tile|module-card|feature-card)\b"
)

# Match a <div class="..."> with a row + gap class. Capture the attr block so
# we can rewrite the class list. Tolerates other attributes on the same tag.
ROW_OPEN = re.compile(
    r"<div(\s[^>]*?\bclass\s*=\s*([\"']))((?:(?!\2).)*?\brow\b(?:(?!\2).)*?\bg[xy]?-\d(?:(?!\2).)*?)(\2[^>]*?)>",
    re.IGNORECASE,
)

COL_OPEN = re.compile(
    r"<div(\s[^>]*?\bclass\s*=\s*([\"']))((?:(?!\2).)*?\bcol(?:-[A-Za-z0-9-]+)?\b(?:(?!\2).)*?)(\2[^>]*?)>",
    re.IGNORECASE,
)


def _find_matching_close(text: str, open_start: int, open_end: int) -> int:
    """Return index *after* the </div> that matches the opening tag at
    open_start..open_end. Naive depth counter — good enough for templated HTML."""
    depth = 1
    i = open_end
    open_re = re.compile(r"<div\b", re.IGNORECASE)
    close_re = re.compile(r"</div\s*>", re.IGNORECASE)
    while depth > 0 and i < len(text):
        o = open_re.search(text, i)
        c = close_re.search(text, i)
        if not c:
            return -1
        if o and o.start() < c.start():
            depth += 1
            i = o.end()
        else:
            depth -= 1
            i = c.end()
    return i if depth == 0 else -1


def _add_class_to_attr(attr_block: str, cls_to_add: str) -> str:
    """Inside an attribute block that contains a class="..." attribute, add
    cls_to_add to the class list. Idempotent."""
    cm = re.search(r'(\bclass\s*=\s*)(["\'])([^"\']*)\2', attr_block, re.IGNORECASE)
    if not cm:
        return attr_block
    existing = cm.group(3)
    if re.search(r"\b" + re.escape(cls_to_add) + r"\b", existing):
        return attr_block
    new_classes = (existing + " " + cls_to_add).strip()
    return attr_block[: cm.start(3)] + new_classes + attr_block[cm.end(3):]


def process(text: str) -> tuple[str, int, int]:
    """Returns (new_text, rows_staggered, cols_revealed)."""
    rows_staggered = 0
    cols_revealed = 0
    out: list[str] = []
    pos = 0
    while pos < len(text):
        m = ROW_OPEN.search(text, pos)
        if not m:
            out.append(text[pos:])
            break

        out.append(text[pos:m.start()])

        attrs_pre = m.group(1)   # leading attrs before class= (and class= itself opening)
        quote = m.group(2)
        class_content = m.group(3)
        attrs_post = m.group(4)  # everything from closing-quote onward to >
        full_attr_block = attrs_pre + class_content + attrs_post

        # If row already carries rmc-reveal-stagger, leave it.
        if re.search(r"\brmc-reveal-stagger\b", class_content):
            out.append(m.group(0))
            pos = m.end()
            continue

        close_idx = _find_matching_close(text, m.start(), m.end())
        if close_idx == -1:
            out.append(m.group(0))
            pos = m.end()
            continue

        row_body = text[m.end():close_idx - len("</div>")]

        # Find the direct child columns. Use a depth-aware walk to ensure we
        # only touch DIRECT children of this row, not nested grids inside cards.
        # Cheap approximation: scan COL_OPEN matches whose position has equal
        # opens/closes between the row start and that match.
        child_cols: list[tuple[int, re.Match[str], str]] = []  # (abs_start, match, child_body)
        body_offset = m.end()
        depth_re = re.compile(r"<div\b|</div\s*>", re.IGNORECASE)

        # Walk the body, tracking depth manually so we only collect col-* divs
        # that sit at depth 1 (direct child of the row).
        depth = 0
        i = m.end()
        while i < close_idx:
            tag_m = depth_re.search(text, i, close_idx)
            if not tag_m:
                break
            if tag_m.group(0).lower().startswith("</div"):
                depth -= 1
                i = tag_m.end()
                continue
            # Opening div — check if it's a direct child col
            if depth == 0:
                col_m = COL_OPEN.match(text, tag_m.start())
                if col_m:
                    # Verify this col's descendants include a card-like class
                    col_close = _find_matching_close(text, col_m.start(), col_m.end())
                    if col_close != -1:
                        col_body = text[col_m.end():col_close - len("</div>")]
                        # Look in this col body for a card hint within a class attribute
                        if any(CARD_HINTS.search(cm2.group(1)) for cm2 in re.finditer(r'\bclass\s*=\s*["\']([^"\']+)["\']', col_body)):
                            child_cols.append((col_m.start(), col_m, col_body))
            depth += 1
            i = tag_m.end()

        if len(child_cols) < 2:
            # Not a real card grid; skip.
            out.append(m.group(0))
            pos = m.end()
            continue

        # Verified card grid: stagger the row + reveal each child column.
        new_attrs = _add_class_to_attr(full_attr_block, "rmc-reveal-stagger")
        out.append("<div" + new_attrs + ">")
        rows_staggered += 1

        # Reconstruct the body, rewriting each child col's opening tag.
        # Children are listed in order; we need to splice them carefully.
        last = m.end()
        for start_abs, col_m, _body in child_cols:
            # Append everything between last cursor and this child's start.
            out.append(text[last:start_abs])
            col_attrs_pre = col_m.group(1)
            col_quote = col_m.group(2)
            col_class = col_m.group(3)
            col_attrs_post = col_m.group(4)
            col_full_attr = col_attrs_pre + col_class + col_attrs_post
            if re.search(r"\brmc-reveal\b", col_class):
                out.append(col_m.group(0))
            else:
                new_col_attr = _add_class_to_attr(col_full_attr, "rmc-reveal")
                out.append("<div" + new_col_attr + ">")
                cols_revealed += 1
            last = col_m.end()
        # Append the remainder of the row body + closing </div>.
        out.append(text[last:close_idx])

        pos = close_idx

    return "".join(out), rows_staggered, cols_revealed


def _is_partial(p: Path) -> bool:
    return any(part in EXCLUDE_DIR_PARTS for part in p.parts)


def main() -> int:
    files_changed = 0
    total_rows = 0
    total_cols = 0
    for p in sorted(TEMPLATES_ROOT.rglob("*.html")):
        if _is_partial(p):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, rows, cols = process(src)
        if rows:
            p.write_text(new, encoding="utf-8")
            files_changed += 1
            total_rows += rows
            total_cols += cols
    print(f"Files changed: {files_changed}")
    print(f"Card-grid rows staggered: {total_rows}")
    print(f"Direct-child cols revealed: {total_cols}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
