#!/usr/bin/env python3
"""Which pages are long for the reason the Sync Center was long?

WHY THIS EXISTS. The Sync Center was rebuilt on 2026-08-21 because it had grown to six
stacked cards, fifteen counter tiles, twenty-two always-on explanatory paragraphs and
thirteen forms. None of that was wrong on its own -- every paragraph had been written
because somebody was confused, and every tile answered a real question. What was never
done is make any of it CONDITIONAL, and what nobody noticed is that three of the panels
had each been built to stand alone, so each re-derived what its neighbour already showed.
Five separate facts rendered twice, and one of those pairs could legitimately DISAGREE
(the next occurrence of a schedule RULE vs the next moment CADENCE was due).

That is not a Sync Center problem. It is what happens to any operational page that
accretes panels over eighteen months, and this repo has a lot of them. So rather than fix
one page and move on, this measures the whole platform for the same four symptoms and
prints a ranked list.

WHAT IT MEASURES, per rendered page (a template that extends a shell), following its
{% include %} tree so a page built out of partials is not scored as if it were empty:

  1. DENSITY      -- cards/sections, counter tiles, forms, tables, total expanded lines.
  2. PERMANENT    -- explanatory paragraphs that render unconditionally, i.e. NOT inside
     TEACHING       an {% if %}. This is the one that made the Sync Center long: a 502
                    diagnosis rendering on a page reporting twelve clean cycles.
  3. DUPLICATE    -- the same `data-*` hook, or the same {{ variable }}, rendered more
     FACTS          than once in one page. Two renderings of one fact is where "the
                    page is long" and "the page contradicts itself" meet.
  4. DOUBLE       -- two or more scripts on one page that both poll. The Sync Center had
     POLLING        exactly this: a fixed 3s setInterval in one file and an adaptive
                    visibility-aware timer in another, hitting the same endpoint and
                    painting different halves of it.

IT IS A REPORT, NOT A GATE. There is no baseline and no exit-1: "this page has 12 tiles"
is not a defect, it is a candidate for the same treatment. Density is a judgement call and
a scanner that pretended otherwise would be ignored. `--json` for the machine-readable
form, `--top N` to bound the report.

Stdlib only, so it runs anywhere without Django.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOTS = [ROOT / "templates"]

# A "page" is a template that extends a shell. Everything else is a partial, and a
# partial's numbers belong to whatever page includes it.
_SHELLS = (
    "base.html",
    "portal_base.html",
    "backend_base.html",
    "control_plane_skeleton.html",
    "control_plane_base.html",
    "marketing/base_marketing.html",
    "admin/base_site.html",
)

_EXTENDS = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']')
_INCLUDE = re.compile(r'{%\s*include\s+["\']([^"\']+)["\']')
_COMMENT_BLOCK = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.S)
_HASH_COMMENT = re.compile(r"{#.*?#}", re.S)
_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)

# Cards and sections: the containers a reader perceives as "another panel to scroll past".
_CARD = re.compile(r'class="[^"]*\b(?:card|rmc-command-panel|rmc-sc-band)\b[^"]*"')
_SECTION = re.compile(r"<section\b")
_FORM = re.compile(r"<form\b")
_TABLE = re.compile(r"<table\b")

# A counter tile: a small uppercase label sitting above a number. Matched by the two
# grammars this codebase actually uses for them.
_TILE = re.compile(
    r'class="[^"]*\b(?:text-uppercase|rmc-sc-figure__label|rmc-metric__label'
    r"|rmc-stat__label|cp-metric__label)\b[^\"]*\"",
)

# An explanatory paragraph: prose in a muted/small class. Distinct from a label.
_EXPLAINER = re.compile(
    r'<p\b[^>]*class="[^"]*\b(?:small|text-muted|text-body-secondary|helptext'
    r"|form-text|rmc-sc-band__note)\b[^\"]*\"[^>]*>",
)

_IF_OPEN = re.compile(r"{%\s*if\b")
_IF_CLOSE = re.compile(r"{%\s*endif\s*%}")

_DATA_HOOK = re.compile(r'\b(data-rmc-[a-z0-9-]+)(?:="[^"]*")?')
_VARIABLE = re.compile(r"{{\s*([a-zA-Z_][\w.]*)\s*}}")
_STATIC_JS = re.compile(r"{%\s*static\s+['\"]([^'\"]*\.js)['\"]")
#: A POLLER re-arms itself. A script that fetches once on load is not one, and counting
#: it turned "two pollers on this page" -- a real bug the Sync Center had -- into a list
#: of sixty-six pages that merely use fetch.
_POLL_TIMER = re.compile(r"setInterval\s*\(|setTimeout\s*\(\s*poll|schedule\s*\(\s*next")
_POLL_FETCH = re.compile(r"fetch\s*\(|XMLHttpRequest|htmx")

#: Variables so ubiquitous that repeating them says nothing about duplication.
_VARIABLE_NOISE = {
    "block.super",
    "csrf_token",
    "forloop.counter",
    "forloop.counter0",
    "school.name",
    "request.user",
    "user.username",
    "STATIC_URL",
}

#: A hook only counts as a duplicated FACT if some JavaScript writes a value into it.
#: Without this the scan drowns: `data-rmc-scroll-policy` appears 53 times on the admin
#: dashboard because it is a structural marker on every scrollable container, and
#: `data-rmc-row-title` appears once per row by design. Neither is a fact rendered twice,
#: and a report where the real finding sits under fifty of those is a report nobody reads
#: -- the same noise-burial that gets a gate switched off.
_JS_WRITE = re.compile(
    r"(?:textContent|innerText|innerHTML|\.value)\s*=|setText\s*\(|setAttribute\s*\("
)
_JS_SELECTOR = re.compile(r'\[(data-rmc-[a-z0-9-]+)')

_MAX_INCLUDE_DEPTH = 6  # magic-number-allow: include nesting past this is a cycle
#: Above this, a repeated hook is structure rather than a duplicated fact. See the
#: note in _duplicate_facts -- this single number is what separates signal from the
#: fifty-three-occurrence markers that made the first version of this scan useless.
_DUPLICATE_FACT_CEILING = 4  # magic-number-allow: a fact shown 5+ times is a marker


def _strip(text: str) -> str:
    """Remove comments, scripts and styles before measuring the markup."""
    text = _COMMENT_BLOCK.sub("", text)
    text = _HASH_COMMENT.sub("", text)
    text = _SCRIPT_BLOCK.sub("", text)
    return _STYLE_BLOCK.sub("", text)


def _resolve(name: str) -> Path | None:
    for base in TEMPLATE_ROOTS:
        candidate = base / name
        if candidate.is_file():
            return candidate
    for app_templates in sorted(ROOT.glob("apps/*/templates")):
        candidate = app_templates / name
        if candidate.is_file():
            return candidate
    return None


def _expand(path: Path, depth: int = 0, seen: set | None = None) -> str:
    """The page as a reader meets it: its own markup plus everything it includes."""
    seen = seen if seen is not None else set()
    if depth > _MAX_INCLUDE_DEPTH or path in seen:
        return ""
    seen.add(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    parts = [text]
    for name in _INCLUDE.findall(text):
        if "{" in name:  # a variable include; cannot be resolved statically
            continue
        target = _resolve(name)
        if target is not None:
            parts.append(_expand(target, depth + 1, seen))
    return "\n".join(parts)


def _unconditional_explainers(text: str) -> int:
    """Explanatory paragraphs that render on EVERY visit.

    An explainer inside an {% if %} is conditional teaching and is exactly what the
    rebuild moved toward, so it is not counted. Depth is tracked by scanning forward
    through the tags rather than parsing, which is enough: over-counting one branch of an
    {% else %} would only ever make a page look slightly worse than it is, and this is a
    report, not a gate.
    """
    depth = 0
    count = 0
    for token in re.finditer(r"{%\s*if\b|{%\s*endif\s*%}|<p\b[^>]*>", text):
        chunk = token.group(0)
        if _IF_OPEN.match(chunk):
            depth += 1
        elif _IF_CLOSE.match(chunk):
            depth = max(0, depth - 1)
        elif depth == 0 and _EXPLAINER.match(chunk):
            count += 1
    return count


def _js_written_hooks() -> set:
    """Every data-rmc hook that some shipped JavaScript paints a value into.

    Computed once from static/js. A hook nothing writes to is structure, not a fact.
    """
    hooks: set = set()
    js_root = ROOT / "static" / "js"
    if not js_root.is_dir():
        return hooks
    for js in js_root.rglob("*.js"):
        try:
            source = js.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _JS_WRITE.search(source):
            continue
        hooks.update(_JS_SELECTOR.findall(source))
    return hooks


_WRITTEN_HOOKS: set = set()


def _duplicate_facts(text: str) -> list:
    """Hooks and variables rendered more than once on one page."""
    findings = []

    # COUNT IS THE DISCRIMINATOR, and it is the only one that survives contact with the
    # real tree. "Is this hook written by JS" was not enough: `data-rmc-scroll-policy`
    # and `data-rmc-section-anchor` pass it and appear 53 and 14 times on one page,
    # because they mark STRUCTURE -- every scrollable container, every anchored section.
    # Nothing legitimately displays ONE value fourteen times. A fact rendered twice is 2;
    # rendered three times, 3. Past `_DUPLICATE_FACT_CEILING` the thing being counted is
    # a marker, not a fact, and reporting it buries the real finding under the noise that
    # gets a report ignored.
    hooks = Counter(
        hook for hook in _DATA_HOOK.findall(text) if hook in _WRITTEN_HOOKS
    )
    for hook, n in hooks.items():
        if 1 < n <= _DUPLICATE_FACT_CEILING:
            findings.append({"kind": "hook", "name": hook, "count": n})

    # A variable repeated outside a {% for %} is the same value drawn twice. Loop bodies
    # are excluded wholesale rather than tracked, because a variable inside a loop is
    # SUPPOSED to repeat.
    outside_loops = re.sub(r"{%\s*for\b.*?{%\s*endfor\s*%}", "", text, flags=re.S)
    # `.id` / `.pk` / `.slug` repeat because they build URLs, not because a value is
    # shown twice. Counting them would put every detail page at the top of the report for
    # doing something entirely correct.
    variables = Counter(
        name
        for name in _VARIABLE.findall(outside_loops)
        if name not in _VARIABLE_NOISE
        and "." in name
        and not name.endswith((".id", ".pk", ".slug", ".count", ".url"))
    )
    for name, n in variables.items():
        if n > 1:
            findings.append({"kind": "variable", "name": name, "count": n})

    return sorted(findings, key=lambda f: -f["count"])


def _pollers(path: Path, text: str) -> list:
    """Scripts loaded by this page that poll. Two is the Sync Center's old bug."""
    out = []
    for rel in set(_STATIC_JS.findall(text)):
        js = ROOT / "static" / rel
        if not js.is_file():
            continue
        try:
            source = js.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _POLL_TIMER.search(source) and _POLL_FETCH.search(source):
            out.append(rel)
    return sorted(out)


