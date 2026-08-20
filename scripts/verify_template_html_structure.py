#!/usr/bin/env python
"""Every shipped template must close the elements it opens.

WHY. An unclosed ``<div>`` does not raise, does not log, and does not fail a test. The
template compiles, the view returns 200, and the browser silently repairs the document by
auto-closing the element at its parent's boundary -- which quietly reparents everything
that follows into a container it was never meant to be inside. Found this way on
2026-08-20, all live on served pages:

  * ``accounts/backend_dashboard.html`` -- ``#section-today`` never closed, so the two
    sibling sections the sticky section-nav scrolls between became its children and the
    page container was left open at ``{% endblock %}``;
  * ``accounts/profile.html`` -- a surplus ``</div>`` shut ``.rmc-account-layout-grid``
    early, evicting the Badges, Finance and Console cards from the balanced grid;
  * ``emis/dashboard.html`` -- "Recent Exports" fell outside ``.emis-dashboard-widgets``,
    losing the ``.emis-dashboard-widgets .card`` styling that is a descendant selector;
  * ``marketplace/{signup_review_queue,webhook_endpoints}.html`` -- a ``</motion>`` tag,
    an element that does not exist and that browsers discard, standing in for ``</div>``;
  * ``compliance/data_rights_queue.html`` -- an "Actions" disclosure injected into the
    ``{% empty %}`` placeholder row, opened and never closed, so the empty state alone
    emitted broken markup;
  * ``siteconfig/report_library.html`` -- a ``<details>`` opened once per row in a file
    containing no ``</details>`` at all.

HOW. Django templates are not HTML until they are rendered, so an HTML parser cannot be
pointed at them directly: ``{% if %}`` branches are mutually exclusive, and the common
idiom ``{% if x %}<div>{% endif %} ... {% if x %}</div>{% endif %}`` is correct while
being textually unbalanced. This walks the template instead and measures every branch
SEPARATELY -- an ``{% if %}`` contributes the delta its branches agree on, and branches
that disagree are the finding. ``{% comment %}`` is stripped BEFORE ``<script>``,
``<style>`` and ``<!-- -->``, because a template that merely mentions "<style>" in prose
inside a comment would otherwise start an HTML match that swallows the
``{% endcomment %}`` and, with it, real markup much further down. That ordering bug
produced a false positive on four email templates while this gate was being written.

THREE CHECKS:
  unknown-close-tag  ``</foo>`` where foo is not an HTML or SVG element. Zero tolerance
                     and not waivable -- ``</motion>`` is never intentional. Hyphenated
                     and namespaced names are allowed: those are custom elements.
  div-balance        net ``<div>`` delta must be zero.
  container-balance  same, for block containers that require an explicit closing tag.

Deliberately unbalanced partials -- the ``_open``/``_close`` pairs that wrap a layout
across two files -- carry ``{# html-structure-allow: reason #}``. The marker waives the
two balance checks for that file and requires a reason, so the coupling is stated in the
file rather than remembered.

Exit codes: 0 clean, 1 one or more findings.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = ("templates", "apps")

SKIP_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "staticfiles", "dist", "build", "coverage",
}

ALLOW_MARKER = re.compile(r"\{#\s*html-structure-allow:\s*(?P<reason>[^#]{8,})#\}")

# Block containers that require an explicit closing tag. Void elements (<br>, <img>) and
# elements whose end tag is OPTIONAL in the HTML parser (<li>, <td>, <tr>, <p>, <option>,
# <thead>, <tfoot>) are deliberately excluded: omitting those is legal HTML, so flagging
# them would be noise, and noise is how a gate gets ignored.
CONTAINER_TAGS = (
    "details", "form", "section", "aside", "table", "tbody", "fieldset",
    "figure", "dialog", "main", "nav", "article", "header", "footer",
    "select", "textarea", "summary", "label", "button", "ul", "ol",
)

HTML_TAGS = set("""
a abbr address area article aside audio b base bdi bdo blockquote body br button canvas
caption cite code col colgroup data datalist dd del details dfn dialog div dl dt em embed
fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 head header hgroup hr html i
iframe img input ins kbd label legend li link main map mark menu meta meter nav noscript
object ol optgroup option output p param picture pre progress q rp rt ruby s samp script
search section select slot small source span strong style sub summary sup table tbody td
template textarea tfoot th thead time title tr track u ul var video wbr
""".split())

# SVG ships inline throughout this tree (icons, sparklines, the world map). Names are
# lowercased before lookup because templates author them in camelCase.
SVG_TAGS = set("""
svg path circle rect ellipse line polyline polygon g defs use symbol desc marker mask
pattern clippath lineargradient radialgradient stop text tspan textpath foreignobject
filter feblend fecolormatrix fecomponenttransfer fecomposite feconvolvematrix
fediffuselighting fedisplacementmap fedropshadow feflood fefunca fefuncb fefuncg fefuncr
fegaussianblur feimage femerge femergenode femorphology feoffset fepointlight
fespecularlighting fespotlight fetile feturbulence animate animatemotion animatetransform
set mpath switch image view
""".split())

KNOWN_TAGS = HTML_TAGS | SVG_TAGS

TAG_RE = re.compile(r"\{%\s*(\w+)([^%]*?)%\}", re.S)
CLOSE_TAG_RE = re.compile(r"</([A-Za-z][\w:.-]*)\s*>")

BRANCHERS = {"if": ("elif", "else"), "ifchanged": ("else",)}
LOOPERS = {"for": ("empty",)}
CLOSERS = {
    "if": "endif", "ifchanged": "endifchanged", "for": "endfor",
    "block": "endblock", "with": "endwith", "spaceless": "endspaceless",
    "autoescape": "endautoescape", "blocktrans": "endblocktrans",
    "blocktranslate": "endblocktranslate", "localize": "endlocalize",
    "filter": "endfilter", "cache": "endcache",
}


def _blank(match):
    """Replace a region with its own newlines so reported line numbers stay true."""
    return "\n" * match.group(0).count("\n")


def strip_noise(src):
    """Blank every region that is not template-rendered markup.

    ORDER MATTERS, and getting it wrong is silent. Django comments go first because the
    server removes them before any HTML exists; strip ``<style>`` first instead and a
    ``{% comment %}`` whose prose mentions "<style>" starts a match that eats the
    ``{% endcomment %}`` and every tag between there and the next ``</style>``.
    """
    src = re.sub(r"\{#.*?#\}", _blank, src, flags=re.S)
    src = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", _blank, src,
                 flags=re.S | re.I)
    src = re.sub(r"\{%\s*verbatim\s*%\}.*?\{%\s*endverbatim\s*%\}", _blank, src,
                 flags=re.S | re.I)
    src = re.sub(r"<script\b.*?</script\s*>", _blank, src, flags=re.S | re.I)
    src = re.sub(r"<style\b.*?</style\s*>", _blank, src, flags=re.S | re.I)
    src = re.sub(r"<!--.*?-->", _blank, src, flags=re.S)
    return src


def line_of(src, offset):
    return src.count("\n", 0, offset) + 1


class BranchAwareCounter:
    """Net delta of one tag across a template, measuring {% if %} branches separately."""

    def __init__(self, src, tag):
        self.src = src
        self.tag = tag
        self.open_re = re.compile(r"<%s\b(?![^>]*/>)" % tag, re.I)
        self.close_re = re.compile(r"</%s\s*>" % tag, re.I)
        # Kept apart on purpose. A loop body that changes depth is a defect on its own
        # merits. A disagreeing {% if %} is NOT: the wrapper idiom
        # {% if x %}<a>{% else %}<div>{% endif %} ... {% if x %}</a>{% else %}</div>{% endif %}
        # is correct and common here, and its branches disagree by design. Those are
        # reported only when the file is ALSO net-unbalanced, where they say where to look.
        self.branch_findings = []
        self.loop_findings = []
        self.toks = self._tokenize(src)
        self.i = 0

    @staticmethod
    def _tokenize(src):
        pos, out = 0, []
        for m in TAG_RE.finditer(src):
            if m.start() > pos:
                out.append(("text", src[pos:m.start()], pos))
            out.append(("tag", m.group(1).lower(), m.start()))
            pos = m.end()
        if pos < len(src):
            out.append(("text", src[pos:], pos))
        return out

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def parse(self, until=None):
        delta = 0
        while self.i < len(self.toks):
            kind, val, off = self.toks[self.i]
            if kind == "text":
                delta += len(self.open_re.findall(val))
                delta -= len(self.close_re.findall(val))
                self.i += 1
                continue
            if until and val in until:
                return delta
            self.i += 1
            if val in BRANCHERS:
                delta += self._branching(val, off)
            elif val in LOOPERS:
                delta += self._loop(val, off)
            elif val in CLOSERS:
                end = CLOSERS[val]
                inner = self.parse({end})
                if self._peek() and self._peek()[1] == end:
                    self.i += 1
                delta += inner
        return delta

    def _branching(self, tag, off):
        end = CLOSERS[tag]
        stops = set(BRANCHERS[tag]) | {end}
        deltas = [self.parse(stops)]
        while self._peek() and self._peek()[1] in BRANCHERS[tag]:
            self.i += 1
            deltas.append(self.parse(stops))
        if self._peek() and self._peek()[1] == end:
            self.i += 1
        if len(set(deltas)) > 1:
            self.branch_findings.append(
                "line %d: {%% %s %%} branches disagree on <%s> nesting (deltas %r)"
                % (line_of(self.src, off), tag, self.tag, deltas)
            )
        return max(set(deltas), key=deltas.count)

    def _loop(self, tag, off):
        end = CLOSERS[tag]
        stops = set(LOOPERS[tag]) | {end}
        body = self.parse(stops)
        empty, saw_empty = 0, False
        if self._peek() and self._peek()[1] in LOOPERS[tag]:
            self.i += 1
            saw_empty = True
            empty = self.parse({end})
        if self._peek() and self._peek()[1] == end:
            self.i += 1
        if body:
            self.loop_findings.append(
                "line %d: {%% %s %%} body changes <%s> depth by %+d per iteration - "
                "each extra row nests one level deeper than the last"
                % (line_of(self.src, off), tag, self.tag, body)
            )
        if saw_empty and empty != body:
            self.loop_findings.append(
                "line %d: {%% empty %%} <%s> delta %+d does not match the loop body's %+d"
                % (line_of(self.src, off), self.tag, empty, body)
            )
        return body


def iter_templates(roots):
    for root in roots:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.html")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            yield path


def check(path):
    """Return the list of finding strings for one template."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    src = strip_noise(raw)
    findings = []

    for m in CLOSE_TAG_RE.finditer(src):
        name = m.group(1).lower()
        if "-" in name or ":" in name:
            continue  # custom element / namespaced tag
        if name not in KNOWN_TAGS:
            findings.append(
                "line %d: </%s> is not an HTML or SVG element - a browser discards an "
                "unknown end tag, so whatever it was meant to close stays open"
                % (line_of(src, m.start()), m.group(1))
            )

    if ALLOW_MARKER.search(raw):
        return findings

    for tag in ("div",) + CONTAINER_TAGS:
        counter = BranchAwareCounter(src, tag)
        total = counter.parse()
        findings.extend(counter.loop_findings)
        if total:
            findings.append(
                "net <%s> delta %+d - the template %s"
                % (tag, total,
                   "opens %d more <%s> than it closes" % (total, tag) if total > 0
                   else "closes %d more </%s> than it opens" % (-total, tag))
            )
            findings.extend(counter.branch_findings)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--roots", nargs="*", default=list(SCAN_ROOTS))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    scanned = 0
    flagged = []
    for path in iter_templates(args.roots):
        scanned += 1
        found = check(path)
        if found:
            flagged.append((path, found))

    total = sum(len(f) for _, f in flagged)
    if not flagged:
        if not args.quiet:
            print("template-html-structure: %d templates scanned, 0 findings." % scanned)
        return 0

    print("template-html-structure: %d templates scanned, %d finding(s) in %d file(s).\n"
          % (scanned, total, len(flagged)))
    for path, found in flagged:
        print("%s" % path.relative_to(REPO_ROOT).as_posix())
        for item in found:
            print("    %s" % item)
        print("")
    print("An unclosed element does not raise and does not fail a test: the page 200s and")
    print("the browser silently reparents everything after it. Close the element, or - for")
    print("a partial deliberately closed by a sibling - add {# html-structure-allow: why #}.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
