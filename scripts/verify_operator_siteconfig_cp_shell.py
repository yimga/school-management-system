#!/usr/bin/env python3
"""
QA gate: manager-host siteconfig operator pages use CP shell + body partials.

Checks:
- ``render_siteconfig_stem`` is called only with keyword arguments it accepts.
- Every stem whose view can be served on a CONTROL-PLANE host has the body
  partial that host renders.
- A portal wrapper whose body partial exists on disk includes THAT partial
  (no stale inline copy of content that is maintained in the partial).
- A portal wrapper with no body partial renders content of its own.
- Body partials declare exactly one primary h1 (visible or visually-hidden).
- ``operator_control_plane_page`` suppresses duplicate workspace header.
- Former-allowlist templates use ``render_siteconfig_stem``, not plain render().

WHY THE BODY-PARTIAL RULE IS ROUTING-AWARE
------------------------------------------
``render_siteconfig_stem`` (apps/siteconfig/control_plane_render.py) has two
branches:

    use_control_plane_shell(request)  ->  operator_control_plane_page.html
                                          + siteconfig/partials/<stem>_body.html
    otherwise                         ->  siteconfig/<stem>.html

ONLY the first branch ever loads the body partial, and ``use_control_plane_shell``
returns False on every tenant host (apps/schools/control_plane.py: a tenant
subdomain, custom domain or sovereign box must never see operator chrome). A stem
whose view is routed ONLY in ``config.tenant_urls`` therefore cannot reach the
branch that needs the partial. Demanding one anyway asserts a WORD, not the
behaviour, and this gate did exactly that: on 2026-09-02 it printed 17 findings
and every one of them was a page that renders correctly -- 16 deliberate
single-file tenant pages (proved by rendering each: 57-60 KB of HTML, one h1
each) plus one tenant-only stem.

What it did NOT print is the defect that was really there. Its stem scan read
only ``apps/siteconfig/``, so it never saw
``apps/schools/views_tenant_self_offboarding.py`` calling
``render_siteconfig_stem(..., page_title="Close school account")`` -- a keyword
the function does not take and does not absorb through **kwargs. Every
authorised GET of /school/studio/offboarding/ raised TypeError and returned 500,
from the commit that created the page (efcb8d652, 2026-05-22) until it was fixed.
Seventeen false findings, one real 500, and no test covers that view.

The exemption is FAIL-CLOSED. A stem is excused only when every one of its call
sites was located in a urlconf AND every one resolves under
``config.tenant_urls`` and under NEITHER ``config.urls`` (the developer/local
urlconf, where ``public_host_kind == "local"`` makes use_control_plane_shell
True) NOR ``config.manager_urls``. A stem this cannot prove tenant-only still
needs its partial, and a Django that will not boot is reported, never skipped.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "siteconfig"
PARTIALS = TEMPLATES / "partials"
RENDER_MODULE = ROOT / "apps" / "siteconfig" / "control_plane_render.py"
VIEWS_ROOT = ROOT / "apps"

sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# The urlconfs served to a host where use_control_plane_shell() can return True.
# "local" (a dev machine, or a bare IP) gets config.urls and IS control-plane;
# "manager" gets config.manager_urls. Everything else is a tenant, base, api or
# docs host, and none of those reach the control-plane branch.
CONTROL_PLANE_URLCONFS = ("config.urls", "config.manager_urls")
TENANT_URLCONF = "config.tenant_urls"

# Former allowlist -- must use render_siteconfig_stem (no plain render bypass).
FORBIDDEN_PLAIN_RENDER_TEMPLATES = frozenset(
    {
        "siteconfig/maintenance.html",
        "siteconfig/region_validation_dashboard.html",
        "siteconfig/region_comparison.html",
        "siteconfig/region_grading_scales_matrix.html",
    }
)
PLAIN_RENDER_RE = re.compile(
    r"render\s*\(\s*request\s*,\s*[\"'](siteconfig/[^\"']+)[\"']",
    re.MULTILINE,
)

H1_RE = re.compile(
    r"<h1\b[^>]*>|class=\"visually-hidden\"[^>]*data-rmc-injected-h1",
    re.IGNORECASE,
)

# Django's own template tag regex. Deliberately NOT re.DOTALL: Django's tag_re
# is not either, so a {% %} spread over two lines is not a tag at all -- it is
# text that prints its own source onto the page. Stripping it here as if it were
# a tag would hide that, and would also let a wrapper full of broken tag source
# count as "blank".
TAG_RE = re.compile(r"(\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\})")
BLOCK_OPEN_RE = re.compile(r"^\{%\s*block\s+([a-zA-Z0-9_]+)\s*%\}$")
BLOCK_END_RE = re.compile(r"^\{%\s*endblock")
INCLUDE_ANY_RE = re.compile(r"\{%\s*include\s")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
ELEMENT_RE = re.compile(r"<[A-Za-z]")


class StemCall:
    """One ``render_siteconfig_stem(request, "<stem>", ...)`` call site."""

    __slots__ = ("stem", "module", "func", "path", "lineno", "kwargs")

    def __init__(self, stem, module, func, path, lineno, kwargs):
        self.stem = stem
        self.module = module
        self.func = func
        self.path = path
        self.lineno = lineno
        self.kwargs = kwargs


def accepted_stem_kwargs() -> tuple[frozenset[str], bool]:
    """Keyword names ``render_siteconfig_stem`` accepts, read from its own AST.

    Read rather than hard-coded: a list of parameter names copied into a gate is
    the classic thing that keeps agreeing with a signature that has moved on.
    Returns (names, absorbs_anything) -- the second is True for **kwargs, in
    which case no keyword can be wrong.
    """
    tree = ast.parse(RENDER_MODULE.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "render_siteconfig_stem":
            names = {a.arg for a in node.args.args} | {
                a.arg for a in node.args.kwonlyargs
            }
            return frozenset(names), node.args.kwarg is not None
    return frozenset(), False


def _enclosing_function(parents: dict, node: ast.AST) -> str:
    cur = parents.get(node)
    while cur is not None and not isinstance(
        cur, (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        cur = parents.get(cur)
    return cur.name if cur is not None else ""


def stem_calls() -> tuple[list[StemCall], list[str]]:
    """Every literal-stem call site under apps/, plus notes on ones we cannot read.

    Scans apps/ entirely, not apps/siteconfig/. The stem renderer is imported by
    apps.schools and apps.lifecycle too, and a scan of one package reported a
    clean 23 stems while a 500 sat in another.
    """
    calls: list[StemCall] = []
    notes: list[str] = []
    for path in sorted(VIEWS_ROOT.rglob("*.py")):
        posix = path.as_posix()
        if (
            path.name.startswith("test_")
            or "/tests/" in posix
            or "/migrations/" in posix
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "render_siteconfig_stem" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            notes.append(f"{path.relative_to(ROOT)}: cannot parse ({exc})")
            continue
        parents: dict = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        module = path.relative_to(ROOT).as_posix()[: -len(".py")].replace("/", ".")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "render_siteconfig_stem":
                continue
            if (
                len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                calls.append(
                    StemCall(
                        stem=node.args[1].value,
                        module=module,
                        func=_enclosing_function(parents, node),
                        path=path.relative_to(ROOT).as_posix(),
                        lineno=node.lineno,
                        kwargs=[kw.arg for kw in node.keywords if kw.arg],
                    )
                )
            else:
                # Not a literal stem: the templates it needs cannot be named
                # here. Say so rather than counting it as checked.
                notes.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: "
                    "render_siteconfig_stem called with a non-literal stem; "
                    "its portal/body templates are UNCHECKED by this gate"
                )
    return calls, notes


def routed_callables(urlconf: str) -> set[tuple[str, str]]:
    """(module, function-name) for every view the given urlconf can dispatch to."""
    from django.urls import get_resolver
    from django.urls.resolvers import URLPattern, URLResolver

    found: set[tuple[str, str]] = set()

    def unwrap(func):
        seen = {func}
        stack = [func]
        while stack:
            current = stack.pop()
            for attr in ("__wrapped__", "view_class", "func"):
                nxt = getattr(current, attr, None)
                if nxt is not None and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def walk(resolver) -> None:
        for pattern in resolver.url_patterns:
            if isinstance(pattern, URLResolver):
                walk(pattern)
            elif isinstance(pattern, URLPattern):
                for func in unwrap(pattern.callback):
                    module = getattr(func, "__module__", "") or ""
                    qualname = getattr(func, "__qualname__", "") or getattr(
                        func, "__name__", ""
                    )
                    found.add((module, qualname.split(".")[0]))

    walk(get_resolver(urlconf))
    return found


def tenant_only_stems(calls: list[StemCall]) -> tuple[set[str], list[str]]:
    """Stems whose every call site is provably reachable on tenant hosts ONLY.

    Fail-closed: anything not positively proved tenant-only is left OUT, and a
    Django that will not boot returns an empty set plus a finding.
    """
    try:
        import django

        django.setup()
        control_plane: set[tuple[str, str]] = set()
        for urlconf in CONTROL_PLANE_URLCONFS:
            control_plane |= routed_callables(urlconf)
        tenant = routed_callables(TENANT_URLCONF)
    except Exception as exc:  # noqa: BLE001 - a boot failure is a finding, not a skip
        return set(), [
            "could not resolve URL routing "
            f"({type(exc).__name__}: {exc}); every stem is treated as "
            "control-plane reachable and must carry a body partial"
        ]

    by_stem: dict[str, list[StemCall]] = {}
    for call in calls:
        by_stem.setdefault(call.stem, []).append(call)

    known = control_plane | tenant
    exempt: set[str] = set()
    for stem, sites in by_stem.items():
        located = all((s.module, s.func) in known for s in sites)
        cp_reachable = any((s.module, s.func) in control_plane for s in sites)
        on_tenant = all((s.module, s.func) in tenant for s in sites)
        if located and on_tenant and not cp_reachable:
            exempt.add(stem)
    return exempt, []


def content_block(text: str) -> str | None:
    """Source of ``{% block content %}``, or None when the template has none."""
    tokens = list(TAG_RE.finditer(text))
    for index, token in enumerate(tokens):
        opened = BLOCK_OPEN_RE.match(token.group(0).strip())
        if not opened or opened.group(1) != "content":
            continue
        depth = 1
        start = token.end()
        for later in tokens[index + 1 :]:
            stripped = later.group(0).strip()
            if BLOCK_OPEN_RE.match(stripped):
                depth += 1
            elif BLOCK_END_RE.match(stripped):
                depth -= 1
                if depth == 0:
                    return text[start : later.start()]
        return text[start:]
    return None


def block_is_blank(block: str) -> bool:
    """True when this content block would put nothing on the page.

    An ``{% include %}`` counts as content: the wrapper delegates, and whether
    the included file is empty is that file's problem, checked where it lives.
    """
    if INCLUDE_ANY_RE.search(block):
        return False
    visible = HTML_COMMENT_RE.sub(" ", TAG_RE.sub(" ", block))
    if ELEMENT_RE.search(visible):
        return False
    return len(re.sub(r"\s+", "", re.sub(r"<[^>]*>", " ", visible))) < 8


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="siteconfig operator CP shell gate")
    parser.add_argument(
        "--no-routing",
        action="store_true",
        help="skip the URL-routing pass (every stem then needs a body partial)",
    )
    args = parser.parse_args(argv)

    findings: list[str] = []

    op_page = TEMPLATES / "operator_control_plane_page.html"
    if op_page.exists():
        op_text = op_page.read_text(encoding="utf-8", errors="replace")
        if "{% block cp_workspace_header %}{% endblock %}" not in op_text.replace(
            " ", ""
        ):
            if "block cp_workspace_header" not in op_text:
                findings.append(
                    "operator_control_plane_page.html must override cp_workspace_header "
                    "(empty) to avoid duplicate rmc_os_page_header with body partials."
                )

    for path in (ROOT / "apps" / "siteconfig" / "views.py",):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for template in PLAIN_RENDER_RE.findall(text):
            if template in FORBIDDEN_PLAIN_RENDER_TEMPLATES:
                findings.append(
                    f"{path.relative_to(ROOT)}: plain render() for {template} "
                    "(use render_siteconfig_stem)"
                )

    calls, notes = stem_calls()
    findings.extend(notes)

    accepted, absorbs_anything = accepted_stem_kwargs()
    if not accepted:
        findings.append(
            "cannot read render_siteconfig_stem's signature from "
            f"{RENDER_MODULE.relative_to(ROOT)}; the keyword check did not run"
        )
    elif not absorbs_anything:
        for call in calls:
            unknown = [kw for kw in call.kwargs if kw not in accepted]
            if unknown:
                findings.append(
                    f"{call.path}:{call.lineno}: render_siteconfig_stem() called with "
                    f"{', '.join(sorted(unknown))}= which it does not accept -- "
                    "TypeError (HTTP 500) on every request to this view"
                )

    if args.no_routing:
        exempt: set[str] = set()
        routing_findings: list[str] = []
    else:
        exempt, routing_findings = tenant_only_stems(calls)
    findings.extend(routing_findings)

    stems = {call.stem for call in calls}
    for stem in sorted(stems):
        portal = TEMPLATES / f"{stem}.html"
        body = PARTIALS / f"{stem}_body.html"
        if not portal.is_file():
            findings.append(f"missing portal template for stem {stem!r}")
        if not body.is_file():
            if stem not in exempt:
                findings.append(
                    f"missing body partial for stem {stem!r} "
                    "(its view is reachable on a control-plane host, where "
                    "render_siteconfig_operator_page renders that partial)"
                )
            continue
        portal_text = portal.read_text(encoding="utf-8", errors="replace")
        if f"partials/{stem}_body.html" not in portal_text:
            findings.append(
                f"{portal.name} does not include siteconfig/partials/{stem}_body.html"
            )
        body_text = body.read_text(encoding="utf-8", errors="replace")
        h1_count = len(H1_RE.findall(body_text))
        if h1_count < 1:
            findings.append(
                f"partials/{stem}_body.html: no <h1> or data-rmc-injected-h1 (SEO/a11y)"
            )
        if h1_count > 2:
            findings.append(
                f"partials/{stem}_body.html: multiple h1 markers ({h1_count})"
            )

    # Portal templates on disk that extend portal_base must actually put
    # something on the page -- either their own content, or the body partial
    # that exists for them. There is no allowlist: "this page is legacy" was
    # never a reason for it to render blank, and the two entries that used to
    # sit here (customizer.html, workflow_hub.html) are full pages that pass
    # this check on their own.
    for portal in sorted(TEMPLATES.glob("*.html")):
        if portal.name == "operator_control_plane_page.html":
            continue
        text = portal.read_text(encoding="utf-8", errors="replace")
        if 'extends "portal_base.html"' not in text:
            continue
        own_partial = PARTIALS / f"{portal.stem}_body.html"
        if own_partial.is_file():
            if f"partials/{portal.stem}_body.html" not in text:
                findings.append(
                    f"{portal.name}: siteconfig/partials/{portal.stem}_body.html "
                    "exists but the wrapper does not include it -- the page is "
                    "serving a stale inline copy of content maintained elsewhere"
                )
            continue
        block = content_block(text)
        if block is None:
            findings.append(
                f"{portal.name}: extends portal_base with no content block -- "
                "the page body is empty"
            )
        elif block_is_blank(block):
            findings.append(
                f"{portal.name}: the content block is empty and includes nothing -- "
                "the page renders blank"
            )

    if findings:
        print(f"verify_operator_siteconfig_cp_shell: {len(findings)} finding(s)\n")
        for item in findings:
            print(f"  - {item}")
        return 1

    print(
        f"verify_operator_siteconfig_cp_shell: OK ({len(stems)} stems, "
        f"{len(exempt)} tenant-host-only, "
        f"{len(list(PARTIALS.glob('*_body.html')))} body partials)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
