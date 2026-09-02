#!/usr/bin/env python3
"""Shared CSS-delivery helpers for shell-template gates (stdlib only).

Gates keep asking a question that is NOT the one they mean:

  1. "Does this shell load <x>.css?"
     `if "x.css" not in template_text:` answers "is that filename SPELLED in
     this one file", which stopped matching reality when the tenant shell was
     bundled.  templates/portal_base.html links exactly one minified sheet,
     `css/portal-shell-enhanced.min.css`, which CONCATENATES 77 sources
     (scripts/portal_css_bundle_manifest.json -> scripts/build_portal_css_bundles.py).
     Every rule in those 77 files ships on that shell while none of their
     filenames appears anywhere in the template.  A filename test therefore
     reports "missing stylesheet" for CSS the browser definitely has.

  2. "Does <a>.css beat <b>.css?"
     Source order only decides a winner when two declarations tie on
     specificity and on !important.  A gate that asserts a <link> ORDER is
     using position as a proxy; `order_decided_collisions()` measures the
     thing itself.

Both helpers are deliberately narrow so the gates that use them can still
FAIL:

  * only a bundle DECLARED in a hash manifest counts;
  * the bundle must be LINKED by that specific shell;
  * the stylesheet must be listed in that bundle's `sources`;
  * the manifest's sha256 for that source must still match the file on disk.
    A stale source means the shell serves the rules that were current when the
    bundle was built, not the ones in the tree -- reporting that as "covered"
    would be a worse lie than the one this module exists to fix, so it is a
    finding of its own (BUNDLED_STALE), never a pass.

Scanning also ignores template text that cannot render: `{% comment %}`
blocks, `{# ... #}` comments, and `{% if False %}` branches.  Retired markup
is routinely parked in an `{% if False %}` block (see
templates/studio_os/shell.html), and a raw substring test happily "finds"
a stylesheet or an include that no browser will ever receive.

Known limit, found by mutating a gate that uses this module: a `<link>` inside a
`{% if %}` branch counts the same as an unconditional one. templates/portal_base.html
links the bundle twice -- deferred for everyone, and eagerly again under
`{% if request.GET.rmc_embed == '1' %}` -- so deleting the deferred link alone still
resolves BUNDLED. Deciding otherwise means evaluating arbitrary template conditions,
which is guesswork; the honest position is that this answers "is it referenced on a
path this shell can take", not "is it referenced on every path". Only `{% if False %}`
is treated as never-taken, because that is a declaration of intent rather than a
runtime condition.

CLI:
    python scripts/shell_css_contract.py            # bundle staleness report
    python scripts/shell_css_contract.py --resolve templates/portal_base.html rmc-command-bar.css
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "templates"

#: Hash manifests emitted by the bundle builders.  Only bundles declared here
#: can satisfy a stylesheet requirement.
BUNDLE_MANIFESTS = (
    "static/css/portal-bundles.manifest.json",
    "static/marketing/css/marketing-bundles.manifest.json",
)

DIRECT = "DIRECT"
BUNDLED = "BUNDLED"
BUNDLED_STALE = "BUNDLED_STALE"
ABSENT = "ABSENT"

_COMMENT_BLOCK = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.S)
_HASH_COMMENT = re.compile(r"\{#.*?#\}", re.S)
_TAG = re.compile(r"\{%\s*(\w+)[^%]*?%\}", re.S)
_IF_FALSE = re.compile(r"\{%\s*if\s+False\s*%\}", re.S)

_CSS_REF = re.compile(r"[\w./-]+\.css")
_INCLUDE = re.compile(r"\{%\s*include\s+[\"']([^\"']+)[\"']([^%]*)%\}", re.S)
_STYLESHEET_KWARG = re.compile(r"stylesheet\s*=\s*[\"']([^\"']+)[\"']")
_EXTENDS = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']\s*%\}")


# --------------------------------------------------------------------------
# template text
# --------------------------------------------------------------------------
def strip_unreachable(text: str) -> str:
    """Drop template text a browser can never receive.

    Removes `{% comment %}` blocks, `{# #}` comments, and every
    `{% if False %} ... {% endif %}` region (nesting-aware).  Everything a
    gate asserts should be asserted against THIS, not against the raw file:
    a retired block parked behind `{% if False %}` still contains all the old
    include paths and class names.
    """
    text = _COMMENT_BLOCK.sub(" ", text)
    text = _HASH_COMMENT.sub(" ", text)

    out: list[str] = []
    pos = 0
    while True:
        m = _IF_FALSE.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos : m.start()])
        depth = 1
        cursor = m.end()
        while depth and cursor < len(text):
            tag = _TAG.search(text, cursor)
            if not tag:
                cursor = len(text)
                break
            name = tag.group(1).lower()
            if name == "if":
                depth += 1
            elif name == "endif":
                depth -= 1
            cursor = tag.end()
        pos = cursor
    return "".join(out)


def _template_text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def reachable_text(rel: str) -> str:
    """`strip_unreachable()` applied to a repo-relative template path."""
    return strip_unreachable(_template_text(rel))


def linked_stylesheets(rel: str, depth: int = 2) -> set[str]:
    """Basenames of every stylesheet a shell actually delivers.

    Covers `{% static 'css/x.css' %}`, a literal href, and the
    `{% include "partials/rmc_deferred_stylesheet.html" with stylesheet="css/x.css" %}`
    indirection the tenant shell uses for its bundle.

    Follows `{% include %}` to `depth` levels (cycle-safe), because a `<link>`
    inside an included partial loads exactly like one written inline, and
    follows `{% extends %}` for the same reason: templates/control_plane_base.html
    writes no stylesheet of its own and inherits the whole head of
    templates/control_plane_skeleton.html, so asking only about its own bytes
    reports every one of them missing.  Depth stays deliberately shallow here --
    stylesheets live in the head and its immediate partials, and a deep walk
    would start counting page-level CSS as shell coverage.
    """
    return set(linked_stylesheet_sources(rel, depth=depth))


def linked_stylesheet_sources(rel: str, depth: int = 2) -> dict[str, str]:
    """`linked_stylesheets`, but mapping each basename to the template that links it.

    Naming the provider matters in the output: a shell can inherit its whole head
    (templates/control_plane_base.html gets every stylesheet from
    templates/control_plane_skeleton.html), and "linked by <the parent>" is a
    true statement where "linked directly" would not be.
    """
    seen: set[str] = set()
    found: dict[str, str] = {}

    def note(name: str, provider: str) -> None:
        found.setdefault(name, provider)

    def walk(target: str, level: int) -> None:
        if target in seen or level < 0:
            return
        seen.add(target)
        text = reachable_text(target)
        if not text:
            return
        for ref in _CSS_REF.findall(text):
            note(Path(ref).name, target)
        children: list[str] = list(_EXTENDS.findall(text))
        for inc_target, kwargs in _INCLUDE.findall(text):
            for ref in _STYLESHEET_KWARG.findall(kwargs):
                if ref.endswith(".css"):
                    note(Path(ref).name, target)
            children.append(inc_target)
        for child_name in children:
            child = "templates/" + child_name.lstrip("/")
            if (REPO / child).is_file():
                walk(child, level - 1)

    walk(rel, depth)
    return found


def reachable_templates(rel: str, depth: int = 6) -> set[str]:
    """Every template a request for *rel* actually renders.

    Follows `{% extends %}` UP the inheritance chain and `{% include %}` down,
    skipping unreachable text, so a question like "does this landing page render
    the activity ticker?" is answered against the tree the browser gets rather
    than against one file's raw bytes.  Depth is generous here (the shell chain
    landing -> control_plane_base -> control_plane_skeleton -> unified_header ->
    operator_topbar -> ticker partial is already five hops) but it is NOT used
    for stylesheet resolution, which stays deliberately shallow.
    """
    seen: set[str] = set()

    def walk(target: str, level: int) -> None:
        if target in seen or level < 0:
            return
        seen.add(target)
        text = reachable_text(target)
        if not text:
            return
        targets = [m for m in _EXTENDS.findall(text)]
        targets += [m for m, _kwargs in _INCLUDE.findall(text)]
        for child in targets:
            child_rel = "templates/" + child.lstrip("/")
            if (REPO / child_rel).is_file():
                walk(child_rel, level - 1)

    walk(rel, depth)
    seen.discard(rel)
    return seen


def included_templates(rel: str, depth: int = 6) -> set[str]:
    """Every template *rel* pulls in through `{% include %}` -- NOT its shell.

    `reachable_templates()` follows `{% extends %}` as well, which is right for
    "what does the browser receive" but wrong for "what does THIS PAGE declare".
    Every portal page inherits templates/portal_base.html, whose page body
    carries `data-rmc-page-fold-nav="required"` unconditionally, so a content
    assertion resolved through the extends chain passes for every page in the
    repo and can never fail.  Walking includes only keeps such a gate binding:
    the page's own content tree is the part it is actually responsible for.
    """
    seen: set[str] = set()

    def walk(target: str, level: int) -> None:
        if target in seen or level < 0:
            return
        seen.add(target)
        text = reachable_text(target)
        if not text:
            return
        for child, _kwargs in _INCLUDE.findall(text):
            child_rel = "templates/" + child.lstrip("/")
            if (REPO / child_rel).is_file():
                walk(child_rel, level - 1)

    walk(rel, depth)
    return seen


def content_text(rel: str, depth: int = 6) -> str:
    """Reachable text of *rel* plus every template it includes, concatenated.

    The string a content gate should grep: unreachable markup already removed,
    included partials already folded in, the inherited shell left out.
    """
    return "\n".join(
        reachable_text(target) for target in sorted(included_templates(rel, depth=depth))
    )


def renders(rel: str, template_name: str, depth: int = 6) -> bool:
    """True when *rel* actually renders the partial called *template_name*.

    `template_name` is matched on basename, so a caller can pass
    "_footer_temporal_dock.html" without pinning the partial's directory.
    """
    target = Path(template_name).name
    return any(Path(t).name == target for t in reachable_templates(rel, depth=depth))


# --------------------------------------------------------------------------
# bundles
# --------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bundles() -> dict[str, dict]:
    """Manifest-declared bundles keyed by their own basename.

    Each value: ``{"manifest": rel, "path": rel, "sources": {basename: entry}}``
    where *entry* is the manifest's ``{"path", "sha256", "bytes"}`` record.
    """
    bundles: dict[str, dict] = {}
    for manifest_rel in BUNDLE_MANIFESTS:
        manifest_path = REPO / manifest_rel
        if not manifest_path.is_file():
            continue
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            bundle_rel = entry.get("path")
            sources = entry.get("sources")
            if not bundle_rel or not isinstance(sources, list) or not sources:
                continue
            bundles[Path(bundle_rel).name] = {
                "manifest": manifest_rel,
                "key": key,
                "path": bundle_rel,
                "sources": {Path(s["path"]).name: s for s in sources},
            }
    return bundles


def stale_bundle_sources() -> list[dict]:
    """Sources whose on-disk sha256 no longer matches the built bundle.

    A stale source means the shell is serving the rules captured at build
    time.  Returned records carry ``bundle``, ``source``, ``manifest_sha``,
    ``disk_sha`` and ``reason`` (``"drift"`` or ``"deleted"``).
    """
    stale: list[dict] = []
    for bundle_name, bundle in load_bundles().items():
        for src_name, entry in bundle["sources"].items():
            src_path = REPO / entry["path"]
            if not src_path.is_file():
                stale.append(
                    {
                        "bundle": bundle_name,
                        "source": entry["path"],
                        "manifest_sha": entry.get("sha256", ""),
                        "disk_sha": "",
                        "reason": "deleted",
                    }
                )
                continue
            disk = _sha256(src_path)
            if disk != entry.get("sha256"):
                stale.append(
                    {
                        "bundle": bundle_name,
                        "source": entry["path"],
                        "manifest_sha": entry.get("sha256", ""),
                        "disk_sha": disk,
                        "reason": "drift",
                    }
                )
    return stale


def resolve(shell_rel: str, css_name: str, depth: int = 2) -> tuple[str, str]:
    """How (if at all) *shell_rel* delivers *css_name*.

    Returns ``(status, detail)`` where status is DIRECT / BUNDLED /
    BUNDLED_STALE / ABSENT.
    """
    css_name = Path(css_name).name
    linked = linked_stylesheet_sources(shell_rel, depth=depth)
    if css_name in linked:
        provider = linked[css_name]
        where = "directly" if provider == shell_rel else f"via {provider}"
        return DIRECT, f"linked {where}"

    bundles = load_bundles()
    for bundle_name in sorted(set(linked) & set(bundles)):
        bundle = bundles[bundle_name]
        entry = bundle["sources"].get(css_name)
        if entry is None:
            continue
        if not (REPO / bundle["path"]).is_file():
            continue
        src_path = REPO / entry["path"]
        if not src_path.is_file():
            return (
                BUNDLED_STALE,
                f"{bundle_name} lists {entry['path']} but that file is gone",
            )
        if _sha256(src_path) != entry.get("sha256"):
            return (
                BUNDLED_STALE,
                f"{bundle_name} was built from an older {entry['path']} "
                f"(manifest sha {str(entry.get('sha256'))[:12]}, "
                f"disk sha {_sha256(src_path)[:12]}) -- rebuild with "
                f"scripts/build_portal_css_bundles.py",
            )
        bundle_provider = linked[bundle_name]
        via = "" if bundle_provider == shell_rel else f" via {bundle_provider}"
        return (
            BUNDLED,
            f"bundled into {bundle_name}, linked by this shell{via} "
            f"({bundle['manifest']})",
        )
    return ABSENT, f"neither linked nor bundled on {shell_rel}"


def missing_stylesheet(shell_rel: str, css_name: str, depth: int = 2) -> str | None:
    """Finding string when *shell_rel* does not deliver *css_name*, else None."""
    status, detail = resolve(shell_rel, css_name, depth=depth)
    if status in (DIRECT, BUNDLED):
        return None
    if status == BUNDLED_STALE:
        return f"{shell_rel}: {css_name} is served STALE -- {detail}"
    return f"{shell_rel}: missing stylesheet {css_name} ({detail})"


# --------------------------------------------------------------------------
# cascade order
# --------------------------------------------------------------------------
def _rules(css_rel: str) -> list[tuple[str, set[str], set[str]]]:
    path = REPO / css_rel
    if not path.is_file():
        return []
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    rules: list[tuple[str, set[str], set[str]]] = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        selector = match.group(1).strip().split("}")[-1].strip()
        body = match.group(2)
        if not selector or selector.startswith("@"):
            continue
        props = {m.group(1) for m in re.finditer(r"([\w-]+)\s*:", body)}
        important = {
            m.group(1) for m in re.finditer(r"([\w-]+)\s*:[^;]*!important", body)
        }
        for part in selector.split(","):
            part = part.strip()
            if part and not part.startswith("@"):
                rules.append((part, props, important))
    return rules


def specificity(selector: str) -> tuple[int, int, int]:
    """(ids, classes, elements) — good enough to spot TIES, which is all we need."""
    sel = re.sub(r"::?[\w-]+\([^)]*\)", " PSEUDOFN ", selector)
    ids = len(re.findall(r"#[\w-]+", sel))
    classes = (
        len(re.findall(r"\.[\w-]+", sel))
        + len(re.findall(r"\[[^\]]+\]", sel))
        + len(re.findall(r"(?<!:):[\w-]+", sel))
    )
    elements = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", sel))
    return ids, classes, elements


def _rightmost_keys(selector: str) -> set[str]:
    last = re.split(r"[\s>+~]+", selector.strip())[-1]
    return set(re.findall(r"[#.][\w-]+", last))


def order_decided_collisions(css_a: str, css_b: str) -> list[dict]:
    """Declarations where SOURCE ORDER alone picks the winner between two sheets.

    A pair qualifies when the two selectors can hit the same element (they
    share a class/id in their rightmost compound), they set the same property,
    they agree on !important, and their specificities TIE.  Anything else is
    decided by specificity or origin, so moving a <link> changes nothing.

    An empty list is the evidence that a <link>-order assertion between these
    two sheets is a proxy with no subject.
    """
    a_rules = _rules(css_a)
    b_rules = _rules(css_b)
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for a_sel, a_props, a_imp in a_rules:
        a_keys = _rightmost_keys(a_sel)
        if not a_keys:
            continue
        a_spec = specificity(a_sel)
        for b_sel, b_props, b_imp in b_rules:
            if not (a_keys & _rightmost_keys(b_sel)):
                continue
            shared = a_props & b_props
            if not shared or a_spec != specificity(b_sel):
                continue
            for prop in sorted(shared):
                if (prop in a_imp) != (prop in b_imp):
                    continue
                key = (prop, a_sel, b_sel)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "property": prop,
                        "a": a_sel,
                        "b": b_sel,
                        "specificity": a_spec,
                        "important": prop in a_imp,
                    }
                )
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve", nargs=2, metavar=("SHELL", "CSS"))
    parser.add_argument("--collisions", nargs=2, metavar=("CSS_A", "CSS_B"))
    args = parser.parse_args()

    if args.resolve:
        status, detail = resolve(args.resolve[0], args.resolve[1])
        print(f"{status}: {detail}")
        return 0 if status in (DIRECT, BUNDLED) else 1

    if args.collisions:
        hits = order_decided_collisions(*args.collisions)
        print(f"order-decided collisions: {len(hits)}")
        for hit in hits:
            print(f"  {hit['property']} spec={hit['specificity']}")
            print(f"    a: {hit['a']}")
            print(f"    b: {hit['b']}")
        return 1 if hits else 0

    bundles = load_bundles()
    total = sum(len(b["sources"]) for b in bundles.values())
    stale = stale_bundle_sources()
    print(f"bundles declared: {len(bundles)}   sources: {total}   stale: {len(stale)}")
    for name, bundle in sorted(bundles.items()):
        print(f"  {name}: {len(bundle['sources'])} sources ({bundle['manifest']})")
    for item in stale:
        print(
            f"  STALE {item['bundle']} <- {item['source']} "
            f"({item['reason']}: manifest {item['manifest_sha'][:12]} "
            f"vs disk {item['disk_sha'][:12]})"
        )
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
