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


def url_names(path: str | Path) -> list[tuple[str, int]]:
    """Every literal route name this template routes to, with its arg count.

    Returns (name, arg_count) pairs. A ``{% url some_var %}`` contributes
    nothing -- the name is not knowable without a render, and pretending
    otherwise would report a name that is really a variable.
    """
    from django.template.defaulttags import URLNode

    source = Path(path).read_text(encoding="utf-8")
    template = engines["django"].from_string(source).template
    out: list[tuple[str, int]] = []
    for node in template.nodelist.get_nodes_by_type(URLNode):
        var = getattr(node.view_name, "var", None)
        if isinstance(var, str):
            out.append((str(var), len(node.args) + len(node.kwargs)))
    return out


def assert_urls_reverse(case, path: str | Path) -> None:
    """Fail unless every argument-free {% url %} in ``path`` reverses.

    A route that was renamed or dropped leaves a template that still parses
    and still passes every substring assertion ever written about it, and
    fails only when someone loads the page -- or silently renders href=""
    if the name came from a context variable instead.

    Reverses against settings.ROOT_URLCONF, which outside a request is the
    dev superset: a name that resolves here may still be absent on a tenant
    host. This proves the name EXISTS, not that a given host can reach it.

    Names taking arguments are skipped (there are no values to give them)
    and the count is asserted non-zero, so a template that routes nowhere
    cannot pass by having nothing to check.
    """
    from django.urls import NoReverseMatch, reverse

    names = url_names(path)
    case.assertTrue(
        names,
        f"{path} contains no literal {{% url %}} at all; either it routes "
        f"nowhere or its body has been emptied",
    )
    checked = 0
    for name, argc in names:
        if argc:
            continue
        checked += 1
        try:
            reverse(name)
        except NoReverseMatch as exc:  # pragma: no cover - the failure IS the point
            case.fail(f"{path} routes to {name!r}, which does not reverse: {exc}")
    case.assertTrue(
        checked,
        f"{path} has {len(names)} url tag(s) but every one takes arguments, "
        f"so nothing was actually reversed",
    )

def _condition_text(node) -> str:
    """One {% if %} condition rendered back to source-like text."""
    if node is None:
        return ""
    operator = getattr(node, "id", None)
    first = getattr(node, "first", None)
    second = getattr(node, "second", None)
    if operator is not None and first is not None:
        if second is None:
            return f"{operator} {_condition_text(first)}"
        return f"{_condition_text(first)} {operator} {_condition_text(second)}"
    value = getattr(node, "value", None)
    token = getattr(value, "token", None)
    return str(token) if token is not None else str(node)


def branch_conditions(path: str | Path) -> list[str]:
    """Every {% if %} / {% elif %} condition this template branches on.

    Normalised back to source-like text: ``a == 'b'``, ``not a.b.c``,
    ``a != 'b'``. Whitespace is single-spaced, so an assertion written
    against this does not break when someone reflows the tag.

    An {% else %} arm contributes nothing -- it has no condition.

    Sound for the same reason as the rest of this module: a template whose
    body is one {% comment %} parses to zero IfNodes.
    """
    from django.template.defaulttags import IfNode

    source = Path(path).read_text(encoding="utf-8")
    template = engines["django"].from_string(source).template
    out: list[str] = []
    for node in template.nodelist.get_nodes_by_type(IfNode):
        for condition, _nodelist in node.conditions_nodelists:
            text = _condition_text(condition)
            if text:
                out.append(text)
    return out


def assert_branches_on(case, path: str | Path, *expressions: str) -> None:
    """Fail unless ``path`` really branches on every one of ``expressions``.

    Match is on the normalised condition text, so give it the way the
    template writes it: ``request.public_host_kind == 'manager'``.

    A clause of a compound condition counts: real templates write
    ``{% if nav_role != 'STUDENT' and nav_role != 'TEACHER' %}`` and a test
    that means "this is gated on nav_role" should not break when a third
    clause is added. Exact-match would have made the helper unusable on the
    very tests that asked for it.
    """
    conditions = branch_conditions(path)
    for expression in expressions:
        wanted = " ".join(expression.split())
        case.assertTrue(
            any(wanted == c or wanted in c for c in conditions),
            f"{path} does not branch on {wanted!r}. "
            f"It branches on {len(conditions)} condition(s): {conditions[:12]}",
        )


def assert_does_not_branch_on(case, path: str | Path, *expressions: str) -> None:
    """The mirror -- and the reason this pair exists.

    A test whose whole claim is that a template must NOT branch on something
    (a raw role column, an impersonation flag) cannot be made sound by an
    absence alone: emptying the template satisfies it. Pair it with an
    assert_branches_on for the condition that SHOULD be there.
    """
    conditions = branch_conditions(path)
    for expression in expressions:
        unwanted = " ".join(expression.split())
        case.assertFalse(
            any(unwanted == c or unwanted in c for c in conditions),
            f"{path} still branches on {unwanted!r}",
        )

def assert_does_not_emit(case, path: str | Path, *needles: str) -> None:
    """Fail if ``path`` actually EMITS any of ``needles``.

    The mirror of assert_markup, and the difference from a plain
    assertNotIn over the file is the whole point: a class named in a
    {# comment #} that forbids it is not the class being used. Measured:
    templates/admin/base.html contains the string rmc-app-shell--fluid
    exactly once, inside a comment reading "never rmc-app-shell--fluid",
    and a source-level assertIn for it PASSED for months.

    Weaker than a source read in one direction and stronger in the other:
    it cannot see a class a tag builds at render time, and it does not
    fire on prose. Use it when the claim is about the PAGE, not the file.
    """
    text = literal_text(path)
    for needle in needles:
        case.assertNotIn(
            needle,
            text,
            f"{path} still emits {needle!r} as literal markup",
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
