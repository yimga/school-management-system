"""Ask the template ENGINE what a template wires, not the file's text.

``assertIn("back_to_top.html", Path(t).read_text())`` passes over a template
whose entire body is ``{% comment %}back_to_top.html{% endcomment %}``. It
asserts the WORD, not the wiring -- which is the whole defect class
scripts/verify_test_asserts_behaviour.py measures, and it is why 11 of the 13
tests in test_page_fold_standards.py were judged VACUOUS.

Parsing the source with Django's own engine answers the question those tests
mean to ask -- is this partial actually pulled in? -- and a comment produces a
CommentNode, not an IncludeNode. That is exactly the harness's mutation, so a
test written against these helpers fails when the template stops wiring
anything, which is what SOUND means.

No database and no request: this is a parse, not a render. SimpleTestCase is
enough.
"""

from __future__ import annotations

from pathlib import Path

from django.template import engines
from django.template.base import TextNode
from django.template.loader_tags import ExtendsNode, IncludeNode


def _literal_name(expr) -> str | None:
    """The template name out of an IncludeNode/ExtendsNode expression.

    A literal (``{% include "a/b.html" %}``) yields the string. A variable
    (``{% include dashboard_partial %}``) yields the variable's name, which
    simply will not match a filename -- correct, because a variable include
    is not a static guarantee that any particular partial is wired.
    """
    if expr is None:
        return None
    var = getattr(expr, "var", expr)
    literal = getattr(var, "literal", None)
    if literal is not None:
        return str(literal)
    text = str(var).strip("\"'")
    return text or None


def wired_templates(source: str) -> set[str]:
    """Every template name this source actually includes or extends."""
    template = engines["django"].from_string(source).template
    names: set[str] = set()
    for node in template.nodelist.get_nodes_by_type((IncludeNode, ExtendsNode)):
        expr = getattr(node, "template", None)
        if expr is None:
            expr = getattr(node, "parent_name", None)
        name = _literal_name(expr)
        if name:
            names.add(name)
    return names


def wired_in(path: str | Path) -> set[str]:
    """wired_templates() for a template file on disk."""
    return wired_templates(Path(path).read_text(encoding="utf-8"))


def assert_wires(case, path: str | Path, *names: str) -> None:
    """Fail unless ``path`` really includes or extends every one of ``names``.

    Names may be given bare (``back_to_top.html``) or loader-relative
    (``partials/back_to_top.html``); a bare name matches any directory.
    """
    wired = wired_in(path)
    for name in names:
        case.assertTrue(
            any(w == name or w.endswith("/" + name) for w in wired),
            f"{path} does not include or extend {name}. "
            f"It wires: {sorted(wired)}",
        )


def assert_does_not_wire(case, path: str | Path, *names: str) -> None:
    """The mirror: fail if ``path`` wires any of ``names``."""
    wired = wired_in(path)
    for name in names:
        case.assertFalse(
            any(w == name or w.endswith("/" + name) for w in wired),
            f"{path} still includes or extends {name}",
        )


def static_assets(path: str | Path) -> set[str]:
    """Every asset this template loads through ``{% static %}``.

    A stylesheet or script name is the single most common thing these
    contract tests assert, and it is the one thing neither literal_text nor
    wired_templates can see: the argument of ``{% static %}`` is a filter
    expression inside a tag, not emitted text and not a template include. The
    honest alternatives were a full render -- which most shells cannot do
    standalone, they need SITE and a request -- or reading the file, which is
    the vacuous assertion this module exists to replace.

    Sound for the same reason as the rest: a template whose body is one
    ``{% comment %}`` parses to zero StaticNodes.
    """
    from django.templatetags.static import StaticNode

    source = Path(path).read_text(encoding="utf-8")
    template = engines["django"].from_string(source).template
    out: set[str] = set()
    for node in template.nodelist.get_nodes_by_type(StaticNode):
        var = getattr(node.path, "var", None)
        literal = getattr(var, "literal", None)
        name = literal if literal is not None else str(var)
        if name:
            out.add(str(name).strip("\"'"))
    return out


def assert_loads_static(case, path: str | Path, *names: str) -> None:
    """Fail unless ``path`` really loads every one of ``names`` via {% static %}."""
    assets = static_assets(path)
    for name in names:
        case.assertTrue(
            any(a == name or a.endswith("/" + name) for a in assets),
            f"{path} does not load {name} through a static tag. "
            f"It loads {len(assets)} asset(s): {sorted(assets)[:12]}",
        )


def literal_text(path: str | Path) -> str:
    """Everything the template emits VERBATIM, as the parser sees it.

    Reading the file instead finds a needle that sits inside a
    ``{% comment %}`` block -- which is precisely how assertions on markup
    became vacuous, because that is the mutation the vacuity harness
    plants. Django discards a comment's contents at parse time, so it
    contributes no TextNode and cannot satisfy an assertion made here.

    Static text only: an attribute emitted by a tag or a variable will not
    appear, and a test that needs one of those needs a real render.
    """
    source = Path(path).read_text(encoding="utf-8")
    template = engines["django"].from_string(source).template
    return "".join(
        node.s for node in template.nodelist.get_nodes_by_type(TextNode)
    )


def assert_markup(case, path: str | Path, *needles: str) -> None:
    """Fail unless ``path`` really EMITS every one of ``needles``."""
    text = literal_text(path)
    for needle in needles:
        case.assertIn(
            needle,
            text,
            f"{path} does not emit {needle!r} as literal markup "
            f"(it may be present in the file but inside a comment)",
        )


def rendered_source(path: str | Path, context: dict | None = None) -> str:
    """Render the template FROM ITS BYTES and return the output.

    From the bytes, not through the loader: the loader can be cached, and a
    cached template would serve the pre-mutation source and make a test look
    sound when it is not. Reading the file each time is the point.

    Only for templates that stand alone -- no request, no database. Where
    that holds it is the strongest assertion available without a client,
    because it asks what the page EMITS, and a ``{% comment %}`` emits "".
    """
    source = Path(path).read_text(encoding="utf-8")
    return engines["django"].from_string(source).render(context or {})


def assert_renders(case, path: str | Path, *needles: str) -> None:
    """Fail unless rendering ``path`` actually produces every needle."""
    out = rendered_source(path)
    for needle in needles:
        case.assertIn(
            needle,
            out,
            f"{path} renders without {needle!r} "
            f"({len(out)} bytes of output)",
        )
