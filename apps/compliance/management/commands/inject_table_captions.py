"""
Pass 10.B: bulk-inject WCAG 1.3.1 `<caption>` tags into data tables.

Walks `templates/**/*.html` and finds `<table class="table…">` elements that
do NOT already carry a `<caption>` within their first 5 child lines. For each
hit, injects a `visually-hidden` caption derived from (in priority order):

  1. The table's `aria-label="…"` attribute (if present).
  2. The most recent `<h1>`/`<h2>` heading above the table.
  3. A generic "Data table" fallback.

The command is DRY-RUN by default. Pass `--write` to actually mutate files.

  python manage.py inject_table_captions                # report only
  python manage.py inject_table_captions --write        # mutate
  python manage.py inject_table_captions --path templates/finance --write

This is the platform-side tool that unblocks the 333-table sweep without
needing every author to handle each table by hand. Humans should still
review the diff before committing.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

TABLE_OPEN = re.compile(
    r"(?P<lead>^[ \t]*)<table(?P<attrs>[^>]*?)>",
    flags=re.IGNORECASE | re.MULTILINE,
)
CAPTION_NEARBY = re.compile(r"<caption\b", flags=re.IGNORECASE)
ARIA_LABEL = re.compile(r"""aria-label\s*=\s*["']([^"']+)["']""", flags=re.IGNORECASE)
HEADING_ABOVE = re.compile(
    r"<h[12][^>]*>(?P<text>[^<]{2,160})</h[12]>",
    flags=re.IGNORECASE,
)

CAPTION_FORMAT = (
    '{lead}  <caption class="visually-hidden">{{% trans "{text}" %}}</caption>\n'
)
LOOKAHEAD_CHARS = 400  # Bytes to scan after <table> for an existing <caption>.


class Command(BaseCommand):
    help = "Inject missing <caption> tags into Django templates (WCAG 1.3.1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="templates",
            help="Root directory to scan (default: templates).",
        )
        parser.add_argument(
            "--write",
            action="store_true",
            help="Actually write changes; default is dry-run (report only).",
        )
        parser.add_argument(
            "--ext",
            default=".html",
            help="File extension to scan (default: .html).",
        )

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

        for path in sorted(root.rglob(f"*{ext}")):
            files_scanned += 1
            try:
                original = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            new_content, added = self._process(original)
            if added == 0:
                continue
            files_changed += 1
            captions_added += added
            rel = path.relative_to(base) if path.is_relative_to(base) else path
            self.stdout.write(
                f"{'WRITE' if write else 'DRY'}: {rel} (+{added} caption{'s' if added != 1 else ''})"
            )
            if write:
                path.write_text(new_content, encoding="utf-8")

        verb = "would add" if not write else "added"
        self.stdout.write(
            self.style.SUCCESS(
                f"Scanned {files_scanned} files; {verb} {captions_added} caption(s) in {files_changed} file(s)."
            )
        )

    def _process(self, content: str) -> tuple[str, int]:
        added = 0
        last_heading_for_offset: dict[int, str] = {}
        # Pre-compute the latest preceding heading for each table match.
        for tbl in TABLE_OPEN.finditer(content):
            window = content[: tbl.start()]
            heading_matches = list(HEADING_ABOVE.finditer(window))
            last_heading_for_offset[tbl.start()] = (
                heading_matches[-1].group("text").strip()
                if heading_matches
                else ""
            )

        out: list[str] = []
        cursor = 0
        for tbl in TABLE_OPEN.finditer(content):
            # Skip if this table already has a caption within LOOKAHEAD_CHARS.
            window_after = content[tbl.end() : tbl.end() + LOOKAHEAD_CHARS]
            if CAPTION_NEARBY.search(window_after):
                continue

            attrs = tbl.group("attrs") or ""
            # Only target Bootstrap "table" class data tables — skip non-data tables.
            if "class=" not in attrs or "table" not in attrs.lower():
                continue

            caption_text = self._derive_caption(
                attrs=attrs,
                heading=last_heading_for_offset.get(tbl.start(), ""),
            )
            if not caption_text:
                continue

            # Append everything up to and including the <table…> open tag,
            # then inject the caption on the next line.
            out.append(content[cursor : tbl.end()])
            out.append("\n")
            out.append(
                CAPTION_FORMAT.format(
                    lead=tbl.group("lead") or "", text=caption_text.replace('"', "")
                )
            )
            cursor = tbl.end()
            # Skip the natural newline if present so we don't double-blank-line.
            if cursor < len(content) and content[cursor] == "\n":
                cursor += 1
            added += 1

        out.append(content[cursor:])
        return "".join(out), added

    @staticmethod
    def _derive_caption(*, attrs: str, heading: str) -> str:
        match = ARIA_LABEL.search(attrs)
        if match:
            return match.group(1).strip()
        if heading:
            cleaned = re.sub(r"\s+", " ", heading).strip()
            return f"Data table: {cleaned}" if cleaned else ""
        return "Data table"
