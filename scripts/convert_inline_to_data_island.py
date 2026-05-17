"""convert_inline_to_data_island — convert Django-interpolated inline scripts
to a JSON data island + external JS reader.

For each inline ``<script>`` whose body contains ``{% url %}``, ``{% trans %}``,
or ``{{ var }}`` references:

1. Identify each Django tag and assign it a stable JSON key (``url_a_b``,
   ``trans_n``, ``ctx_var_x``).
2. Generate a JSON data island ``<script type="application/json" id="page-data-<slug>-<n>">{...}</script>``
   that emits the resolved values server-side.
3. Generate an external JS file ``static/js/_pages/<slug>-<n>.js`` containing
   the original script body with each Django tag replaced by
   ``window.__RMC_PAGE_DATA__["<slug>-<n>"].<key>``.
4. Replace the inline ``<script>`` with the data island + an external
   ``<script src=...>`` pair.

Conservative scope: skips bodies that contain ``{% if %}`` / ``{% for %}`` /
nested control flow (those need page-by-page understanding to extract reliably).

Defaults to dry-run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates"
OUT_DIR = ROOT / "static" / "js" / "_pages"

RE_SCRIPT_OPEN = re.compile(
    r'<script(?![^>]*\bsrc=)(?![^>]*\btype=["\'](?:application/(?:json|ld\+json)|importmap)["\'])([^>]*)>',
    re.IGNORECASE,
)
RE_DJANGO_TAG = re.compile(r"\{\{|\{%")
RE_LOAD_STATIC = re.compile(r"\{%\s*load[^%]*\bstatic\b[^%]*%\}", re.IGNORECASE)
RE_DJANGO_COMMENT_BLOCK = re.compile(
    r"\{%\s*comment\s*(?:\".*?\")?\s*%\}.*?\{%\s*endcomment\s*%\}",
    re.IGNORECASE | re.DOTALL,
)
RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
RE_LINE_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)

# Each captures the tag in group(1) for the named-tag forms, and the variable
# expression in group(1) for {{ … }}.
RE_URL_TAG = re.compile(r"\{%\s*url\s+([^%]+?)\s*%\}", re.IGNORECASE)
RE_TRANS_TAG = re.compile(r"\{%\s*trans\s+(['\"][^'\"]+['\"])\s*%\}", re.IGNORECASE)
RE_VAR_TAG = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
# Disqualifying — bodies with these need manual review.
RE_COMPLEX_TAGS = re.compile(
    r"\{%\s*(if|else|elif|endif|for|endfor|with|endwith|include|extends|block|endblock|spaceless|endspaceless|comment|endcomment|cycle|firstof|regroup|now|widthratio|csrf_token)\b",
    re.IGNORECASE,
)

SKIP_DIR_PARTS_FOR_EXTERNALISATION = {"admin", "unfold"}


def _is_partial(path: Path) -> bool:
    return any(p.lower() in SKIP_DIR_PARTS_FOR_EXTERNALISATION for p in path.parts)


def _strip_comments(text: str) -> str:
    text = RE_DJANGO_COMMENT_BLOCK.sub("", text)
    text = RE_HTML_COMMENT.sub("", text)
    text = RE_LINE_COMMENT.sub("", text)
    return text


def _slug_for(path: Path) -> str:
    rel = path.relative_to(TEMPLATES_ROOT)
    parts = list(rel.with_suffix("").parts)
    return "__".join(parts).replace(" ", "-").lower()


def _find_inline_script_spans(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for m in RE_SCRIPT_OPEN.finditer(text):
        open_end = m.end()
        close_idx = text.lower().find("</script>", open_end)
        if close_idx == -1:
            continue
        body = text[open_end:close_idx]
        out.append((m.start(), close_idx + len("</script>"), body))
    return out


def _safe_to_convert(body: str) -> bool:
    """Skip bodies that need control-flow understanding."""
    return not RE_COMPLEX_TAGS.search(body)


def _slug_key(s: str) -> str:
    """Produce a JS-identifier-safe key from an arbitrary expression string."""
    s = s.strip().strip("'\"")
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s.lower() or "value"


def _build_island_and_js(body: str, page_data_key: str) -> tuple[str, str]:
    """Convert a script body into (json_payload_lines, external_js_body).

    The json_payload_lines are inner lines suitable for placing inside the
    data-island ``<script type="application/json">{...}</script>``.
    The external_js_body is the original body with each Django tag replaced
    by a lookup into ``window.__RMC_PAGE_DATA__[page_data_key]``.
    """
    payload: list[tuple[str, str]] = []
    seen_keys: set[str] = set()

    def _next_unique_key(base: str) -> str:
        if base not in seen_keys:
            seen_keys.add(base)
            return base
        i = 2
        while f"{base}_{i}" in seen_keys:
            i += 1
        k = f"{base}_{i}"
        seen_keys.add(k)
        return k

    # Pass 1: {% url ... %}
    def _url_repl(m: re.Match) -> str:
        expr = m.group(1).strip()
        # Use the first identifier as the key seed
        first_token = expr.split()[0].strip("'\"")
        key = _next_unique_key("url_" + _slug_key(first_token))
        # Server-side payload entry as raw Django expression
        payload.append((key, "{% " + "url " + expr + " %}"))
        return f'(window.__RMC_PAGE_DATA__["{page_data_key}"]||{{}})["{key}"]'

    body = RE_URL_TAG.sub(_url_repl, body)

    # Pass 2: {% trans "..." %}
    def _trans_repl(m: re.Match) -> str:
        literal = m.group(1).strip()
        key = _next_unique_key("trans_" + _slug_key(literal))
        payload.append((key, "{% " + "trans " + literal + " %}"))
        return f'(window.__RMC_PAGE_DATA__["{page_data_key}"]||{{}})["{key}"]'

    body = RE_TRANS_TAG.sub(_trans_repl, body)

    # Pass 3: {{ var }}
    def _var_repl(m: re.Match) -> str:
        expr = m.group(1).strip()
        key = _next_unique_key("var_" + _slug_key(expr))
        payload.append((key, "{{ " + expr + " }}"))
        return f'(window.__RMC_PAGE_DATA__["{page_data_key}"]||{{}})["{key}"]'

    body = RE_VAR_TAG.sub(_var_repl, body)

    # Guard: refuse to emit output where a property-read expression ended up
    # wrapped in surrounding string-literal quotes. This happens when the
    # original inline script had a Django tag *inside* a JS string literal —
    # the regex substitution preserved the outer quotes and turned the
    # expression into a literal string. That broke ~40 page-JS files before
    # this guard was added; manual unwrap fix lives in
    # scripts/fix_data_island_string_literals.py. Refuse to write any new
    # broken output and surface the line so a human can rewrite it.
    if re.search(
        r'[\"\']\(window\.__RMC_PAGE_DATA__\[\"[^\"]+\"\]\|\|\{\}\)\[\"[^\"]+\"\][\"\']',
        body,
    ):
        raise RuntimeError(
            "Cannot externalise this inline script: a Django tag sits inside "
            "a JS string literal, which would emit a literal-string expression "
            "(see scripts/fix_data_island_string_literals.py for the bug class). "
            "Rewrite the inline source to read the value into a variable first, "
            "e.g. const X = '{{ var|escapejs }}'; then use X in the string."
        )

    # Build payload lines
    lines = []
    for k, v in payload:
        # Quote the value as a JSON string. Django's escapejs filter is right
        # for *string* values; for {{ var }} values the operator can later
        # adjust if the value is non-string.
        rendered = v
        if v.startswith("{% url"):
            rendered = '"' + v + '"'
        elif v.startswith("{% trans"):
            rendered = '"' + v + '"'
        else:
            # {{ var }} — cast to string, escape for JS in JSON
            rendered = '"{{ ' + v[3:-3].strip() + '|escapejs }}"'
        lines.append(f'  "{k}": {rendered}')

    json_body = "{\n" + ",\n".join(lines) + "\n}" if lines else "{}"
    return json_body, body


def _ensure_load_static(text: str) -> str:
    if RE_LOAD_STATIC.search(text):
        return text
    m = re.search(r"\{%\s*extends[^%]*%\}", text, re.IGNORECASE)
    if m:
        return text[: m.end()] + "\n{% load static %}" + text[m.end():]
    return "{% load static %}\n" + text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run).")
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many files.")
    args = parser.parse_args()

    candidates: list[Path] = []
    for p in TEMPLATES_ROOT.rglob("*.html"):
        if _is_partial(p):
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        spans = _find_inline_script_spans(_strip_comments(raw))
        if not spans:
            continue
        candidates.append(p)

    if args.limit:
        candidates = candidates[: args.limit]

    converted = 0
    skipped_complex = 0
    written_js = 0

    for p in candidates:
        raw = p.read_text(encoding="utf-8", errors="replace")
        spans = _find_inline_script_spans(raw)
        if not spans:
            continue

        slug = _slug_for(p)
        new_text = raw
        wrote_any = False

        # Process spans in REVERSE order so prior offsets stay valid.
        for ordinal, (s, e, body) in enumerate(reversed(spans), start=1):
            if not RE_DJANGO_TAG.search(body):
                # Pure JS — already handled by the prior helper; skip here.
                continue
            if not _safe_to_convert(body):
                skipped_complex += 1
                continue

            # Block index from start, not reversed:
            block_idx = len(spans) - ordinal + 1
            page_data_key = f"{slug}-{block_idx}"
            out_name = f"{slug}-{block_idx}.js"
            out_path = OUT_DIR / out_name

            json_body, external_js = _build_island_and_js(body, page_data_key)

            replacement = (
                f'<script type="application/json" id="page-data-{page_data_key}">'
                f'{{% include "_pages/{out_name}.json" %}}'
                f'</script>'
                f'<script>(function(){{var el=document.getElementById("page-data-{page_data_key}");'
                f'window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{{}};'
                f'if(el){{try{{window.__RMC_PAGE_DATA__["{page_data_key}"]=JSON.parse(el.textContent||"{{}}")}}catch(_e){{}}}}}}());</script>'
                f'<script src="{{% static \'_pages/{out_name}\' %}}"></script>'
            )
            # Bah — ".json" as a sibling include creates Django-template-rendering complexity.
            # Simpler: emit the JSON inline directly into the data island (still CSP-safe — JSON is data).
            replacement = (
                f'<script type="application/json" id="page-data-{page_data_key}">{json_body}</script>'
                f'<script src="{{% static \'_pages/{out_name}\' %}}"></script>'
            )
            new_text = new_text[:s] + replacement + new_text[e:]
            wrote_any = True

            if args.apply:
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                # Wrap the body in a tiny IIFE that loads the page-data first.
                wrapped = (
                    "(function(){\n"
                    f'  var pageDataEl=document.getElementById("page-data-{page_data_key}");\n'
                    "  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};\n"
                    "  if(pageDataEl){try{window.__RMC_PAGE_DATA__"
                    f'["{page_data_key}"]'
                    "=JSON.parse(pageDataEl.textContent||\"{}\")}catch(_e){}}\n"
                    + external_js.strip("\n")
                    + "\n})();\n"
                )
                out_path.write_text(wrapped, encoding="utf-8")
                written_js += 1

        if wrote_any and args.apply:
            new_text = _ensure_load_static(new_text)
            p.write_text(new_text, encoding="utf-8")
            converted += 1

    print(f"convert_inline_to_data_island:")
    print(f"  candidate files:       {len(candidates)}")
    print(f"  converted (or would):  {converted}")
    print(f"  static .js files:      {written_js}")
    print(f"  skipped (complex):     {skipped_complex}")
    if not args.apply:
        print("  (dry-run — re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