def _score(row: dict) -> int:
    """A rough ranking, weighted toward the symptoms that actually made a page long.

    Permanent teaching and duplicate facts are weighted above raw size on purpose: a big
    page that says each thing once is a big page, while a small page that contradicts
    itself is a bug.
    """
    return (
        row["explainers"] * 3
        + len(row["duplicates"]) * 4
        + row["tiles"] * 2
        + row["cards"]
        + (10 if len(row["pollers"]) > 1 else 0)
    )


def collect() -> list:
    global _WRITTEN_HOOKS
    _WRITTEN_HOOKS = _js_written_hooks()
    pages = []
    for base in TEMPLATE_ROOTS:
        for path in sorted(base.rglob("*.html")):
            try:
                head = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            extends = _EXTENDS.search(head)
            if not extends or not extends.group(1).endswith(_SHELLS):
                continue
            expanded = _strip(_expand(path))
            row = {
                "template": str(path.relative_to(ROOT)).replace("\\", "/"),
                "lines": expanded.count("\n") + 1,
                "cards": len(_CARD.findall(expanded)) + len(_SECTION.findall(expanded)),
                "tiles": len(_TILE.findall(expanded)),
                "forms": len(_FORM.findall(expanded)),
                "tables": len(_TABLE.findall(expanded)),
                "explainers": _unconditional_explainers(expanded),
                "duplicates": _duplicate_facts(expanded),
                "pollers": _pollers(path, _expand(path)),
            }
            row["score"] = _score(row)
            pages.append(row)
    return sorted(pages, key=lambda r: -r["score"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--top", type=int, default=25, help="how many pages to print")
    args = parser.parse_args()

    pages = collect()
    if args.json:
        print(json.dumps({"pages": pages}, indent=2))
        return 0

    print(f"page-density scan: {len(pages)} rendered pages\n")
    header = f"{'score':>5}  {'cards':>5} {'tiles':>5} {'expl':>5} {'dupes':>5} {'forms':>5} {'lines':>6}  template"
    print(header)
    print("-" * len(header))
    for row in pages[: args.top]:
        print(
            f"{row['score']:>5}  {row['cards']:>5} {row['tiles']:>5} "
            f"{row['explainers']:>5} {len(row['duplicates']):>5} {row['forms']:>5} "
            f"{row['lines']:>6}  {row['template']}"
        )

    doubles = [r for r in pages if len(r["pollers"]) > 1]
    if doubles:
        print(f"\npages loading more than one polling script: {len(doubles)}")
        for row in doubles[:12]:
            print(f"  {row['template']}")
            for js in row["pollers"]:
                print(f"      {js}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
