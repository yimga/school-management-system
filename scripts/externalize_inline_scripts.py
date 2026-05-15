"""externalize_inline_scripts — convert inline executable <script> blocks
to CSP-friendly forms.

For every page-level template that has at least one inline executable
``<script>`` (no ``src=`` and not a JSON data-island), the helper:

1. Extracts the script content.
2. Classifies it:
   - **PURE_JS** — no Django ``{{ }}`` or ``{% %}`` tags inside the script body.
     → Convert to an external ``static/js/_pages/<slug>.js`` file + replace the
       inline block with ``<script src="{% static 'js/_pages/<slug>.js' %}"></script>``.
   - **DJANGO_INTERPOLATED** — has ``{{ }}`` or ``{% %}``.
     → Skip (operator must convert to a JSON data island manually because the
       payload schema is page-specific). The helper logs the file so an
       operator can triage.

The helper is dry-run by default. Pass ``--apply`` to write changes.

Usage::

    python scripts/externalize_inline_scripts.py
    python scripts/externalize_inline_scripts.py --apply
    python scripts/externalize_inline_scripts.py --apply --only finance,portal
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"
OUT_DIR = ROOT / "static" / "js" / "_pages"

# Match the OPENING <script> tag of an inline executable block (no src=,
# no application/json|ld+json|importmap type).
RE_SCRIPT_OPEN = re.compile(
    r'<script(?![^>]*\bsrc=)(?![^>]*\btype=["\'](?:application/(?:json|ld\+json)|importmap)["\'])([^>]*)>',
    re.IGNORECASE,
)
RE_DJANGO_TAG = re.compile(r"\{\{|\{%")
RE_DJANGO_COMMENT_BLOCK = re.compile(
    r"\{%\s*comment\s*(?:\".*?\")?\s*%\}.*?\{%\s*endcomment\s*%\}",
    re.IGNORECASE | re.DOTALL,
)
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
RE_LINE_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
RE_LOAD_STATIC = re.compile(r"\{%\s*load[^%]*\bstatic\b[^%]*%\}", re.IGNORECASE)

# Page-level checks (skip-link, h1, etc.) skip these dirs because they're
# fragments. But for inline-script externalisation we DO want to process them
# — the inline script lives in the partial and ships to every including page.
SKIP_DIR_PARTS_FOR_PAGE_CHECKS = {"partials", "components", "errors", "emails", "admin", "unfold"}
SKIP_DIR_PARTS_FOR_EXTERNALISATION = {"admin", "unfold"}  # vendor only


def _is_partial(path: Path) -> bool:
    return any(p.lower() in SKIP_DIR_PARTS_FOR_EXTERNALISATION for p in path.parts)


def _strip_comments(text: str) -> str:
    text = RE_DJANGO_COMMENT_BLOCK.sub("", text)
    text = RE_HTML_COMMENT.sub("", text)
    text = RE_LINE_COMMENT.sub("", text)
    return text


def _slug_for(path: Path) -> str:
    """Derive a slug like 'finance__dashboard' from templates/finance/dashboard.html."""
    rel = path.relative_to(TEMPLATES_ROOT)
    parts = list(rel.with_suffix("").parts)
    return "__".join(parts).replace(" ", "-").lower()


def _find_inline_script_spans(text: str) -> list[tuple[int, int, str]]:
    """Return list of (open_start, close_end, body) for each inline <script>."""
    out: list[tuple[int, int, str]] = []
    for m in RE_SCRIPT_OPEN.finditer(text):
        open_end = m.end()
        # Look for matching </script> from open_end forward.
        close_idx = text.lower().find("</script>", open_end)
        if close_idx == -1:
            continue
        body = text[open_end:close_idx]
        out.append((m.start(), close_idx + len("</script>"), body))
    return out


def _classify(body: str) -> str:
    """Return 'PURE_JS' or 'DJANGO_INTERPOLATED'."""
    return "DJANGO_INTERPOLATED" if RE_DJANGO_TAG.search(body) else "PURE_JS"


def _ensure_load_static(text: str) -> tuple[str, bool]:
    """Insert ``{% load static %}`` if not already present. Returns (new_text, inserted)."""
    if RE_LOAD_STATIC.search(text):
        return text, False
    # Insert after the first line (typically {% extends %}) or at top.
    m = re.search(r"\{%\s*extends[^%]*%\}", text, re.IGNORECASE)
    if m:
        insert_at = m.end()
        return text[:insert_at] + "\n{% load static %}" + text[insert_at:], True
    return "{% load static %}\n" + text, True


def _externalize_pure_js(
    path: Path,
    text: str,
    spans: list[tuple[int, int, str]],
    write: bool,
) -> tuple[str, list[Path]]:
    """Replace every PURE_JS inline span with an external <script src=...>.

    Returns (new_text, list_of_written_static_paths).
    """
    slug_base = _slug_for(path)
    written_static: list[Path] = []

    # Process spans in reverse order so indices remain valid as we mutate text.
    new_text = text
    pure_indices = [i for i, (_, _, body) in enumerate(spans) if _classify(body) == "PURE_JS"]
    for n_th, idx in enumerate(reversed(pure_indices)):
        s, e, body = spans[idx]
        # Stable name per file: first PURE block uses base slug, subsequent ones get -2, -3 …
        ordinal = len(pure_indices) - n_th  # 1-based original ordinal
        suffix = "" if ordinal == 1 else f"-{ordinal}"
        out_name = f"{slug_base}{suffix}.js"
        out_path = OUT_DIR / out_name

        replacement = (
            f'<script src="{{% static \'js/_pages/{out_name}\' %}}"></script>'
        )
        if write:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path.write_text(body.strip("\n") + "\n", encoding="utf-8")
        written_static.append(out_path)
        new_text = new_text[:s] + replacement + new_text[e:]

    if pure_indices and write:
        new_text, _inserted = _ensure_load_static(new_text)

    return new_text, written_static


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    parser.add_argument("--only", type=str, default="", help="Comma-separated dir filter.")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many files (0 = no limit).")
    args = parser.parse_args()

    only = {p.strip().lower() for p in args.only.split(",") if p.strip()} or None

    pure_files = 0
    django_files = 0
    pure_blocks = 0
    django_blocks = 0
    written_files = 0
    written_statics = 0
    converted_paths: list[str] = []
    deferred_paths: list[str] = []

    candidates: list[Path] = []
    for p in TEMPLATES_ROOT.rglob("*.html"):
        if _is_partial(p):
            continue
        if only:
            rel_parts = {x.lower() for x in p.relative_to(TEMPLATES_ROOT).parts}
            if not (rel_parts & only):
                continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _strip_comments(raw)
        spans = _find_inline_script_spans(text)
        if not spans:
            continue
        candidates.append(p)

    if args.limit:
        candidates = candidates[: args.limit]

    for p in candidates:
        raw = p.read_text(encoding="utf-8", errors="replace")
        # Operate on raw (so we keep comments) — but recompute spans against raw too.
        spans = _find_inline_script_spans(raw)
        kinds = [_classify(body) for _, _, body in spans]
        n_pure = sum(1 for k in kinds if k == "PURE_JS")
        n_dj = sum(1 for k in kinds if k == "DJANGO_INTERPOLATED")
        pure_blocks += n_pure
        django_blocks += n_dj
        if n_pure:
            pure_files += 1
        if n_dj and not n_pure:
            django_files += 1

        if n_pure == 0:
            deferred_paths.append(str(p.relative_to(ROOT)))
            continue

        new_text, written = _externalize_pure_js(p, raw, spans, write=args.apply)
        if args.apply and new_text != raw:
            p.write_text(new_text, encoding="utf-8")
            written_files += 1
            written_statics += len(written)
        converted_paths.append(str(p.relative_to(ROOT)))

    print("externalize_inline_scripts:")
    print(f"  candidates with inline scripts: {len(candidates)}")
    print(f"  files that have PURE_JS blocks: {pure_files}")
    print(f"  files with ONLY Django-interp blocks: {django_files}")
    print(f"  total PURE_JS blocks:           {pure_blocks}")
    print(f"  total Django-interp blocks:     {django_blocks}")
    if args.apply:
        print(f"  templates rewritten:            {written_files}")
        print(f"  static .js files written:       {written_statics}")
    else:
        print("  (dry-run — no files written)")

    if deferred_paths:
        print(f"\n  Deferred (Django-interp only) — {len(deferred_paths)} file(s) need data-island conversion:")
        for p in deferred_paths[:20]:
            print(f"    - {p}")
        if len(deferred_paths) > 20:
            print(f"    … and {len(deferred_paths)-20} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())
