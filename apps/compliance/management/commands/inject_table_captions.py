"""
Pass 10.B / 10.D: bulk-inject WCAG 1.3.1 `<caption>` tags into data tables.

Walks `templates/**/*.html` and finds `<table ...>` elements that do NOT
already carry a `<caption>` within the next ~10 lines. For each hit,
inserts `<caption class="visually-hidden">{% trans "..." %}</caption>`
using a layered heuristic:

  1. nearest preceding `<h1>`..`<h6>` / `<summary>` element
  2. `.card-title` text
  3. `.card-header` text (including nested `<strong>`, links, etc.)
  4. `{% include "...page_header.html" with title=_("...") %}` includes
  5. `cp-mini-heading` / `mini-heading` / `section-title` / `panel-title` classes
  6. `.text-uppercase` / `.eyebrow` micro-headings
  7. file-level `{% block title %}` / `{% block backend_title %}` /
     `{% block cp_title %}` or the visually-hidden injected h1 fallback

Tables that already have `aria-label` / `aria-labelledby` (accessible
name present) or `role="presentation"` (layout, not data) are skipped.
Email templates (`templates/emails/`) are skipped wholesale — they're
layout-table only.

DRY-RUN by default; pass `--write` to mutate files. Idempotent — re-running
is safe.

  python manage.py inject_table_captions                  # dry-run
  python manage.py inject_table_captions --write          # apply
  python manage.py inject_table_captions --path templates/finance --write
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management.base import BaseCommand

TABLE_OPEN_RE = re.compile(r"^(?P<indent>\s*)<table\b(?P<attrs>[^>]*)>", re.IGNORECASE)
ARIA_NAME_RE = re.compile(r"\baria-label(?:ledby)?\s*=", re.IGNORECASE)
PRESENTATION_ROLE_RE = re.compile(r'\brole\s*=\s*"(?:presentation|none)"', re.IGNORECASE)
HEADING_RE = re.compile(
    r"<(?:h[1-6]|summary)\b[^>]*>(?P<inner>.+?)</(?:h[1-6]|summary)>",
    re.IGNORECASE | re.DOTALL,
)
CARD_TITLE_RE = re.compile(
    r'class="[^"]*\bcard-title\b[^"]*"[^>]*>(?P<inner>[^<]+(?:<(?!/)[^>]*>[^<]*</[^>]+>[^<]*)*?)</',
    re.IGNORECASE,
)
CARD_HEADER_RE = re.compile(
    r'class="[^"]*\bcard-header\b[^"]*"[^>]*>(?P<inner>.+?)</div>',
    re.IGNORECASE | re.DOTALL,
)
PAGE_HEADER_TITLE_RE = re.compile(
    r'include\s+"[^"]*page_header\.html"\s+with[^%]*\btitle\s*=\s*(?P<inner>_\([^)]+\)|"[^"]+"|\'[^\']+\')',
    re.IGNORECASE,
)
TITLE_KW_RE = re.compile(
    r'\btitle\s*=\s*(?P<inner>_\([^)]+\)|"[^"]+"|\'[^\']+\')',
    re.IGNORECASE,
)
HEADING_CLASS_RE = re.compile(
    r'class="[^"]*(?:cp-mini-heading|mini-heading|section-title|sub-heading|widget-title|panel-title|h6|h5|h4)\b[^"]*"[^>]*>(?P<inner>.+?)</',
    re.IGNORECASE | re.DOTALL,
)
EYEBROW_RE = re.compile(
    r'class="[^"]*(?:text-uppercase|eyebrow)[^"]*"[^>]*>(?P<inner>[^<]+(?:<(?!/)[^>]*>[^<]*</[^>]+>[^<]*)*?)</',
    re.IGNORECASE,
)
TABLE_CLOSE_RE = re.compile(r"</table>", re.IGNORECASE)
BLOCK_TITLE_RE = re.compile(
    r"\{%\s*block\s+(?:title|backend_title|cp_title|admin_title|page_title)\s*%\}(?P<inner>.+?)\{%\s*endblock\s*%\}",
    re.IGNORECASE | re.DOTALL,
)
INJECTED_H1_RE = re.compile(
    r'<h1\b[^>]*data-rmc-injected-h1[^>]*>(?P<inner>.+?)</h1>',
    re.IGNORECASE | re.DOTALL,
)

# Layout-table directories: skip entirely.
SKIP_PATH_PARTS = {"emails", "node_modules"}


def _strip_inline_html(text: str) -> str:
    text = re.sub(
        r"</?(?:span|i|em|strong|b|small|code|sup|sub|kbd|abbr|mark|div|a)\b[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _unwrap_python_string(literal: str) -> str:
    """_("...") / "..." / '...' -> {% trans "..." %}"""
    literal = literal.strip()
    if literal.startswith("_("):
        inner = literal[2:].rstrip(")").strip()
        if inner and inner[0] in "\"'" and inner[-1] in "\"'":
            inner = inner[1:-1]
        return f'{{% trans "{inner}" %}}'
    if literal and literal[0] in "\"'" and literal[-1] in "\"'":
        inner = literal[1:-1]
        return f'{{% trans "{inner}" %}}'
    return literal


def _is_useful_caption(text: str) -> bool:
    if not text:
        return False
    visible = re.sub(r"\{%.+?%\}|\{\{.+?\}\}", "", text).strip()
    bare = re.sub(r"[\s\W]+", "", visible)
    if "{% trans" in text or "{% blocktrans" in text or "{{" in text:
        return True
    return len(bare) >= 3


def _find_caption_text(lines: list[str], table_idx: int) -> str | None:
    for j in range(table_idx - 1, max(-1, table_idx - 30), -1):
        line = lines[j]
        if TABLE_CLOSE_RE.search(line):
            return None
        for regex in (HEADING_RE, CARD_TITLE_RE, CARD_HEADER_RE):
            m = regex.search(line)
            if m:
                inner = _strip_inline_html(m.group("inner"))
                if _is_useful_caption(inner):
                    return inner
        m = PAGE_HEADER_TITLE_RE.search(line)
        if m:
            return _unwrap_python_string(m.group("inner"))
        m = TITLE_KW_RE.search(line)
        if m and "{% block title" in line:
            return _unwrap_python_string(m.group("inner"))
        for regex in (HEADING_CLASS_RE, EYEBROW_RE):
            m = regex.search(line)
            if m:
                inner = _strip_inline_html(m.group("inner"))
                if _is_useful_caption(inner):
                    return inner
    return None


def _find_file_level_title(content: str) -> str | None:
    m = INJECTED_H1_RE.search(content)
    if m:
        inner = _strip_inline_html(m.group("inner"))
        if _is_useful_caption(inner):
            return inner
    m = BLOCK_TITLE_RE.search(content)
    if m:
        inner = _strip_inline_html(m.group("inner"))
        if _is_useful_caption(inner):
            return inner
    return None


def _process(content: str) -> tuple[str, int, int]:
    """Return (new_content, captions_added, tables_skipped_no_heading)."""
    lines = content.split("\n")
    file_fallback = _find_file_level_title(content)
    added = 0
    skipped = 0
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        m = TABLE_OPEN_RE.match(line)
        if not m:
            continue
        attrs = m.group("attrs") or ""
        if ARIA_NAME_RE.search(attrs) or PRESENTATION_ROLE_RE.search(attrs):
            continue
        chunk = "\n".join(lines[i : i + 10])
        if "<caption" in chunk.lower():
            continue
        caption = _find_caption_text(lines, i) or file_fallback
        if not caption:
            skipped += 1
            continue
        indent = m.group("indent") + "  "
        if "{%" in caption or "{{" in caption:
            inner = caption
        else:
            safe = caption.replace('"', "'")
            inner = f'{{% trans "{safe}" %}}'
        out.append(f'{indent}<caption class="visually-hidden">{inner}</caption>')
        added += 1
    return "\n".join(out), added, skipped


def _iter_files(root: Path, ext: str) -> Iterable[Path]:
    for p in root.rglob(f"*{ext}"):
        if any(part in SKIP_PATH_PARTS for part in p.parts):
            continue
        yield p


class Command(BaseCommand):
    help = "Inject missing <caption class='visually-hidden'> into data tables (WCAG 1.3.1)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default="templates", help="Root to scan.")
        parser.add_argument("--write", action="store_true", help="Apply (default: dry-run).")
        parser.add_argument("--ext", default=".html", help="Extension to scan.")

    def handle(self, *args, **options):
        root_arg = options["path"]
        write = bool(options["write"])
        ext = options["ext"]

        base = Path(settings.BASE_DIR) if hasattr(settings, "BASE_DIR") else Path(".")
        root = (base / root_arg).resolve() if not Path(root_arg).is_absolute() else Path(root_arg)
        if not root.exists():
            self.stderr.write(self.style.ERROR(f"Path not found: {root}"))
            return

        files_scanned = 0
        files_changed = 0
        captions_added = 0
        tables_skipped = 0

        for path in sorted(_iter_files(root, ext)):
            files_scanned += 1
            try:
                original = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new_content, added, skipped = _process(original)
            tables_skipped += skipped
            if added == 0:
                continue
            files_changed += 1
            captions_added += added
            try:
                rel = path.relative_to(base)
            except ValueError:
                rel = path
            self.stdout.write(
                f"{'WRITE' if write else 'DRY'}: {rel} (+{added} caption{'s' if added != 1 else ''})"
            )
            if write:
                path.write_text(new_content, encoding="utf-8")

        verb = "would add" if not write else "added"
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {files_scanned} files; {verb} {captions_added} caption(s) in "
                f"{files_changed} file(s); {tables_skipped} table(s) had no heading to derive from."
            )
        )
