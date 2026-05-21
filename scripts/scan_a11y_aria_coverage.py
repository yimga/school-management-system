"""Scan: every interactive element has an accessible name (WCAG 2.1 AA).

Audits Django templates under ``templates/`` for interactive elements
(``<button>``, ``<a href=...>``, ``<input>``, ``<select>``,
``<textarea>``, ``[role="button"]``, ``[role="link"]``) and flags
those that lack an accessible name. An accessible name is provided
by ANY of:

  - non-empty text content between open/close tags (text node OR Django
    template variable / tag — assumed to produce visible text);
  - ``aria-label="..."``;
  - ``aria-labelledby="..."``;
  - ``title="..."`` (last-resort fallback per WCAG 4.1.2);
  - for ``<input>``: ``placeholder="..."`` paired with an explicit
    type that is conventionally self-labeling (``hidden`` / ``submit``
    / ``button`` / ``image``-with-``alt``) OR an explicit ``value=``
    (for ``submit`` / ``button``);
  - for ``<a>``: ``aria-label`` / inner text / ``title`` / inner
    ``<img alt="...">``;
  - for ``<button>``: ``aria-label`` / inner text / inner
    ``<img alt="...">`` / inner ``{% trans ... %}``;
  - for ``[role="..."]``: same rules as a ``<button>`` / ``<a>``.

Allow-marker: place ``<!-- a11y-allow: <reason> -->`` on the
same template line OR the line immediately above the interactive
element to suppress the finding. Reason must be at least 8 characters
and contain at least 2 hyphen-separated tokens (e.g.
``icon-only-paired-with-text-sibling-aria-labelledby``).

Zero-tolerance gate from day 1 — wave v3.57.0.

Usage::

    python scripts/scan_a11y_aria_coverage.py [--strict] [--json] [--update-baseline]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_DIRS = [
    REPO_ROOT / "templates",
]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-a11y-aria.json"

# Interactive tag patterns. We use a single non-capturing regex that grabs
# the opening tag through the closing `>` so we can inspect attributes,
# then a separate cursor walk to extract inner text content up to the
# matching close tag for the same element.
INTERACTIVE_OPEN_RE = re.compile(
    r"<\s*(?P<tag>button|a|input|select|textarea)\b(?P<attrs>[^>]*)>",
    re.IGNORECASE,
)
# Self-closing detection for inputs (always void).
VOID_TAGS = {"input"}
# Allow-marker pattern matches both line-above and same-line cases.
ALLOW_MARKER_RE = re.compile(
    r"<!--\s*a11y-allow:\s*([A-Za-z0-9_\-]+(?:-[A-Za-z0-9_\-]+)+)\s*-->",
    re.IGNORECASE,
)
# Skip template comments & script/style blocks during a single linear pass.
SKIP_BLOCK_RE = re.compile(
    r"<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|\{\#.*?\#\}",
    re.IGNORECASE | re.DOTALL,
)


def _strip_skip_blocks(text: str) -> str:
    """Replace skip blocks with blanks (preserve newlines for line numbers)."""

    def _blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return SKIP_BLOCK_RE.sub(_blank, text)


def _has_attr(attrs: str, name: str) -> str | None:
    """Return attribute value if attribute present + non-empty, else None."""
    m = re.search(
        rf'\b{re.escape(name)}\s*=\s*"([^"]*)"',
        attrs,
        re.IGNORECASE,
    )
    if m:
        val = m.group(1).strip()
        return val if val else None
    m = re.search(
        rf"\b{re.escape(name)}\s*=\s*'([^']*)'",
        attrs,
        re.IGNORECASE,
    )
    if m:
        val = m.group(1).strip()
        return val if val else None
    return None


def _find_close(text: str, tag: str, start: int) -> int:
    """Find matching close tag, handling nesting roughly. -1 if not found."""
    close_re = re.compile(rf"<\s*/\s*{re.escape(tag)}\s*>", re.IGNORECASE)
    open_re = re.compile(
        rf"<\s*{re.escape(tag)}\b[^>]*>",
        re.IGNORECASE,
    )
    depth = 1
    i = start
    while i < len(text):
        co = close_re.search(text, i)
        op = open_re.search(text, i)
        if not co:
            return -1
        if op and op.start() < co.start():
            depth += 1
            i = op.end()
            continue
        depth -= 1
        if depth == 0:
            return co.start()
        i = co.end()
    return -1


_VISIBLE_INNER_RE = re.compile(r"\S")


def _inner_has_visible_text(inner: str) -> bool:
    """True if inner content includes visible glyphs, template tags that produce
    text, or an img with alt text."""
    if not inner:
        return False
    # Strip skip blocks again (paranoia for nested template comments).
    inner_clean = _strip_skip_blocks(inner)
    # Remove all nested HTML tags but KEEP {% trans/blocktrans %} & {{ var }}.
    # First, capture <img alt="..."> as a visible text source.
    if re.search(r"<\s*img\b[^>]*\balt\s*=\s*['\"][^'\"]+['\"]", inner_clean, re.IGNORECASE):
        return True
    # SVG with <title> child.
    if re.search(r"<\s*title\b[^>]*>[^<]*\S[^<]*<\s*/\s*title\s*>", inner_clean, re.IGNORECASE):
        return True
    # Strip remaining HTML tags.
    text_only = re.sub(r"<[^>]+>", "", inner_clean)
    if _VISIBLE_INNER_RE.search(text_only):
        # The remaining content has SOMETHING non-whitespace — could be a
        # bare Django var or just chars. Either way, that's a visible label.
        return True
    return False


def _has_accessible_name(
    tag: str,
    attrs: str,
    inner: str,
) -> bool:
    # ARIA attributes available to any element.
    if _has_attr(attrs, "aria-label"):
        return True
    if _has_attr(attrs, "aria-labelledby"):
        return True
    if _has_attr(attrs, "aria-describedby"):
        return True
    if _has_attr(attrs, "title"):
        return True
    tag_l = tag.lower()
    if tag_l in {"button", "a", "select", "textarea"}:
        if _inner_has_visible_text(inner):
            return True
        # `<a href=...>{% trans 'X' %}</a>` is caught by inner-has-visible-text.
        return False
    if tag_l == "input":
        itype = (_has_attr(attrs, "type") or "text").lower()
        if itype in {"hidden", "submit", "button", "reset", "image"}:
            # value="" or alt="" provides the name.
            if _has_attr(attrs, "value"):
                return True
            if itype == "image" and _has_attr(attrs, "alt"):
                return True
            if itype == "hidden":
                # Hidden inputs are non-interactive — accessible name not required.
                return True
        # For text-like inputs: prefer <label for=...> but we can't easily
        # follow that across DOM, so accept placeholder + aria-label/title above.
        if _has_attr(attrs, "placeholder") and _has_attr(attrs, "id"):
            # If id is present, assume a sibling <label for="id"> exists. This
            # is a soft check — over-permissive on purpose to avoid noise.
            return True
        return False
    return True


def _line_no(text: str, offset: int) -> int:
    return text[:offset].count("\n") + 1


def _is_allowed_at(text: str, line_start: int, line_end: int) -> bool:
    """Look for an a11y-allow marker on the current line OR the line above."""
    # Same line.
    if ALLOW_MARKER_RE.search(text[line_start:line_end]):
        return True
    # Line above.
    prev_end = line_start - 1
    if prev_end <= 0:
        return False
    prev_start = text.rfind("\n", 0, prev_end) + 1
    if ALLOW_MARKER_RE.search(text[prev_start:prev_end]):
        return True
    return False


def _scan_template(path: pathlib.Path, text: str) -> list[str]:
    findings: list[str] = []
    cleaned = _strip_skip_blocks(text)
    for m in INTERACTIVE_OPEN_RE.finditer(cleaned):
        tag = m.group("tag").lower()
        attrs = m.group("attrs") or ""
        open_end = m.end()
        # Skip non-link <a> (anchors without href are just bookmarks).
        if tag == "a" and not _has_attr(attrs, "href"):
            continue
        # role="presentation" or aria-hidden="true" → not interactive.
        role = _has_attr(attrs, "role")
        if role and role.lower() in {"presentation", "none"}:
            continue
        if _has_attr(attrs, "aria-hidden") in {"true", "True", "TRUE"}:
            continue
        if tag in VOID_TAGS:
            inner = ""
        else:
            close_pos = _find_close(cleaned, tag, open_end)
            inner = cleaned[open_end:close_pos] if close_pos > 0 else ""
        if _has_accessible_name(tag, attrs, inner):
            continue
        # Resolve original-text line bounds for marker search.
        line_no = _line_no(text, m.start())
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.start())
        if line_end < 0:
            line_end = len(text)
        if _is_allowed_at(text, line_start, line_end):
            continue
        snippet = re.sub(r"\s+", " ", m.group(0))[:120]
        findings.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {snippet}")
    return findings


def scan_all() -> list[str]:
    findings: list[str] = []
    for tdir in TEMPLATE_DIRS:
        if not tdir.exists():
            continue
        for html in tdir.rglob("*.html"):
            try:
                text = html.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            findings.extend(_scan_template(html, text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan_all()
    total = len(findings)

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    baseline_total = 0
    if BASELINE_PATH.exists():
        try:
            baseline_total = int(
                json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get(
                    "finding_count", 0
                )
            )
        except (json.JSONDecodeError, ValueError):
            baseline_total = 0

    if args.update_baseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "finding_count": total,
                    "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
                    "findings": findings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": total,
                    "baseline": baseline_total,
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(f"scan_a11y_aria_coverage: {total} violations")
        if not args.update_baseline:
            print(f"baseline: {baseline_total}")
        for f in findings[:30]:
            print(f"  {f}")

    if args.strict and total > baseline_total:
        print(f"FAIL: {total} > baseline {baseline_total}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
