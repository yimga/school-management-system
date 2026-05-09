"""inject_visually_hidden_h1 — for pages with no h1/h2/h3 anywhere.

For every template that:
  1. Extends a base, and
  2. Defines ``{% block content %}``, and
  3. Has zero ``<h1>`` elements (verified via a relaxed regex), and
  4. Has a ``{% block title %}…{% endblock %}`` we can lift the title from,

…inject a single ``<h1 class="visually-hidden">{title}</h1>`` immediately
after ``{% block content %}`` opens. Visually invisible (Bootstrap class
that screen readers + audit verifiers see), preserving the existing layout.

Defaults to dry-run; pass --apply to actually write.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"

RE_EXTENDS = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']', re.IGNORECASE)
RE_BLOCK_TITLE = re.compile(
    r"\{%\s*block\s+title\s*%\}(.+?)\{%\s*endblock(?:\s+title)?\s*%\}",
    re.IGNORECASE | re.DOTALL,
)
RE_BLOCK_CONTENT_OPEN = re.compile(
    r"\{%\s*block\s+content\s*%\}",
    re.IGNORECASE,
)
RE_H1_ANY = re.compile(r"<h1[\s>]", re.IGNORECASE)
RE_DJANGO_COMMENT_BLOCK = re.compile(
    r"\{%\s*comment\s*(?:\".*?\")?\s*%\}.*?\{%\s*endcomment\s*%\}",
    re.IGNORECASE | re.DOTALL,
)
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
RE_LINE_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)

SKIP_DIR_PARTS = {"partials", "components", "errors", "emails", "admin", "unfold"}


def _is_partial(path: Path) -> bool:
    return any(p.lower() in SKIP_DIR_PARTS for p in path.parts)


def _strip_comments(text: str) -> str:
    text = RE_DJANGO_COMMENT_BLOCK.sub("", text)
    text = RE_HTML_COMMENT.sub("", text)
    text = RE_LINE_COMMENT.sub("", text)
    return text


def _candidate_files(only: set[str] | None) -> list[Path]:
    out: list[Path] = []
    for p in TEMPLATES_ROOT.rglob("*.html"):
        if _is_partial(p):
            continue
        if only:
            rel_parts = {x.lower() for x in p.relative_to(TEMPLATES_ROOT).parts}
            if not (rel_parts & only):
                continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not RE_EXTENDS.search(text):
            continue
        clean = _strip_comments(text)
        if RE_H1_ANY.search(clean):
            continue
        if not RE_BLOCK_CONTENT_OPEN.search(text):
            continue
        if not RE_BLOCK_TITLE.search(text):
            continue
        out.append(p)
    return out


def _extract_title_expression(text: str) -> str | None:
    """Pull the inside of {% block title %}...{% endblock %}.

    We keep the original Django expression intact (`{% trans "..." %}` etc.)
    so the h1 text matches the document title.
    """
    m = RE_BLOCK_TITLE.search(text)
    if not m:
        return None
    inner = m.group(1).strip()
    # Strip any nested {% block %} (e.g. {% block backend_title %}…{% endblock %})
    # by keeping only the inner-most stripped content.
    inner = re.sub(r"\{%\s*block\s+\w+\s*%\}", "", inner)
    inner = re.sub(r"\{%\s*endblock(?:\s+\w+)?\s*%\}", "", inner)
    inner = inner.strip()
    return inner or None


def _inject(text: str, title_expr: str) -> tuple[str, bool]:
    """Insert <h1 class="visually-hidden"> right after the block content tag."""
    new_h1 = (
        '\n  <h1 class="visually-hidden" data-rmc-injected-h1="1">'
        f'{title_expr}'
        '</h1>'
    )
    new_text, n = RE_BLOCK_CONTENT_OPEN.subn(
        lambda m: m.group(0) + new_h1, text, count=1
    )
    return new_text, n > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run).")
    parser.add_argument("--only", type=str, default="", help="Comma-separated dir filter.")
    args = parser.parse_args()

    only = {p.strip().lower() for p in args.only.split(",") if p.strip()} or None
    candidates = _candidate_files(only)
    print(f"inject_visually_hidden_h1: {len(candidates)} candidate template(s)")

    written = 0
    skipped = 0
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        title = _extract_title_expression(text)
        if not title:
            skipped += 1
            continue
        new_text, ok = _inject(text, title)
        if not ok:
            skipped += 1
            continue
        rel = path.relative_to(ROOT)
        if args.apply:
            path.write_text(new_text, encoding="utf-8")
            print(f"  INJECTED {rel}")
        else:
            print(f"  WOULD INJECT {rel}  // title: {title[:60]!r}")
        written += 1

    if not args.apply:
        print(f"\nDRY-RUN: would inject {written} h1(s); {skipped} skipped.")
        print("Re-run with --apply to write.")
    else:
        print(f"\nDone. Injected {written} h1(s); {skipped} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
